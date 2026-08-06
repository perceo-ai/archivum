from __future__ import annotations

import re
from pathlib import Path

import pytest

from archivum.archgraph.repo import collect_files, repo_artifacts, snapshot_repo
from archivum.archgraph.mapper import CandidateArtifact, CandidateRelationship


def test_snapshot_reads_head_sha(git_repo):
    snap = snapshot_repo(git_repo)
    assert re.match(r"^[0-9a-f]{40}$", snap.commit_sha), f"unexpected sha: {snap.commit_sha!r}"


def test_collect_files_filters(git_repo):
    # add a node_modules/x.py that should be excluded
    nm = git_repo / "node_modules"
    nm.mkdir()
    (nm / "x.py").write_text("# excluded")

    files = collect_files(git_repo)

    # all returned files must be .py (since py_sample only has .py)
    assert all(p.suffix == ".py" for p in files)
    # none should be under .git/
    assert not any(".git" in p.parts for p in files)
    # node_modules/x.py must be excluded
    assert not any("node_modules" in p.parts for p in files)
    # there should be at least one file
    assert len(files) > 0


def test_repo_artifacts_shapes(git_repo):
    snap = snapshot_repo(git_repo)
    results = repo_artifacts(snap, scope="repo:test")

    artifacts = [r for r in results if isinstance(r, CandidateArtifact)]
    rels = [r for r in results if isinstance(r, CandidateRelationship)]

    kinds = {a.kind for a in artifacts}
    assert "repo" in kinds
    assert "commit" in kinds
    assert len(artifacts) == 2

    assert len(rels) == 1
    rel = rels[0]
    commit_art = next(a for a in artifacts if a.kind == "commit")
    repo_art = next(a for a in artifacts if a.kind == "repo")
    assert rel.src_id == commit_art.id
    assert rel.dst_id == repo_art.id


def test_non_git_dir_working_tree(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    snap = snapshot_repo(plain)
    assert snap.commit_sha == "working-tree"
