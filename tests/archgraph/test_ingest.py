from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import aiosqlite
import pytest

from archivum.archgraph.ingest import changed_files, ingest_repo, prune_dangling
from archivum.archgraph.mapper import CandidateEntity, Provenance


class FakeValidationLayer:
    """Local copy of FakeValidationLayer — mirrors conftest exactly."""

    _VALID_METHODS = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}

    def __init__(self) -> None:
        self.accepted: list[object] = []
        self.rejected: list[object] = []

    def validate_batch(self, candidates: list) -> None:
        for candidate in candidates:
            provenance = getattr(candidate, "provenance", [])
            method = getattr(candidate, "extraction_method", "")
            if provenance and method in self._VALID_METHODS:
                self.accepted.append(candidate)
            else:
                self.rejected.append(candidate)


@pytest.fixture
async def lexical_conn(tmp_path):
    async with aiosqlite.connect(tmp_path / "lexical.db") as conn:
        yield conn


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def shared_cache_dir(tmp_path):
    d = tmp_path / "shared_cache"
    d.mkdir()
    return d


async def test_full_ingest_lands_in_l1(git_repo, cache_dir, tmp_path, fake_validation):
    async with aiosqlite.connect(tmp_path / "lexical.db") as conn:
        report = await ingest_repo(
            git_repo,
            scope="repo:test",
            cache_dir=cache_dir,
            validation=fake_validation,
            lexical_conn=conn,
        )

    assert report.nodes > 0
    names = {c.name for c in fake_validation.accepted if hasattr(c, "name")}
    assert "Calculator" in names, f"Expected 'Calculator' in accepted names, got: {names}"


async def test_second_run_uses_cache(git_repo, shared_cache_dir, tmp_path):
    # First run
    fv1 = FakeValidationLayer()
    async with aiosqlite.connect(tmp_path / "lex1.db") as conn:
        report1 = await ingest_repo(
            git_repo,
            scope="repo:test",
            cache_dir=shared_cache_dir,
            validation=fv1,
            lexical_conn=conn,
        )
    assert report1.files > 0

    # Second run with same cache_dir
    fv2 = FakeValidationLayer()
    async with aiosqlite.connect(tmp_path / "lex2.db") as conn:
        report2 = await ingest_repo(
            git_repo,
            scope="repo:test",
            cache_dir=shared_cache_dir,
            validation=fv2,
            lexical_conn=conn,
        )

    assert report2.files > 0
    assert report2.cache_hits == report2.files, (
        f"Expected all {report2.files} files to be cache hits, got {report2.cache_hits}"
    )


async def test_all_relationships_have_method(git_repo, cache_dir, tmp_path, fake_validation):
    valid_methods = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
    async with aiosqlite.connect(tmp_path / "lexical.db") as conn:
        await ingest_repo(
            git_repo,
            scope="repo:test",
            cache_dir=cache_dir,
            validation=fake_validation,
            lexical_conn=conn,
        )

    from archivum.archgraph.mapper import CandidateRelationship

    rels = [c for c in fake_validation.accepted if isinstance(c, CandidateRelationship)]
    assert len(rels) > 0, "Expected at least one accepted relationship"
    for rel in rels:
        assert rel.extraction_method in valid_methods, (
            f"Relationship {rel.id!r} has invalid method {rel.extraction_method!r}"
        )


# ---------------------------------------------------------------------------
# Task 14 — incremental re-index + dangling pruning
# ---------------------------------------------------------------------------

def _git_env() -> dict:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=_git_env()
    )
    return result.stdout.strip()


def _make_two_file_repo(tmp_path: Path) -> Path:
    """Create a git repo with two Python files."""
    repo = tmp_path / "two_file_repo"
    repo.mkdir()
    (repo / "calc.py").write_text(
        "class Calc:\n    def add(self, a, b):\n        return a + b\n"
    )
    (repo / "utils.py").write_text(
        "class Helper:\n    def greet(self, name):\n        return f'hi {name}'\n"
    )
    env = _git_env()
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env)
    return repo


