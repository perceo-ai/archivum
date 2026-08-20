"""A source could not answer for its own output.

`sources` has no page_slug and `pages` has no source_id, so the two looked
unrelated — even though ingest cites the source on every record it derives.
"""

from unittest.mock import AsyncMock, patch

import pytest_asyncio
from fastapi.testclient import TestClient

import archivum.db.sqlite as sqlite_mod
from archivum.auth import CurrentUser, get_current_user, require_writer
from archivum.config import Settings, get_settings
from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.repository import KnowledgeRepository
from archivum.main import create_app


@pytest_asyncio.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)

    with (
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
    ):
        app = create_app()

    owner = CurrentUser(username="owner", role="owner", wiki_id="default")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[require_writer] = lambda: owner
    app.dependency_overrides[get_settings] = lambda: settings

    yield TestClient(app, raise_server_exceptions=True)


def cite(source_id: str) -> Citation:
    return Citation(
        source_id=source_id,
        chunk_id=f"{source_id}:chunk:0",
        span_start=None,
        span_end=None,
        quote=None,
    )


async def test_a_source_can_answer_for_what_it_produced(env):
    source_id = "source:default:paper.pdf"
    scope = "wiki:default"

    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(
            KnowledgeObject(
                id=source_id, kind="source", label="paper.pdf", scope=scope,
                confidence=1.0, extraction_method="EXTRACTED",
                citations=[cite(source_id)], properties={},
            )
        )
        for slug in ("topics/a", "topics/b"):
            await repo.upsert_object(
                KnowledgeObject(
                    id=f"page:default:{slug}", kind="page", label=slug, scope=scope,
                    confidence=0.8, extraction_method="EXTRACTED",
                    citations=[cite(source_id)], properties={"slug": slug},
                )
            )
        # A page from a different source must not be swept in.
        await repo.upsert_object(
            KnowledgeObject(
                id="page:default:unrelated", kind="page", label="unrelated", scope=scope,
                confidence=0.8, extraction_method="EXTRACTED",
                citations=[cite("source:default:other.pdf")], properties={"slug": "unrelated"},
            )
        )

    body = env.get(f"/api/sources/{source_id}/derived").json()

    slugs = sorted(r["slug"] for r in body["records"] if r["slug"])
    assert slugs == ["topics/a", "topics/b"]
    assert body["pages"] == 2
    # The source cites itself; it is not its own output.
    assert source_id not in {r["id"] for r in body["records"]}


async def test_a_source_with_no_output_is_not_an_error(env):
    body = env.get("/api/sources/source:default:empty.pdf/derived").json()
    assert body["records"] == []
    assert body["pages"] == 0



async def test_distilling_another_vaults_source_is_a_404(env):
    """`source_id` arrives in the request body, so it is attacker-chosen.

    Distillation reads a source's full text and writes it into memory, so an
    unscoped lookup would let anyone pull another vault's conversation into
    their own memory just by naming its id.
    """
    from archivum.store.models import Source
    from archivum.store.repository import SourceStore
    from archivum.store.source_types import SourceType

    await SourceStore().insert_source(
        Source(
            id="t" * 32, content_hash="h" * 64, version=1,
            source_type=SourceType.CONVERSATION, origin_uri="conversation:x:theirs",
            scope="personal", ingested_at="t", recorded_at="t", valid_from="t",
            valid_to=None, wiki_id="theirs",
        )
    )

    res = env.post("/api/memory/distill", json={"source_id": "t" * 32})
    assert res.status_code == 404
    # The message matters: the source must be invisible, not merely
    # unprocessable. Without the tenancy filter the lookup succeeds and the
    # request fails later with "has no document" — same status, but it has
    # already confirmed the source exists and read its row.
    assert "not found" in res.json()["detail"]["detail"]
