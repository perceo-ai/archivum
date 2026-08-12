from __future__ import annotations

import os
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from archivum.archgraph.ingest import IngestReport
from archivum.db import sqlite as app_sqlite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_report() -> IngestReport:
    return IngestReport(files=3, nodes=5, edges=2, rejected=0, cache_hits=1)


def _git_env() -> dict:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cli_ingest_invokes_pipeline(tmp_path, monkeypatch):
    """main(['ingest', <repo>, '--scope', 'repo:test']) calls _run_ingest and returns 0."""
    from archivum.archgraph import hook

    calls: list[dict] = []

    async def fake_run_ingest(repo: Path, scope: str, cache_dir: Path, update: bool) -> IngestReport:
        calls.append({"repo": repo, "scope": scope, "cache_dir": cache_dir, "update": update})
        return _fake_report()

    monkeypatch.setattr(hook, "_run_ingest", fake_run_ingest)

    rc = hook.main(["ingest", str(tmp_path), "--scope", "repo:test"])

    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["repo"] == tmp_path
    assert calls[0]["scope"] == "repo:test"
    assert calls[0]["update"] is False


def test_install_post_commit_hook(tmp_path):
    """install_post_commit_hook writes an executable post-commit script."""
    from archivum.archgraph.hook import install_post_commit_hook

    # Create a minimal .git/hooks directory
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)

    p = install_post_commit_hook(tmp_path)

    assert p.exists()
    assert os.access(p, os.X_OK)
    content = p.read_text()
    assert "archivum-archgraph ingest" in content
    assert "--update" in content


def test_bad_args_returns_nonzero():
    """main(['nonsense']) returns non-zero without raising."""
    from archivum.archgraph.hook import main

    rc = main(["nonsense"])
    assert rc != 0


def test_cli_real_ingest_smoke(git_repo, tmp_path, monkeypatch):
    """End-to-end smoke: real _run_ingest via CLI returns 0."""
    from archivum.archgraph.hook import main

    cache_dir = tmp_path / "c"
    canonical_db = tmp_path / "archivum.db"
    monkeypatch.setattr(app_sqlite, "_db_path", canonical_db)

    rc = main(["ingest", str(git_repo), "--scope", "repo:test", "--cache-dir", str(cache_dir)])
    assert rc == 0
    assert canonical_db.exists()
    assert not (git_repo / ".archivum" / "knowledge.db").exists()

    with sqlite3.connect(canonical_db) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "knowledge_objects" in tables

    with sqlite3.connect(cache_dir / "index.db") as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "knowledge_objects" not in tables


def test_cli_update_uses_last_indexed_sha_to_prune_deleted_files(tmp_path, monkeypatch):
    from archivum.archgraph.hook import main

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "live.py").write_text("class Live:\n    def run(self):\n        return 1\n")
    (repo / "stale.py").write_text("class Stale:\n    def run(self):\n        return 2\n")
    env = _git_env()
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env)

    cache_dir = tmp_path / "cache"
    canonical_db = tmp_path / "archivum.db"
    monkeypatch.setattr(app_sqlite, "_db_path", canonical_db)

    rc = main(["ingest", str(repo), "--scope", "repo:test", "--cache-dir", str(cache_dir)])
    assert rc == 0

    (repo / "stale.py").unlink()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "delete stale"], cwd=repo, check=True, env=env)

    rc = main(
        ["ingest", str(repo), "--scope", "repo:test", "--cache-dir", str(cache_dir), "--update"]
    )
    assert rc == 0

    with sqlite3.connect(canonical_db) as conn:
        labels = {row[0] for row in conn.execute("SELECT label FROM knowledge_objects")}

    assert "Live" in labels
    assert "Stale" not in labels
