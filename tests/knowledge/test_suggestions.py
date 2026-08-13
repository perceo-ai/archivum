import aiosqlite
import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.knowledge.suggestions import SuggestionRepository, init_suggestion_schema


@pytest.mark.asyncio
async def test_suggestion_can_be_accepted_once():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        suggestion = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Related\n\n- [[Beta]]",
            proposed_objects=[],
            citations=[],
        )
        await repo.accept_suggestion(suggestion.id)
        await repo.accept_suggestion(suggestion.id)
        loaded = await repo.get_suggestion(suggestion.id)
        assert loaded.status == "accepted"


@pytest.mark.asyncio
async def test_init_db_creates_suggestion_table(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db")
    await sqlite_mod.init_db(settings)
    async with aiosqlite.connect(str(settings.db_path)) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("memory_suggestions",),
        ) as cursor:
            assert await cursor.fetchone() == ("memory_suggestions",)


@pytest.mark.asyncio
async def test_suggestion_can_be_rejected():
    async with aiosqlite.connect(":memory:") as conn:
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        suggestion = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Related",
            proposed_objects=[],
            citations=[],
        )
        await repo.reject_suggestion(suggestion.id)
        assert (await repo.get_suggestion(suggestion.id)).status == "rejected"


@pytest.mark.asyncio
async def test_suggestion_supports_review_action_lifecycle_states():
    async with aiosqlite.connect(":memory:") as conn:
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        for action, expected in [
            ("merge", "merged"),
            ("replace", "replaced"),
            ("keep_both", "kept"),
            ("retire", "retired"),
            ("change_scope", "scope_changed"),
            ("change_visibility", "visibility_changed"),
        ]:
            suggestion = await repo.create_suggestion(
                target_id=f"page:default:{action}",
                suggestion_type="memory_atom",
                proposed_markdown=f"## {action}",
                proposed_objects=[],
                citations=[],
            )
            await repo.transition_suggestion(suggestion.id, action)
            assert (await repo.get_suggestion(suggestion.id)).status == expected


@pytest.mark.asyncio
async def test_conflicting_transitions_and_missing_ids_fail():
    async with aiosqlite.connect(":memory:") as conn:
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        suggestion = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Related",
            proposed_objects=[],
            citations=[],
        )
        await repo.accept_suggestion(suggestion.id)
        with pytest.raises(ValueError):
            await repo.reject_suggestion(suggestion.id)
        with pytest.raises(KeyError):
            await repo.accept_suggestion("suggestion:missing")
        with pytest.raises(KeyError):
            await repo.reject_suggestion("suggestion:missing")

        rejected = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Rejected",
            proposed_objects=[],
            citations=[],
        )
        await repo.reject_suggestion(rejected.id)
        with pytest.raises(ValueError):
            await repo.accept_suggestion(rejected.id)


@pytest.mark.asyncio
async def test_expire_due_candidates_moves_only_stale_pending_items():
    async with aiosqlite.connect(":memory:") as conn:
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        stale = await repo.create_suggestion(
            target_id="wiki:default",
            suggestion_type="memory_atom",
            proposed_markdown="old",
            proposed_objects=[],
            citations=[],
            expires_at="2026-08-01T00:00:00+00:00",
        )
        fresh = await repo.create_suggestion(
            target_id="wiki:default",
            suggestion_type="memory_atom",
            proposed_markdown="fresh",
            proposed_objects=[],
            citations=[],
            expires_at="2026-09-01T00:00:00+00:00",
        )
        accepted = await repo.create_suggestion(
            target_id="wiki:default",
            suggestion_type="memory_atom",
            proposed_markdown="accepted",
            proposed_objects=[],
            citations=[],
            expires_at="2026-08-01T00:00:00+00:00",
        )
        await repo.accept_suggestion(accepted.id)

        expired = await repo.expire_due_candidates("2026-08-13T00:00:00+00:00")

        assert [item.id for item in expired] == [stale.id]
        assert (await repo.get_suggestion(stale.id)).status == "expired"
        assert (await repo.get_suggestion(fresh.id)).status == "pending"
        assert (await repo.get_suggestion(accepted.id)).status == "accepted"


@pytest.mark.asyncio
async def test_suggestion_payloads_round_trip_as_json():
    async with aiosqlite.connect(":memory:") as conn:
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        objects = [{"id": "entity:beta", "properties": {"score": 0.8}}]
        citations = [
            Citation(
                source_id="source:alpha",
                chunk_id="chunk:alpha:0",
                span_start=2,
                span_end=8,
                quote="Beta",
            ).model_dump()
        ]
        suggestion = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Related",
            proposed_objects=objects,
            citations=citations,
        )
        loaded = await repo.get_suggestion(suggestion.id)
        assert loaded.proposed_objects == objects
        assert loaded.citations == citations


@pytest.mark.asyncio
async def test_suggestion_round_trips_review_card_metadata():
    async with aiosqlite.connect(":memory:") as conn:
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)

        suggestion = await repo.create_suggestion(
            target_id="wiki:default",
            suggestion_type="memory_atom",
            proposed_markdown="Archivum should be human-centered.",
            proposed_objects=[],
            citations=[],
            proposed_scopes=["person:self", "project:archivum"],
            scores={
                "human_relevance": 0.95,
                "future_utility": 0.9,
                "durability": 0.8,
                "specificity": 0.85,
                "novelty": 0.7,
                "evidence_quality": 0.75,
                "compression_ratio": 0.6,
                "risk": 0.1,
            },
            duplicates=["memory:principle:old"],
            conflicts=["memory:decision:projects-root"],
            retention_tier="candidate",
            agent_visibility="on_review",
            rationale="High utility product direction with explicit provenance.",
            estimated_durability="durable",
            expires_at="2026-09-12T00:00:00+00:00",
        )

        loaded = await repo.get_suggestion(suggestion.id)

        assert loaded.proposed_scopes == ["person:self", "project:archivum"]
        assert loaded.scores["future_utility"] == 0.9
        assert loaded.duplicates == ["memory:principle:old"]
        assert loaded.conflicts == ["memory:decision:projects-root"]
        assert loaded.retention_tier == "candidate"
        assert loaded.agent_visibility == "on_review"
        assert loaded.rationale == "High utility product direction with explicit provenance."
        assert loaded.estimated_durability == "durable"
        assert loaded.expires_at == "2026-09-12T00:00:00+00:00"


@pytest.mark.asyncio
async def test_acceptance_only_changes_suggestion_status(tmp_path):
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        canonical = KnowledgeObject(
            id="entity:beta",
            kind="entity",
            label="Beta",
            scope="person:self",
            confidence=1.0,
            extraction_method="USER_AUTHORED",
            citations=[
                Citation(
                    source_id="page:default:alpha",
                    chunk_id="page:default:alpha",
                    span_start=0,
                    span_end=4,
                    quote="Beta",
                )
            ],
            properties={"entity_type": "person"},
        )
        knowledge = KnowledgeRepository(conn)
        page_path = tmp_path / "alpha.md"
        page_path.write_text("# Alpha\n\nOriginal markdown", encoding="utf-8")
        original_markdown = page_path.read_text(encoding="utf-8")
        await knowledge.upsert_object(canonical)
        suggestion = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Related\n\n- [[Beta]]",
            proposed_objects=[{"id": "entity:gamma"}],
            citations=[],
        )
        await repo.accept_suggestion(suggestion.id)
        assert (await repo.get_suggestion(suggestion.id)).status == "accepted"
        assert await knowledge.get_object(canonical.id) == canonical
        assert page_path.read_text(encoding="utf-8") == original_markdown
