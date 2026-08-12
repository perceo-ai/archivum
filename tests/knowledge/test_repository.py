import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


@pytest.mark.asyncio
async def test_upsert_and_get_object_round_trip():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        obj = KnowledgeObject(
            id="entity:alice",
            kind="entity",
            label="Alice",
            scope="wiki:default",
            confidence=1.0,
            extraction_method="USER_AUTHORED",
            citations=[Citation(source_id="page:alice", chunk_id="page:alice", span_start=0, span_end=5, quote="Alice")],
            properties={"entity_type": "person"},
        )
        await repo.upsert_object(obj)
        loaded = await repo.get_object("entity:alice")
        assert loaded == obj


@pytest.mark.asyncio
async def test_relationship_query_by_node():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        rel = KnowledgeRelationship(
            id="rel:a:b",
            src_id="entity:a",
            dst_id="entity:b",
            rel_type="related_to",
            scope="wiki:default",
            confidence=0.7,
            extraction_method="INFERRED",
            citations=[Citation(source_id="page:a", chunk_id="page:a", span_start=0, span_end=10, quote="A met B")],
            properties={},
        )
        await repo.upsert_relationship(rel)
        rows = await repo.list_relationships(node_id="entity:a")
        assert [r.id for r in rows] == ["rel:a:b"]
