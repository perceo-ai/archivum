import aiosqlite
import pytest

from archivum.knowledge.models import Citation
from archivum.memory.registry import MemoryAssetRegistry, init_memory_schema


def _citation(quote: str = "evidence") -> Citation:
    return Citation(
        source_id="source:1",
        chunk_id="chunk:1",
        span_start=0,
        span_end=len(quote),
        quote=quote,
    )


async def _registry(conn):
    await init_memory_schema(conn)
    return MemoryAssetRegistry(conn)


async def _register(registry, **overrides):
    payload = {
        "id": "memory:skill:deploy",
        "wiki_id": "default",
        "asset_type": "skill",
        "layer": "L2",
        "name": "Deploy the stack",
        "scope": "wiki:default",
        "summary": "3 steps",
        "body": "# Deploy",
        "citations": [_citation()],
    }
    payload.update(overrides)
    return await registry.register_asset(**payload)


@pytest.mark.asyncio
async def test_register_round_trips_every_governance_field():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        asset = await _register(registry, tags=["skill"], metadata={"tool_calls": 4})
        loaded = await registry.get_asset("memory:skill:deploy")
        assert loaded == asset
        assert loaded.owner == "person:self"
        assert loaded.status == "draft"
        assert loaded.visibility == "private"
        assert loaded.version == 1
        assert loaded.metadata == {"tool_calls": 4}
        assert loaded.citations[0].quote == "evidence"


@pytest.mark.asyncio
async def test_version_bumps_only_when_content_changes():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        await _register(registry)
        unchanged = await _register(registry)
        assert unchanged.version == 1

        changed = await _register(registry, body="# Deploy v2")
        assert changed.version == 2
        versions = await registry.list_versions("memory:skill:deploy")
        assert [v.version for v in versions] == [2, 1]
        assert versions[1].body == "# Deploy"


@pytest.mark.asyncio
async def test_content_edit_does_not_silently_reactivate_an_archived_asset():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        await _register(registry)
        await registry.set_status("memory:skill:deploy", "archived")
        edited = await _register(registry, body="# Deploy v2", status="active")
        assert edited.status == "archived"


@pytest.mark.asyncio
async def test_status_and_visibility_transitions():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        await _register(registry)
        activated = await registry.set_status("memory:skill:deploy", "active")
        assert activated.status == "active"
        assert activated.version == 1
        shared = await registry.set_visibility("memory:skill:deploy", "shared")
        assert shared.visibility == "shared"
        # The current snapshot tracks the governance state it was activated at.
        versions = await registry.list_versions("memory:skill:deploy")
        assert versions[0].status == "active"

        with pytest.raises(KeyError):
            await registry.set_status("memory:skill:missing", "active")


@pytest.mark.asyncio
async def test_invalid_enum_values_are_rejected():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        with pytest.raises(ValueError, match="asset type"):
            await _register(registry, asset_type="nonsense")
        with pytest.raises(ValueError, match="layer"):
            await _register(registry, layer="L9")
        with pytest.raises(ValueError, match="status"):
            await _register(registry, status="maybe")
        with pytest.raises(ValueError, match="visibility"):
            await _register(registry, visibility="everyone")


@pytest.mark.asyncio
async def test_list_assets_filters_by_wiki_type_and_status():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        await _register(registry)
        await _register(registry, id="memory:chat:s1", asset_type="chat", layer="L1")
        await _register(
            registry, id="memory:skill:other", wiki_id="other", scope="wiki:other"
        )
        await registry.set_status("memory:chat:s1", "active")

        assert [a.id for a in await registry.list_assets(wiki_id="other")] == [
            "memory:skill:other"
        ]
        skills = await registry.list_assets(wiki_id="default", asset_type="skill")
        assert [a.id for a in skills] == ["memory:skill:deploy"]
        active = await registry.list_assets(wiki_id="default", status="active")
        assert [a.id for a in active] == ["memory:chat:s1"]


@pytest.mark.asyncio
async def test_binding_requires_an_existing_agent_and_asset():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        await _register(registry)
        with pytest.raises(KeyError, match="Agent"):
            await registry.bind_asset(
                agent_key="ghost", wiki_id="default", asset_id="memory:skill:deploy"
            )
        await registry.upsert_agent(agent_key="coder", wiki_id="default", name="Coder")
        with pytest.raises(KeyError, match="asset"):
            await registry.bind_asset(
                agent_key="coder", wiki_id="default", asset_id="memory:skill:ghost"
            )
        with pytest.raises(ValueError, match="binding mode"):
            await registry.bind_asset(
                agent_key="coder",
                wiki_id="default",
                asset_id="memory:skill:deploy",
                mode="sometimes",
            )


@pytest.mark.asyncio
async def test_bindings_are_upserted_and_removable():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        await _register(registry)
        await registry.upsert_agent(agent_key="coder", wiki_id="default", name="Coder")
        await registry.bind_asset(
            agent_key="coder", wiki_id="default", asset_id="memory:skill:deploy"
        )
        await registry.bind_asset(
            agent_key="coder",
            wiki_id="default",
            asset_id="memory:skill:deploy",
            mode="on_demand",
            priority=5,
        )
        bindings = await registry.list_bindings(agent_key="coder", wiki_id="default")
        assert [(b.mode, b.priority) for b in bindings] == [("on_demand", 5)]
        assert await registry.unbind_asset(
            agent_key="coder", wiki_id="default", asset_id="memory:skill:deploy"
        )
        assert await registry.list_bindings(agent_key="coder", wiki_id="default") == []


@pytest.mark.asyncio
async def test_deleting_an_asset_clears_versions_and_bindings():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _registry(conn)
        await _register(registry)
        await registry.upsert_agent(agent_key="coder", wiki_id="default", name="Coder")
        await registry.bind_asset(
            agent_key="coder", wiki_id="default", asset_id="memory:skill:deploy"
        )
        assert await registry.delete_asset("memory:skill:deploy")
        assert await registry.get_asset("memory:skill:deploy") is None
        assert await registry.list_versions("memory:skill:deploy") == []
        assert await registry.list_bindings(agent_key="coder", wiki_id="default") == []
