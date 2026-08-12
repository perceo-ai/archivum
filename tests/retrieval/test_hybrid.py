import pytest

from archivum.knowledge.models import Citation, ContextNode, ContextPackage
from archivum.retrieval import hybrid
from archivum.retrieval.hybrid import fuse_ranked_hits


def _citation(value: str) -> Citation:
    return Citation(
        source_id=f"source:{value}",
        chunk_id=f"chunk:{value}",
        span_start=0,
        span_end=len(value),
        quote=value,
    )


def test_fuse_ranked_hits_prefers_items_found_by_multiple_channels():
    hits = fuse_ranked_hits(
        keyword=[("page:a", 0.7), ("page:b", 0.9)],
        vector=[("page:a", 0.8), ("page:c", 0.95)],
        graph=[("page:a", 0.4)],
        limit=2,
    )

    assert [hit.id for hit in hits] == ["page:a", "page:b"]
    assert hits[0].score > hits[1].score


@pytest.mark.asyncio
async def test_hybrid_retrieve_reserves_graph_neighbor_capacity_and_enriches_hits(
    monkeypatch,
):
    vector_rows = [
        {"slug": f"page-{index}", "title": f"Page {index}", "excerpt": "excerpt", "score": 0.9}
        for index in range(6)
    ]
    captured = {}

    async def fake_vector(*args, **kwargs):
        return vector_rows

    async def fake_keyword(*args, **kwargs):
        return []

    class Connection:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    async def fake_context_package(repo, request):
        captured["request"] = request
        return ContextPackage(
            query=request.query,
            seeds=request.seed_ids or [],
            nodes=[
                ContextNode(
                    id="page:isolated:page-0",
                    label="Page 0",
                    node_type="page",
                    citations=[_citation("page-0")],
                ),
                ContextNode(
                    id="entity:neighbor",
                    label="Neighbor",
                    node_type="entity",
                    citations=[_citation("neighbor evidence")],
                ),
            ],
            edges=[],
            citations=[_citation("neighbor evidence")],
            insufficient_evidence=False,
            reason=None,
        )

    monkeypatch.setattr(hybrid, "_vector_rows", fake_vector)
    monkeypatch.setattr(hybrid, "_keyword_rows", fake_keyword)
    monkeypatch.setattr(hybrid.sqlite, "get_db", lambda: Connection())
    monkeypatch.setattr(hybrid, "build_context_package", fake_context_package)

    hits = await hybrid.hybrid_retrieve("neighbor", "isolated", limit=10)

    request = captured["request"]
    assert request.scope == "wiki:isolated"
    assert request.max_nodes == 10
    assert len(request.seed_ids or []) == 6
    neighbor = next(hit for hit in hits if hit.id == "entity:neighbor")
    assert neighbor.source == "graph"
    assert neighbor.citation.quote == "neighbor evidence"
    page = next(hit for hit in hits if hit.id == "page:isolated:page-0")
    assert page.citation.quote == "excerpt"