async def test_update_reextracts_only_changed(tmp_path, fake_validation):
    """Incremental update only processes the changed file and finds new symbols."""
    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text(
        "class Calculator:\n    def add(self, a, b):\n        return a + b\n"
    )
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=_git_env())

    first_sha = _run_git(["rev-parse", "HEAD"], repo)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Full ingest at first commit
    fv1 = FakeValidationLayer()
    async with aiosqlite.connect(tmp_path / "lex1.db") as conn:
        await ingest_repo(
            repo,
            scope="repo:test",
            cache_dir=cache_dir,
            validation=fv1,
            lexical_conn=conn,
        )

    # Modify calc.py and commit
    with open(repo / "calc.py", "a") as f:
        f.write("\ndef new_function():\n    return 42\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=_git_env())
    subprocess.run(["git", "commit", "-q", "-m", "add new_function"], cwd=repo, check=True, env=_git_env())

    # Incremental update
    fv2 = FakeValidationLayer()
    async with aiosqlite.connect(tmp_path / "lex2.db") as conn:
        report = await ingest_repo(
            repo,
            scope="repo:test",
            cache_dir=cache_dir,
            validation=fv2,
            lexical_conn=conn,
            update=True,
            since_sha=first_sha,
        )

    # Only calc.py was changed — exactly 1 file processed
    assert report.files == 1, f"Expected 1 changed file processed, got {report.files}"
    names = {c.name for c in fv2.accepted if hasattr(c, "name")}
    assert "new_function" in names, f"Expected 'new_function' in accepted names, got: {names}"


async def test_update_prunes_deleted_file(tmp_path, fake_validation):
    """After deleting a file and running update, that file's objects are pruned."""
    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo = _make_two_file_repo(tmp_path)
    first_sha = _run_git(["rev-parse", "HEAD"], repo)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    # Full ingest
    fv1 = FakeValidationLayer()
    async with aiosqlite.connect(tmp_path / "lex1.db") as conn:
        report1 = await ingest_repo(
            repo,
            scope="repo:test",
            cache_dir=cache_dir,
            validation=fv1,
            lexical_conn=conn,
        )
    assert report1.files == 2

    # Delete utils.py and commit
    (repo / "utils.py").unlink()
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=_git_env())
    subprocess.run(["git", "commit", "-q", "-m", "delete utils.py"], cwd=repo, check=True, env=_git_env())

    # Incremental update — utils.py objects should be pruned
    fv2 = FakeValidationLayer()
    async with aiosqlite.connect(tmp_path / "lex2.db") as conn:
        report2 = await ingest_repo(
            repo,
            scope="repo:test",
            cache_dir=cache_dir,
            validation=fv2,
            lexical_conn=conn,
            update=True,
            since_sha=first_sha,
        )

    names = {c.name for c in fv2.accepted if hasattr(c, "name")}
    assert "Helper" not in names, f"'Helper' from deleted utils.py should be pruned, got: {names}"


async def test_cross_file_edge_provenance_is_file_addressable_and_prunable(tmp_path, fake_validation):
    """A cross-file INFERRED edge must be anchored to its source FILE (not a
    synthetic repo-level key) so prune_dangling can reach it when that file is
    deleted — otherwise the edge would dangle forever after a file removal."""
    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo = tmp_path / "xrepo"
    repo.mkdir()
    (repo / "b.py").write_text("def helper():\n    return 1\n")
    (repo / "a.py").write_text("from b import helper\n\ndef run():\n    return helper()\n")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=_git_env())

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    fv = FakeValidationLayer()
    async with aiosqlite.connect(tmp_path / "lex.db") as conn:
        await ingest_repo(
            repo, scope="repo:test", cache_dir=cache_dir, validation=fv, lexical_conn=conn
        )

    inferred = [
        c for c in fv.accepted
        if getattr(c, "extraction_method", None) == "INFERRED" and hasattr(c, "src_id")
    ]
    assert inferred, "expected a cross-file INFERRED relationship (a.run -> b.helper)"
    a_py = str(repo / "a.py")
    for c in inferred:
        chunk_ids = {p.chunk_id for p in c.provenance}
        # file-addressable, NOT the old synthetic "cross_file:..." key
        assert all(not cid.startswith("cross_file:") for cid in chunk_ids), chunk_ids
        assert any(cid.endswith("a.py") or cid.endswith("b.py") for cid in chunk_ids), chunk_ids

    # Deleting a.py must let prune_dangling remove its cross-file edge.
    kept, pruned = prune_dangling(fv.accepted, {a_py})
    assert pruned >= 1
    stale = [
        c for c in kept
        if getattr(c, "extraction_method", None) == "INFERRED"
        and any(p.chunk_id == a_py for p in getattr(c, "provenance", []))
    ]
    assert not stale, f"cross-file edge from deleted a.py should be prunable, got {stale}"


def test_prune_dangling_pure():
    """Unit-test prune_dangling with hand-built candidates."""
    deleted = {"/repo/dead.py"}

    # Candidate whose only provenance is from deleted file -> pruned
    dead_prov = Provenance(chunk_id="/repo/dead.py", span="L1", extraction_method="EXTRACTED")
    dead_candidate = CandidateEntity(
        id="dead_1",
        kind="function",
        name="dead_func",
        scope="repo:test",
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[dead_prov],
    )

    # Candidate whose provenance is from live file -> kept
    live_prov = Provenance(chunk_id="/repo/live.py", span="L1", extraction_method="EXTRACTED")
    live_candidate = CandidateEntity(
        id="live_1",
        kind="function",
        name="live_func",
        scope="repo:test",
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[live_prov],
    )

    # Candidate with mixed provenance (one dead, one live) -> kept
    mixed_candidate = CandidateEntity(
        id="mixed_1",
        kind="function",
        name="mixed_func",
        scope="repo:test",
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[dead_prov, live_prov],
    )

    # Candidate with no provenance -> kept (no evidence to prune)
    no_prov_candidate = CandidateEntity(
        id="noprov_1",
        kind="function",
        name="no_prov_func",
        scope="repo:test",
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[],
    )

    kept, pruned_count = prune_dangling(
        [dead_candidate, live_candidate, mixed_candidate, no_prov_candidate],
        deleted,
    )

    assert pruned_count == 1, f"Expected 1 pruned, got {pruned_count}"
    kept_names = {c.name for c in kept}
    assert "dead_func" not in kept_names, "dead_func should be pruned"
    assert "live_func" in kept_names
    assert "mixed_func" in kept_names
    assert "no_prov_func" in kept_names
