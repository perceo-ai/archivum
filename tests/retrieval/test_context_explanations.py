import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.retrieval.context import ContextRequest, build_context_package


def _citation(value: str) -> Citation:
    return Citation(
        source_id=f"source:{value}",
        chunk_id=f"chunk:{value}",
        span_start=0,
        span_end=len(value),
        quote=value,
    )


def _object(object_id: str, label: str, *, stale=False) -> KnowledgeObject:
    return KnowledgeObject(
        id=object_id,
        kind="memory",
        label=label,
        scope="person:self",
        confidence=0.9,
        extraction_method="EXTRACTED",
        citations=[_citation(label)],
        properties={"stale": stale} if stale else {},
    )


@pytest.mark.asyncio
async def test_context_package_explains_inclusions_exclusions_and_staleness():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("memory:alpha", "Alpha"))
        await repo.upsert_object(_object("memory:beta", "Beta", stale=True))
        await repo.upsert_object(_object("memory:gamma", "Gamma"))

        package = await build_context_package(
            repo,
            ContextRequest(
                query="",
                scope="person:self",
                seed_ids=["memory:alpha", "memory:beta", "memory:gamma"],
                max_nodes=2,
                depth=0,
            ),
        )

        assert package.inclusion_explanations["memory:alpha"].startswith("Included")
        assert package.inclusion_explanations["memory:beta"].startswith("Included")
        assert package.exclusion_explanations["memory:gamma"] == "Excluded by max_nodes budget."
        assert package.staleness_warnings["memory:beta"] == "Marked stale by source metadata."
