import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.memory.registry import MemoryAssetRegistry, init_memory_schema
from archivum.retrieval.context import ContextRequest, build_context_package


def _citation(value: str) -> Citation:
    return Citation(
        source_id=f"source:{value}",
        chunk_id=f"chunk:{value}",
        span_start=0,
        span_end=len(value),
        quote=value,
    )


def _object(object_id: str, label: str, *, review_state: str | None = None) -> KnowledgeObject:
    properties = {"review_state": review_state} if review_state else {}
    return KnowledgeObject(
        id=object_id,
        kind="memory",
        label=label,
        scope="person:self",
        confidence=0.9,
        extraction_method="EXTRACTED",
        citations=[_citation(label)],
        properties=properties,
    )


async def _connect():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_knowledge_schema(conn)
    await init_memory_schema(conn)
    return conn


@pytest.mark.asyncio
async def test_scope_item_budget_bounds_the_context_package():
    conn = await _connect()
    try:
        repo = KnowledgeRepository(conn)
        registry = MemoryAssetRegistry(conn)
        await registry.upsert_scope(
            id="person:self",
            wiki_id="default",
            scope_type="human",
            name="Self",
            budget_tokens=100_000,
            budget_items=1,
        )
        await repo.upsert_object(_object("memory:alpha", "Alpha"))
        await repo.upsert_object(_object("memory:beta", "Beta"))

        package = await build_context_package(
            repo,
            ContextRequest(
                query="",
                scope="person:self",
                seed_ids=["memory:alpha", "memory:beta"],
                max_nodes=10,
                depth=0,
            ),
        )

        assert [node.id for node in package.nodes] == ["memory:alpha"]
        assert (
            package.exclusion_explanations["memory:beta"]
            == "Excluded by scope item budget."
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_scope_token_budget_trims_but_keeps_the_first_node():
    conn = await _connect()
    try:
        repo = KnowledgeRepository(conn)
        registry = MemoryAssetRegistry(conn)
        await registry.upsert_scope(
            id="person:self",
            wiki_id="default",
            scope_type="human",
            name="Self",
            budget_tokens=1,
            budget_items=20,
        )
        await repo.upsert_object(_object("memory:alpha", "Alpha" * 40))
        await repo.upsert_object(_object("memory:beta", "Beta" * 40))

        package = await build_context_package(
            repo,
            ContextRequest(
                query="",
                scope="person:self",
                seed_ids=["memory:alpha", "memory:beta"],
                max_nodes=10,
                depth=0,
            ),
        )

        assert [node.id for node in package.nodes] == ["memory:alpha"]
        assert (
            package.exclusion_explanations["memory:beta"]
            == "Excluded by scope token budget."
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_pending_review_memory_stays_out_of_context_packages():
    conn = await _connect()
    try:
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("memory:accepted", "Accepted", review_state="accepted"))
        await repo.upsert_object(_object("memory:pending", "Pending", review_state="pending"))

        package = await build_context_package(
            repo,
            ContextRequest(
                query="",
                scope="person:self",
                seed_ids=["memory:accepted", "memory:pending"],
                max_nodes=10,
                depth=0,
            ),
        )

        assert [node.id for node in package.nodes] == ["memory:accepted"]
        assert (
            package.exclusion_explanations["memory:pending"]
            == "Excluded pending human review."
        )
    finally:
        await conn.close()
