from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from archivum.archgraph.ingest import ingest_repo


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
