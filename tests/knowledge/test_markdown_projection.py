import aiosqlite
import pytest

from archivum.knowledge.personal_root import SELF_ID
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.pages_to_knowledge import (
    remove_page_from_knowledge,
    rename_page_in_knowledge,
    sync_page_to_knowledge,
)


@pytest.mark.asyncio
async def test_markdown_page_becomes_user_authored_knowledge_object():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)

        await sync_page_to_knowledge(
            repo, slug="alpha", title="Alpha", markdown="See [[Beta]].", wiki_id="default"
        )

        obj = await repo.get_object("page:default:alpha")
        assert obj is not None
        assert obj.kind == "page"
        assert obj.extraction_method == "USER_AUTHORED"


@pytest.mark.asyncio
async def test_wikilinks_become_user_authored_relationships():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)

        await sync_page_to_knowledge(
            repo,
            slug="alpha",
            title="Alpha",
            markdown="See [[Beta Page|Beta]].",
            wiki_id="default",
        )

        rels = await repo.list_relationships(node_id="page:default:alpha")
        references = [rel for rel in rels if rel.src_id == "page:default:alpha"]
        assert len(references) == 1
        assert references[0].dst_id == "page:default:beta-page"
        assert references[0].rel_type == "references"
        assert references[0].extraction_method == "USER_AUTHORED"


@pytest.mark.asyncio
async def test_markdown_page_links_back_to_self_as_authored_thought():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)

        await sync_page_to_knowledge(
            repo,
            slug="morning-note",
            title="Morning Note",
            markdown="Thinking about focus.",
            wiki_id="default",
        )

        rels = await repo.list_relationships(node_id=SELF_ID)
        assert any(
            rel.dst_id == "page:default:morning-note" and rel.rel_type == "authored_thought"
            for rel in rels
        )


@pytest.mark.asyncio
async def test_project_page_links_back_to_self_as_owned_project():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)

        await sync_page_to_knowledge(
            repo,
            slug="archivum",
            title="Archivum",
            markdown="---\ntype: project\n---\n\n# Archivum\n",
            wiki_id="default",
        )

        rels = await repo.list_relationships(node_id=SELF_ID)
        assert any(
            rel.dst_id == "page:default:archivum" and rel.rel_type == "owns_project"
            for rel in rels
        )


@pytest.mark.asyncio
async def test_sync_reconciles_stale_wikilinks_and_self_relationship_type():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)

        await sync_page_to_knowledge(
            repo,
            slug="alpha",
            title="Alpha",
            markdown="See [[Beta]].",
            wiki_id="default",
        )
        await sync_page_to_knowledge(
            repo,
            slug="alpha",
            title="Alpha",
            markdown="---\ntype: project\n---\n\nSee [[Gamma]].",
            wiki_id="default",
        )

        rels = await repo.list_relationships(node_id="page:default:alpha")
        assert {(rel.rel_type, rel.dst_id) for rel in rels} == {
            ("owns_project", "page:default:alpha"),
            ("references", "page:default:gamma"),
        }


@pytest.mark.asyncio
async def test_rename_replaces_old_canonical_page_id_and_relationships():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)

        await sync_page_to_knowledge(
            repo,
            slug="old-name",
            title="Renamed",
            markdown="See [[Target]].",
            wiki_id="default",
        )
        await rename_page_in_knowledge(
            repo,
            old_slug="old-name",
            new_slug="new-name",
            title="Renamed",
            markdown="See [[Target]].",
            wiki_id="default",
        )

        assert await repo.get_object("page:default:old-name") is None
        assert await repo.get_object("page:default:new-name") is not None
        rels = await repo.list_relationships(node_id=SELF_ID)
        assert any(rel.dst_id == "page:default:new-name" for rel in rels)
        assert not any(rel.dst_id == "page:default:old-name" for rel in rels)


@pytest.mark.asyncio
async def test_delete_removes_page_object_and_incident_relationships():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)

        await sync_page_to_knowledge(
            repo,
            slug="alpha",
            title="Alpha",
            markdown="See [[Beta]].",
            wiki_id="default",
        )
        await sync_page_to_knowledge(
            repo,
            slug="source",
            title="Source",
            markdown="See [[Alpha]].",
            wiki_id="default",
        )
        await remove_page_from_knowledge(repo, slug="alpha", wiki_id="default")

        assert await repo.get_object("page:default:alpha") is None
        assert all(
            "page:default:alpha" not in (rel.src_id, rel.dst_id)
            for rel in await repo.list_relationships()
        )
