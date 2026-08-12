import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.retrieval.context import ContextRequest, build_context_package


@pytest.mark.asyncio
async def test_context_package_returns_bounded_cited_subgraph():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        citation = Citation(source_id="page:alpha", chunk_id="page:alpha", span_start=0, span_end=5, quote="Alpha")
        await repo.upsert_object(KnowledgeObject(id="entity:alpha", kind="entity", label="Alpha", scope="wiki:default", confidence=1.0, extraction_method="EXTRACTED", citations=[citation], properties={}))
        await repo.upsert_object(KnowledgeObject(id="entity:beta", kind="entity", label="Beta", scope="wiki:default", confidence=1.0, extraction_method="EXTRACTED", citations=[citation], properties={}))
        await repo.upsert_relationship(KnowledgeRelationship(id="rel:alpha:beta", src_id="entity:alpha", dst_id="entity:beta", rel_type="related_to", scope="wiki:default", confidence=0.8, extraction_method="INFERRED", citations=[citation], properties={}))
        package = await build_context_package(repo, ContextRequest(query="Alpha", scope="wiki:default", max_nodes=2))
        assert package.insufficient_evidence is False
        assert [n.id for n in package.nodes] == ["entity:alpha", "entity:beta"]
        assert package.edges[0].extraction_method == "INFERRED"


@pytest.mark.asyncio
async def test_context_package_defaults_to_self_when_no_seed_ids_are_given():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        root = await ensure_personal_root(repo, display_name="Me", wiki_id="default")
        citation = Citation(source_id="page:project", chunk_id="page:project", span_start=0, span_end=7, quote="Project")
        await repo.upsert_object(KnowledgeObject(id="project:one", kind="project", label="Project One", scope="wiki:default", confidence=1.0, extraction_method="USER_AUTHORED", citations=[citation], properties={}))
        await link_to_self(repo, "project:one", "owns_project", citation=citation)
        package = await build_context_package(repo, ContextRequest(query="", scope="wiki:default", max_nodes=2))
        assert package.seeds == [SELF_ID]
        assert package.nodes[0].id == root.id
