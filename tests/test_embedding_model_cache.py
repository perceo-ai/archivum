"""The embedding model is cached where fastembed looks, and cannot stop the app.

Both halves of this cost the deployment twenty minutes of downtime on
2026-11-04. A `model_cache` volume was mounted at `/home/app/.cache` while
fastembed defaults to `/tmp/fastembed_cache`, so nothing was ever cached and
every restart re-downloaded the model. One of those downloads was interrupted,
leaving a snapshot directory with no model file in it — and because
`init_collection` aborted startup, `onnxruntime`'s `NO_SUCHFILE` then stopped
the backend from starting at all, on every restart of that container, taking
the wiki, code search and fix recall down with it. None of those need a vector.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("service", ["backend", "mcp"])
def test_the_cache_path_is_inside_the_volume_that_persists_it(compose, service):
    env = compose["services"][service].get("environment") or []
    setting = next((e for e in env if str(e).startswith("FASTEMBED_CACHE_PATH=")), None)
    assert setting, f"{service} must say where fastembed caches, or it uses /tmp"

    cache_path = setting.split("=", 1)[1]
    # Strip the `${VAR:-default}` form around the default.
    if cache_path.startswith("${"):
        cache_path = cache_path.split(":-", 1)[1].rstrip("}")

    mounts = compose["services"][service].get("volumes") or []
    targets = [str(m).split(":")[1] for m in mounts if str(m).count(":") >= 1]
    assert any(cache_path.startswith(target) for target in targets), (
        f"{service} caches at {cache_path}, which no volume covers — "
        "mounting a volume elsewhere caches nothing"
    )


@pytest.mark.parametrize(
    "dockerfile", ["apps/backend/Dockerfile", "apps/backend/Dockerfile.mcp"]
)
def test_the_cache_directory_belongs_to_the_user_that_writes_it(dockerfile):
    """A fresh named volume takes the ownership of the path it covers.

    Root-owned, a container running as `app` cannot download into it.
    """
    text = (ROOT / dockerfile).read_text(encoding="utf-8")
    assert "/home/app/.cache" in text, f"{dockerfile} never creates the cache dir"
    chown_lines = [
        line
        for line in text.splitlines()
        if "chown" in line and "/home/app/.cache" in line
    ]
    assert chown_lines, f"{dockerfile} does not give the cache dir to `app`"


async def test_startup_survives_an_unusable_embedding_model(monkeypatch, tmp_path):
    """Vector search is one retrieval channel, not the service."""
    from unittest.mock import AsyncMock

    from archivum.config import Settings, get_settings

    # Real, writable paths: the lifespan creates its directories before it
    # touches any store.
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
        code_cache_dir=tmp_path / "code-cache",
    )
    monkeypatch.setattr("archivum.main.get_settings", lambda: settings)

    import archivum.main as main_mod

    boom = AsyncMock(side_effect=RuntimeError("NO_SUCHFILE: model_optimized.onnx"))
    monkeypatch.setattr(main_mod.qdrant, "init_collection", boom)
    monkeypatch.setattr(main_mod.sqlite, "init_db", AsyncMock())
    monkeypatch.setattr(main_mod.graph, "init_graph", AsyncMock())
    monkeypatch.setattr(main_mod.sqlite, "ensure_owner_exists", AsyncMock())

    app = main_mod.create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    # Entering the lifespan is what used to raise and exit the process.
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        assert client.get("/install").status_code == 200
    assert boom.await_count == 1, "the collection init must still be attempted"
