import aiosqlite
import pytest

from archivum.archgraph.lexical import build_lexical_index
from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.retrieval.context import ContextRequest, build_context_package


def _citation(label: str) -> Citation:
    return Citation(
        source_id=f"page:{label}",
        chunk_id=f"page:{label}",
        span_start=0,
        span_end=len(label),
        quote=label,
    )


def _object(
    object_id: str,
    label: str,
    *,
    scope: str = "wiki:default",
    source_type: str | None = None,
) -> KnowledgeObject:
    return KnowledgeObject(
        id=object_id,
        kind="symbol" if scope.startswith("repo:") else "entity",
        label=label,
        scope=scope,
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=[_citation(label)],
        properties={} if source_type is None else {"source_type": source_type},
    )


def _relationship(
    relationship_id: str,
    src_id: str,
    dst_id: str,
    relation: str,
    *,
    scope: str = "wiki:default",
) -> KnowledgeRelationship:
    return KnowledgeRelationship(
        id=relationship_id,
        src_id=src_id,
        dst_id=dst_id,
        rel_type=relation,
        scope=scope,
        confidence=0.8,
        extraction_method="INFERRED",
        citations=[_citation(relationship_id)],
        properties={},
    )


@pytest.mark.asyncio
async def test_context_package_returns_bounded_cited_subgraph():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("entity:alpha", "Alpha"))
        await repo.upsert_object(_object("entity:beta", "Beta"))
        await repo.upsert_relationship(
            _relationship("rel:alpha:beta", "entity:alpha", "entity:beta", "related_to")
        )

        package = await build_context_package(
            repo, ContextRequest(query="Alpha", scope="wiki:default", max_nodes=2)
        )

        assert package.insufficient_evidence is False
        assert [node.id for node in package.nodes] == ["entity:alpha", "entity:beta"]
        assert package.edges[0].extraction_method == "INFERRED"


@pytest.mark.asyncio
async def test_context_package_defaults_to_self_when_no_seed_ids_are_given():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        root = await ensure_personal_root(repo, display_name="Me", wiki_id="default")
        project = _object("project:one", "Project One")
        await repo.upsert_object(project)
        await link_to_self(repo, project.id, "owns_project", citation=_citation("Project"))

        package = await build_context_package(
            repo, ContextRequest(query="", scope="wiki:default", max_nodes=2)
        )

        assert package.seeds == [SELF_ID]
        assert package.nodes[0].id == root.id


@pytest.mark.asyncio
async def test_context_package_uses_explicit_seed_when_query_has_no_match():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("entity:alpha", "Alpha"))

        package = await build_context_package(
            repo,
            ContextRequest(
                query="missing", scope="wiki:default", seed_ids=["entity:alpha"]
            ),
        )

        assert package.seeds == ["entity:alpha"]
        assert [node.id for node in package.nodes] == ["entity:alpha"]


@pytest.mark.asyncio
async def test_context_package_respects_depth_max_nodes_relations_and_scope():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        for object_id in ("entity:alpha", "entity:beta", "entity:gamma"):
            await repo.upsert_object(_object(object_id, object_id.rsplit(":", 1)[1].title()))
        await repo.upsert_object(_object("entity:outside", "Outside", scope="wiki:other"))
        await repo.upsert_relationship(
            _relationship("rel:a:b", "entity:alpha", "entity:beta", "related_to")
        )
        await repo.upsert_relationship(
            _relationship("rel:b:g", "entity:beta", "entity:gamma", "related_to")
        )
        await repo.upsert_relationship(
            _relationship("rel:a:g", "entity:alpha", "entity:gamma", "mentions")
        )
        await repo.upsert_relationship(
            _relationship(
                "rel:a:outside",
                "entity:alpha",
                "entity:outside",
                "related_to",
                scope="wiki:other",
            )
        )

        depth_zero = await build_context_package(
            repo,
            ContextRequest(
                query="", scope="wiki:default", seed_ids=["entity:alpha"], depth=0
            ),
        )
        bounded = await build_context_package(
            repo,
            ContextRequest(
                query="",
                scope="wiki:default",
                seed_ids=["entity:alpha"],
                max_nodes=2,
                relations=["related_to"],
            ),
        )

        assert [node.id for node in depth_zero.nodes] == ["entity:alpha"]
        assert depth_zero.edges == []
        assert [node.id for node in bounded.nodes] == ["entity:alpha", "entity:beta"]
        assert [(edge.from_id, edge.to_id, edge.relation) for edge in bounded.edges] == [
            ("entity:alpha", "entity:beta", "related_to")
        ]


