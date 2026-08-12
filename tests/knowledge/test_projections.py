import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.projections import rebuild_knowledge_projections
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


@pytest.mark.asyncio
async def test_projection_excludes_code_objects_from_qdrant(monkeypatch):
    indexed = []

    async def fake_index_page(slug, title, markdown, wiki_id="default"):
        indexed.append(slug)

    monkeypatch.setattr("archivum.knowledge.projections.index_page", fake_index_page)

    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(KnowledgeObject(
            id="symbol:retrieve_code",
            kind="symbol",
            label="retrieve_code",
            scope="repo:test",
            confidence=1.0,
            extraction_method="EXTRACTED",
            citations=[Citation(source_id="repo:test", chunk_id="file:a.py", span_start=0, span_end=10, quote="def retrieve_code")],
            properties={},
        ))
        report = await rebuild_knowledge_projections(repo, wiki_id="default")
        assert report.qdrant_indexed == 0
        assert indexed == []
