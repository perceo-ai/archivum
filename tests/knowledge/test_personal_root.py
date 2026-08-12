import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


@pytest.mark.asyncio
async def test_ensure_personal_root_creates_me_node():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        root = await ensure_personal_root(repo, display_name="Pranav", wiki_id="default")
        assert root.id == SELF_ID
        assert root.kind == "person"
        assert root.label == "Pranav"
        assert root.properties["is_owner"] is True


@pytest.mark.asyncio
async def test_link_project_to_self():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await ensure_personal_root(repo, display_name="Me", wiki_id="default")
        await repo.upsert_object(KnowledgeObject(
            id="project:archivum",
            kind="project",
            label="Archivum",
            scope="wiki:default",
            confidence=1.0,
            extraction_method="USER_AUTHORED",
            citations=[Citation(source_id="page:archivum", chunk_id="page:archivum", span_start=0, span_end=8, quote="Archivum")],
            properties={},
        ))
        rel = await link_to_self(
            repo,
            "project:archivum",
            "owns_project",
            citation=Citation(source_id="page:archivum", chunk_id="page:archivum", span_start=0, span_end=8, quote="Archivum"),
        )
        assert rel.src_id == SELF_ID
        assert rel.dst_id == "project:archivum"
        assert rel.rel_type == "owns_project"