@pytest.mark.asyncio
async def test_context_package_filters_non_code_source_type_and_declares_no_evidence():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("entity:note", "Shared", source_type="document"))
        await repo.upsert_object(_object("entity:mail", "Shared", source_type="message"))

        filtered = await build_context_package(
            repo,
            ContextRequest(query="Shared", scope="wiki:default", source_type="document"),
        )
        empty = await build_context_package(
            repo, ContextRequest(query="", scope="wiki:missing")
        )

        assert [node.id for node in filtered.nodes] == ["entity:note"]
        assert empty.nodes == []
        assert empty.insufficient_evidence is True
        assert empty.reason is not None


@pytest.mark.asyncio
async def test_source_type_filter_does_not_restore_excluded_personal_root():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await ensure_personal_root(repo, display_name="Me", wiki_id="default")
        await repo.upsert_object(
            _object("entity:note", "Note", source_type="document")
        )

        package = await build_context_package(
            repo,
            ContextRequest(query="", scope="wiki:default", source_type="document"),
        )

        assert package.seeds == []
        assert package.nodes == []
        assert package.insufficient_evidence is True


@pytest.mark.asyncio
async def test_context_package_routes_code_requests_through_lexical_retrieval():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("symbol:runner", "Entrypoint", scope="repo:test"))
        await repo.upsert_object(_object("symbol:helper", "helper", scope="repo:test"))
        await repo.upsert_relationship(
            _relationship(
                "rel:runner:helper",
                "symbol:runner",
                "symbol:helper",
                "calls",
                scope="repo:test",
            )
        )
        await build_lexical_index(
            conn,
            [("symbol:runner", "runner executes"), ("symbol:helper", "helper")],
        )

        package = await build_context_package(
            repo,
            ContextRequest(
                query="runner",
                scope="repo:test",
                source_type="code",
                code_connection=conn,
            ),
        )

        assert package.seeds == ["symbol:runner"]
        assert [node.id for node in package.nodes] == ["symbol:runner", "symbol:helper"]
        assert package.edges[0].relation == "calls"


@pytest.mark.asyncio
async def test_context_package_falls_back_to_canonical_code_context_without_lexical_index():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("symbol:runner", "runner", scope="repo:test"))
        await repo.upsert_object(_object("symbol:helper", "helper", scope="repo:test"))
        await repo.upsert_relationship(
            _relationship(
                "rel:runner:helper",
                "symbol:runner",
                "symbol:helper",
                "calls",
                scope="repo:test",
            )
        )

        package = await build_context_package(
            repo,
            ContextRequest(query="runner", scope="repo:test", source_type="code"),
        )

        assert package.seeds == ["symbol:runner"]
        assert [node.id for node in package.nodes] == ["symbol:runner", "symbol:helper"]
        assert package.edges[0].relation == "calls"


@pytest.mark.asyncio
async def test_canonical_code_fallback_preserves_explicit_seed_ids():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(_object("symbol:runner", "runner", scope="repo:test"))
        await repo.upsert_object(_object("symbol:helper", "helper", scope="repo:test"))

        package = await build_context_package(
            repo,
            ContextRequest(
                query="runner",
                scope="repo:test",
                source_type="code",
                seed_ids=["symbol:helper"],
                max_nodes=1,
            ),
        )

        assert package.seeds == ["symbol:helper"]
        assert [node.id for node in package.nodes] == ["symbol:helper"]
