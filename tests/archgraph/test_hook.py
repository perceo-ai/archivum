from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from archivum.archgraph.ingest import IngestReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_report() -> IngestReport:
    return IngestReport(files=3, nodes=5, edges=2, rejected=0, cache_hits=1)


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


def test_cli_real_ingest_smoke(git_repo, tmp_path):
    """End-to-end smoke: real _run_ingest via CLI returns 0."""
    from archivum.archgraph.hook import main

    cache_dir = tmp_path / "c"
    rc = main(["ingest", str(git_repo), "--scope", "repo:test", "--cache-dir", str(cache_dir)])
    assert rc == 0
