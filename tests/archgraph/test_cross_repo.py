from __future__ import annotations

import pytest

from archivum.archgraph.cross_repo import resolve_cross_repo


class FakeL1:
    """In-memory stand-in for PER-317's L1 read API used by archgraph resolvers."""

    def __init__(self, objects=None):
        self._objects = list(objects or [])

    async def list_objects(self, kind=None, scope=None):
        return [
            o
            for o in self._objects
            if (kind is None or o.get("kind") == kind)
            and (scope is None or o.get("scope") == scope)
        ]


async def test_links_same_package_across_repos():
    """Package 'requests' in repo:a and repo:b → one INFERRED CandidateRelationship."""
    l1 = FakeL1([
        {"id": "a-requests", "kind": "package", "scope": "repo:a", "label": "requests"},
        {"id": "b-requests", "kind": "package", "scope": "repo:b", "label": "requests"},
    ])
    results = await resolve_cross_repo(l1)
    assert len(results) == 1
    r = results[0]
    assert r.extraction_method == "INFERRED"
    assert set([r.src_id, r.dst_id]) == {"a-requests", "b-requests"}
    assert r.rel_type in {"same_symbol_as", "depends_on"}


async def test_no_link_within_same_repo():
    """Two 'requests' packages both in repo:a → no cross-repo edge."""
    l1 = FakeL1([
        {"id": "a-requests-1", "kind": "package", "scope": "repo:a", "label": "requests"},
        {"id": "a-requests-2", "kind": "package", "scope": "repo:a", "label": "requests"},
    ])
    results = await resolve_cross_repo(l1)
    assert results == []


async def test_ambiguous_on_common_name():
    """Symbol 'main' (weak kind) across repo:a, repo:b, repo:c (≥3 scopes) → AMBIGUOUS."""
    l1 = FakeL1([
        {"id": "a-main", "kind": "symbol", "scope": "repo:a", "label": "main"},
        {"id": "b-main", "kind": "symbol", "scope": "repo:b", "label": "main"},
        {"id": "c-main", "kind": "symbol", "scope": "repo:c", "label": "main"},
    ])
    results = await resolve_cross_repo(l1)
    assert len(results) >= 1
    for r in results:
        assert r.extraction_method == "AMBIGUOUS"
