import aiosqlite
import pytest

from archivum.knowledge.models import Citation
from archivum.memory.loadouts import match_score, query_tokens, resolve_loadout
from archivum.memory.registry import MemoryAssetRegistry, init_memory_schema


async def _setup(conn):
    await init_memory_schema(conn)
    registry = MemoryAssetRegistry(conn)
    await registry.upsert_agent(agent_key="coder", wiki_id="default", name="Coder")
    return registry


async def _asset(registry, asset_id, *, name, summary="", status="active", cited=True):
    await registry.register_asset(
        id=asset_id,
        wiki_id="default",
        asset_type="skill",
        layer="L2",
        name=name,
        scope="wiki:default",
        summary=summary,
        citations=(
            [
                Citation(
                    source_id="source:1",
                    chunk_id="chunk:1",
                    span_start=0,
                    span_end=4,
                    quote=name,
                )
            ]
            if cited
            else []
        ),
    )
    if status != "draft":
        await registry.set_status(asset_id, status)


def test_query_tokens_drop_short_noise():
    assert query_tokens("Deploy the DB to k8s") == {"deploy", "the", "k8s"}


def test_match_score_is_zero_without_a_query():
    class _Asset:
        name = "Deploy"
        summary = ""
        body = ""
        tags: list[str] = []

    assert match_score(_Asset(), set()) == 0.0


@pytest.mark.asyncio
async def test_unknown_agent_returns_an_explicit_reason():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _setup(conn)
        package = await resolve_loadout(
            registry, agent_key="ghost", wiki_id="default"
        )
        assert package.entries == []
        assert package.insufficient_evidence is True
        assert "ghost" in package.reason


@pytest.mark.asyncio
async def test_only_active_assets_are_handed_to_an_agent():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _setup(conn)
        await _asset(registry, "memory:skill:draft", name="Draft skill", status="draft")
        await _asset(registry, "memory:skill:live", name="Live skill")
        for asset_id in ("memory:skill:draft", "memory:skill:live"):
            await registry.bind_asset(
                agent_key="coder", wiki_id="default", asset_id=asset_id
            )

        package = await resolve_loadout(registry, agent_key="coder", wiki_id="default")
        assert [entry.asset.id for entry in package.entries] == ["memory:skill:live"]


@pytest.mark.asyncio
async def test_archived_assets_drop_out_of_the_loadout():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _setup(conn)
        await _asset(registry, "memory:skill:live", name="Live skill")
        await registry.bind_asset(
            agent_key="coder", wiki_id="default", asset_id="memory:skill:live"
        )
        await registry.set_status("memory:skill:live", "archived")
        package = await resolve_loadout(registry, agent_key="coder", wiki_id="default")
        assert package.entries == []


@pytest.mark.asyncio
async def test_on_demand_bindings_need_a_matching_query():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _setup(conn)
        await _asset(
            registry,
            "memory:skill:deploy",
            name="Deploy the stack",
            summary="docker compose and caddy",
        )
        await registry.bind_asset(
            agent_key="coder",
            wiki_id="default",
            asset_id="memory:skill:deploy",
            mode="on_demand",
        )

        idle = await resolve_loadout(registry, agent_key="coder", wiki_id="default")
        assert idle.entries == []
        assert "on-demand skipped" in idle.reason

        matched = await resolve_loadout(
            registry, agent_key="coder", wiki_id="default", query="docker deploy"
        )
        assert [entry.asset.id for entry in matched.entries] == ["memory:skill:deploy"]
        assert matched.entries[0].reason.startswith("Query match")


@pytest.mark.asyncio
async def test_entries_are_ordered_by_priority_and_carry_citations():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _setup(conn)
        await _asset(registry, "memory:skill:a", name="A skill")
        await _asset(registry, "memory:skill:b", name="B skill")
        await registry.bind_asset(
            agent_key="coder", wiki_id="default", asset_id="memory:skill:a", priority=50
        )
        await registry.bind_asset(
            agent_key="coder", wiki_id="default", asset_id="memory:skill:b", priority=10
        )

        package = await resolve_loadout(registry, agent_key="coder", wiki_id="default")
        assert [entry.asset.id for entry in package.entries] == [
            "memory:skill:b",
            "memory:skill:a",
        ]
        assert len(package.citations) == 2
        assert package.insufficient_evidence is False


@pytest.mark.asyncio
async def test_uncited_loadout_is_flagged_as_unverified():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _setup(conn)
        await _asset(registry, "memory:skill:a", name="A skill", cited=False)
        await registry.bind_asset(
            agent_key="coder", wiki_id="default", asset_id="memory:skill:a"
        )
        package = await resolve_loadout(registry, agent_key="coder", wiki_id="default")
        assert package.entries
        assert package.insufficient_evidence is True
        assert "unverified" in package.reason


@pytest.mark.asyncio
async def test_limit_bounds_the_returned_entries():
    async with aiosqlite.connect(":memory:") as conn:
        registry = await _setup(conn)
        for index in range(5):
            await _asset(registry, f"memory:skill:{index}", name=f"Skill {index}")
            await registry.bind_asset(
                agent_key="coder",
                wiki_id="default",
                asset_id=f"memory:skill:{index}",
                priority=index,
            )
        package = await resolve_loadout(
            registry, agent_key="coder", wiki_id="default", limit=2
        )
        assert [entry.asset.id for entry in package.entries] == [
            "memory:skill:0",
            "memory:skill:1",
        ]
