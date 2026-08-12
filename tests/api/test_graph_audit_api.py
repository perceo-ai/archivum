from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import archivum.db.sqlite as sqlite_mod
from archivum.auth import CurrentUser, get_current_user
from archivum.config import Settings, get_settings
from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root
from archivum.knowledge.repository import KnowledgeRepository
from archivum.main import create_app


def _citation(source_id="source:1"):
    return Citation(
        source_id=source_id,
        chunk_id="chunk:1",
        span_start=0,
        span_end=8,
        quote="evidence",
    )


def _node(node_id, label):
    return KnowledgeObject(
        id=node_id,
        kind="page",
        label=label,
        scope="wiki:default",
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=[_citation()],
        properties={},
    )


def _edge(src, dst, rel_type="references"):
    return KnowledgeRelationship(
        id=f"rel:{src}:{rel_type}:{dst}",
        src_id=src,
        dst_id=dst,
        rel_type=rel_type,
        scope="wiki:default",
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=[_citation()],
        properties={},
    )


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)

    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        await ensure_personal_root(repo)
        for node_id, label in (
            ("page:default:a1", "Alpha one"),
            ("page:default:a2", "Alpha two"),
            ("page:default:a3", "Alpha three"),
            ("page:default:b1", "Beta one"),
            ("page:default:b2", "Beta two"),
            ("page:default:b3", "Beta three"),
        ):
            await repo.upsert_object(_node(node_id, label))
        for src, dst in (
            ("a1", "a2"),
            ("a2", "a3"),
            ("a3", "a1"),
            ("b1", "b2"),
            ("b2", "b3"),
            ("b3", "b1"),
        ):
            await repo.upsert_relationship(
                _edge(f"page:default:{src}", f"page:default:{dst}")
            )
        await repo.upsert_relationship(
            _edge("page:default:a1", "page:default:b1", rel_type="mentions")
        )

    with (
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
    ):
        app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        username="owner", role="owner", wiki_id="default"
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app, raise_server_exceptions=True)


@pytest.mark.asyncio
async def test_audit_reports_clusters_provenance_and_narrative(client):
    body = client.get("/api/graph/audit").json()
    assert body["scope"] == "wiki:default"
    assert body["node_count"] == 7  # six pages plus the owner root
    assert body["by_extraction_method"]["EXTRACTED"] == 6
    assert body["by_extraction_method"]["USER_AUTHORED"] == 1
    assert body["narrative"]
    assert any("clusters" in line for line in body["narrative"])


@pytest.mark.asyncio
async def test_audit_flags_the_self_cited_owner_root(client):
    body = client.get("/api/graph/audit").json()
    assert SELF_ID in body["self_cited_ids"]


@pytest.mark.asyncio
async def test_communities_endpoint_separates_the_two_lobes(client):
    communities = client.get("/api/graph/communities").json()["communities"]
    grouped = {frozenset(c["member_ids"]) for c in communities}
    assert frozenset({"page:default:a1", "page:default:a2", "page:default:a3"}) in grouped
    assert frozenset({"page:default:b1", "page:default:b2", "page:default:b3"}) in grouped


@pytest.mark.asyncio
async def test_surprising_endpoint_ranks_the_bridge_first(client):
    links = client.get("/api/graph/surprising", params={"limit": 3}).json()["links"]
    assert {links[0]["src_id"], links[0]["dst_id"]} == {
        "page:default:a1",
        "page:default:b1",
    }
    assert links[0]["cross_community"] is True
    assert "linked to" in links[0]["reason"]


@pytest.mark.asyncio
async def test_path_endpoint_walks_across_the_bridge(client):
    body = client.get(
        "/api/graph/path",
        params={"source": "page:default:a2", "target": "page:default:b2"},
    ).json()
    assert body["found"] is True
    assert [step["to_id"] for step in body["steps"]] == [
        "page:default:a1",
        "page:default:b1",
        "page:default:b2",
    ]


@pytest.mark.asyncio
async def test_path_endpoint_404s_on_an_unknown_node(client):
    response = client.get(
        "/api/graph/path", params={"source": "page:default:a1", "target": "page:nope"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_graph_node"


@pytest.mark.asyncio
async def test_path_endpoint_reports_disconnection_without_erroring(client):
    async with sqlite_mod.get_db() as conn:
        await KnowledgeRepository(conn).upsert_object(
            _node("page:default:lonely", "Lonely")
        )
    body = client.get(
        "/api/graph/path",
        params={"source": "page:default:a1", "target": "page:default:lonely"},
    ).json()
    assert body["found"] is False
    assert "No relationship path" in body["reason"]
