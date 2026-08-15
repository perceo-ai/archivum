import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.capture.schema import Conversation, Outcome, ToolCall, Turn
from archivum.capture.store import CaptureStore
from archivum.config import Settings
from archivum.knowledge.personal_root import SELF_ID
from archivum.knowledge.repository import KnowledgeRepository
from archivum.knowledge.suggestions import SuggestionRepository
from archivum.memory.distill import PERSONA_ID
from archivum.memory.registry import MemoryAssetRegistry
from archivum.memory.service import (
    DistillationError,
    activate_asset,
    distill_conversation,
    load_conversation,
)
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    store = CaptureStore(
        store=SourceStore(), blob_store=BlobStore(settings.blob_dir), settings=settings
    )
    return settings, store


def _conversation(session_id="s1", *, texts=None, tool_calls=(), outcomes=()):
    texts = texts or ["I prefer uv over pip. Never commit secrets."]
    turns = [Turn(role="user", text=text) for text in texts]
    if tool_calls:
        turns.append(Turn(role="assistant", text="working", tool_calls=tuple(tool_calls)))
    return Conversation(
        session_id=session_id,
        interface="claude_code_native",
        started_at="2026-08-12T00:00:00Z",
        turns=tuple(turns),
        outcomes=tuple(outcomes),
    )


async def _distill(settings, source_id, **kwargs):
    loaded = await load_conversation(source_id, settings=settings)
    async with sqlite_mod.get_db() as conn:
        return await distill_conversation(conn, loaded, wiki_id="default", **kwargs)


@pytest.mark.asyncio
async def test_missing_source_is_reported_not_swallowed(env):
    settings, _ = env
    with pytest.raises(DistillationError, match="not found"):
        await load_conversation("source:nope", settings=settings)


@pytest.mark.asyncio
async def test_distillation_writes_cited_atoms_and_a_chat_asset(env):
    settings, store = env
    result = await store.capture(_conversation())

    report = await _distill(settings, result.source_id)
    assert report.atoms_total == 2
    assert report.atoms_accepted == 2
    assert report.atoms_pending_review == 2

    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        atoms = await repo.list_objects(kind="memory_atom", scope="wiki:default")
        chat = await repo.get_object(f"memory:chat:{result.source_id}")
        owner_edges = await repo.list_relationships(node_id=SELF_ID)
        pending = await SuggestionRepository(conn).list_suggestions(
            target_id="wiki:default"
        )

    assert {atom.properties["atom_type"] for atom in atoms} == {
        "preference",
        "constraint",
    }
    for atom in atoms:
        assert atom.citations and atom.citations[0].quote
        assert atom.extraction_method == "EXTRACTED"
        # Direct canonical writes are provisional until a human reviews them.
        assert atom.properties["review_state"] == "pending"
    assert len(pending) == 2
    assert chat is not None
    assert chat.properties["session_id"] == "s1"
    assert "remembers" in {edge.rel_type for edge in owner_edges}


@pytest.mark.asyncio
async def test_atom_citation_quotes_the_original_transcript(env):
    settings, store = env
    result = await store.capture(_conversation())
    await _distill(settings, result.source_id)

    source = await SourceStore().get_source(result.source_id)
    document = await SourceStore().get_document_for_source(result.source_id)
    chunks = await SourceStore().list_chunks(document.id)
    assert source is not None

    async with sqlite_mod.get_db() as conn:
        atoms = await KnowledgeRepository(conn).list_objects(kind="memory_atom")

    from archivum.capture.canonical import from_canonical_bytes
    from archivum.capture.transcript import render_transcript

    text, _ = render_transcript(from_canonical_bytes(BlobStore(settings.blob_dir).get(source.content_hash)))
    chunk_ids = {chunk.id for chunk in chunks}
    for atom in atoms:
        citation = atom.citations[0]
        assert citation.chunk_id in chunk_ids
        assert text[citation.span_start : citation.span_end] == citation.quote


@pytest.mark.asyncio
async def test_weak_atoms_go_to_review_instead_of_canonical_memory(env):
    settings, store = env
    result = await store.capture(
        _conversation(texts=["I think I prefer uv over pip."])
    )
    report = await _distill(settings, result.source_id)

    assert report.atoms_accepted == 0
    assert report.atoms_pending_review == 1
    async with sqlite_mod.get_db() as conn:
        pending = await SuggestionRepository(conn).list_suggestions(
            target_id="wiki:default"
        )
        atoms = await KnowledgeRepository(conn).list_objects(kind="memory_atom")
    assert atoms == []
    assert [s.suggestion_type for s in pending] == ["memory_atom"]
    assert pending[0].citations[0]["quote"] == "I think I prefer uv over pip."


@pytest.mark.asyncio
async def test_distilled_assets_start_as_drafts_pending_review(env):
    settings, store = env
    result = await store.capture(_conversation())
    report = await _distill(settings, result.source_id, scenario_key="archivum")

    async with sqlite_mod.get_db() as conn:
        registry = MemoryAssetRegistry(conn)
        assets = [await registry.get_asset(asset_id) for asset_id in report.asset_ids]
    # Nothing distillation produces is agent-loadable until a human activates it.
    assert assets and all(asset.status == "draft" for asset in assets)
    assert all(asset.approved_by is None for asset in assets)


@pytest.mark.asyncio
async def test_reviewed_atoms_are_not_suggested_again(env):
    settings, store = env
    result = await store.capture(_conversation(session_id="s1"))
    await _distill(settings, result.source_id)

    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        suggestions = SuggestionRepository(conn)
        for suggestion in await suggestions.list_suggestions(target_id="wiki:default"):
            await suggestions.accept_suggestion(suggestion.id)
        # Simulate the review effect marking the canonical atom as accepted.
        for atom in await repo.list_objects(kind="memory_atom"):
            atom.properties["review_state"] = "accepted"
            await repo.upsert_object(atom)

    second = await store.capture(_conversation(session_id="s2"))
    report = await _distill(settings, second.source_id)

    assert report.atoms_pending_review == 0
    async with sqlite_mod.get_db() as conn:
        pending = await SuggestionRepository(conn).list_suggestions(
            target_id="wiki:default"
        )
        atoms = await KnowledgeRepository(conn).list_objects(kind="memory_atom")
    assert pending == []
    assert all(atom.properties["review_state"] == "accepted" for atom in atoms)


@pytest.mark.asyncio
async def test_derived_memory_stays_out_of_context_until_activated(env):
    from archivum.retrieval.context import ContextRequest, build_context_package

    settings, store = env
    result = await store.capture(_conversation())
    report = await _distill(settings, result.source_id, scenario_key="archivum")
    chat_id = f"memory:chat:{result.source_id}"

    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        request = ContextRequest(
            query="",
            scope="wiki:default",
            wiki_id="default",
            seed_ids=[chat_id, report.scenario_id],
            max_nodes=20,
            depth=0,
        )
        before = await build_context_package(repo, request)
        await activate_asset(conn, repo, chat_id, approved_by="owner")
        after = await build_context_package(repo, request)

    assert chat_id not in {node.id for node in before.nodes}
    assert before.exclusion_explanations[chat_id] == "Excluded pending human review."
    assert chat_id in {node.id for node in after.nodes}
    # The scenario is still unreviewed and stays excluded.
    assert report.scenario_id not in {node.id for node in after.nodes}


@pytest.mark.asyncio
async def test_contradicting_capture_flags_a_conflict_review_card(env):
    settings, store = env
    first = await store.capture(
        _conversation(session_id="s1", texts=["I always use tabs for indentation."])
    )
    await _distill(settings, first.source_id)

    second = await store.capture(
        _conversation(session_id="s2", texts=["I never use tabs for indentation."])
    )
    report = await _distill(settings, second.source_id)

    assert report.conflicts_flagged == 1
    async with sqlite_mod.get_db() as conn:
        pending = await SuggestionRepository(conn).list_suggestions(
            target_id="wiki:default"
        )
    conflicted = [s for s in pending if s.conflicts]
    assert len(conflicted) == 1
    assert conflicted[0].conflicts[0].startswith("memory:atom:")


@pytest.mark.asyncio
async def test_report_counts_scanned_sentences(env):
    settings, store = env
    result = await store.capture(_conversation())
    report = await _distill(settings, result.source_id)
    # "I prefer uv over pip." and "Never commit secrets." are two sentences.
    assert report.sentences_scanned == 2


@pytest.mark.asyncio
async def test_llm_evaluation_types_atoms_and_routes_proposals_to_review(
    env, monkeypatch
):
    from unittest.mock import AsyncMock

    from archivum.memory import service as service_mod
    from archivum.memory.evaluator import (
        AtomEvaluation,
        EvaluationResult,
        ProposedAtom,
    )

    settings, store = env
    result = await store.capture(_conversation())
    evaluation = EvaluationResult(
        evaluations={
            0: AtomEvaluation(
                keep=True,
                semantic_type="preference",
                scores={"human_relevance": 0.9, "durability": 0.9},
                rationale="Restated tooling preference.",
                durability_estimate="long",
            )
        },
        proposed=[
            ProposedAtom(
                text="Secret hygiene is a hard rule for the owner.",
                semantic_type="principle",
                turn_index=0,
                rationale="Generalizes the stated constraint.",
            )
        ],
    )
    monkeypatch.setattr(
        service_mod, "_maybe_evaluate", AsyncMock(return_value=evaluation)
    )

    report = await _distill(settings, result.source_id)

    # 2 deterministic atoms + 1 LLM proposal, all review-gated.
    assert report.atoms_pending_review == 3
    async with sqlite_mod.get_db() as conn:
        pending = await SuggestionRepository(conn).list_suggestions(
            target_id="wiki:default"
        )
        atoms = await KnowledgeRepository(conn).list_objects(kind="memory_atom")
    assert len(pending) == 3
    rationales = {s.rationale for s in pending}
    assert "Restated tooling preference." in rationales
    assert "Generalizes the stated constraint." in rationales
    typed = [a for a in atoms if a.properties.get("semantic_type") == "preference"]
    assert typed
    # The proposal itself never reaches canonical memory without review.
    assert all("hard rule" not in atom.properties["text"] for atom in atoms)


@pytest.mark.asyncio
async def test_persona_appears_only_after_the_statement_recurs(env):
    settings, store = env
    first = await store.capture(_conversation(session_id="s1"))
    report = await _distill(settings, first.source_id)
    assert report.persona_updated is False

    second = await store.capture(_conversation(session_id="s2"))
    report = await _distill(settings, second.source_id)
    assert report.persona_updated is True

    async with sqlite_mod.get_db() as conn:
        persona = await KnowledgeRepository(conn).get_object(PERSONA_ID)
        asset = await MemoryAssetRegistry(conn).get_asset(PERSONA_ID)
    assert persona is not None
    assert persona.properties["trait_count"] == 2
    assert asset is not None
    assert asset.asset_type == "persona"
    assert asset.layer == "L3"


@pytest.mark.asyncio
async def test_scenario_memory_is_registered_as_an_l2_asset(env):
    settings, store = env
    result = await store.capture(_conversation())
    report = await _distill(settings, result.source_id, scenario_key="archivum")

    assert report.scenario_id == "memory:scenario:wiki:default:archivum"
    async with sqlite_mod.get_db() as conn:
        asset = await MemoryAssetRegistry(conn).get_asset(report.scenario_id)
        edges = await KnowledgeRepository(conn).list_relationships(
            node_id=report.scenario_id
        )
    assert asset.layer == "L2"
    assert asset.status == "draft"  # durable promotion requires review
    assert "contains_atom" in {edge.rel_type for edge in edges}


@pytest.mark.asyncio
async def test_skill_is_extracted_only_from_real_tool_steps(env):
    settings, store = env
    talky = await store.capture(_conversation(session_id="talk"))
    report = await _distill(settings, talky.source_id)
    assert report.skill_id is None
    assert "no completed tool steps" in report.skill_reason

    worked = await store.capture(
        _conversation(
            session_id="work",
            texts=["Deploy the stack and verify it."],
            tool_calls=[
                ToolCall(name="Write", arguments={"file_path": "/a"}, result="ok"),
                ToolCall(
                    name="Bash", arguments={"command": "docker compose up"}, result="ok"
                ),
                ToolCall(name="Bash", arguments={"command": "pytest -q"}, result="ok"),
            ],
            outcomes=[Outcome(task="Deploy", status="success")],
        )
    )
    report = await _distill(settings, worked.source_id)
    assert report.skill_id == "memory:skill:deploy-the-stack-and-verify-it"

    async with sqlite_mod.get_db() as conn:
        asset = await MemoryAssetRegistry(conn).get_asset(report.skill_id)
        obj = await KnowledgeRepository(conn).get_object(report.skill_id)
    assert asset.status == "draft"  # activation stays a human decision
    assert [step["tool"] for step in obj.properties["steps"]] == ["Write", "Bash", "Bash"]
    assert obj.citations


@pytest.mark.asyncio
async def test_activating_an_asset_links_it_to_the_owner(env):
    settings, store = env
    worked = await store.capture(
        _conversation(
            session_id="work",
            texts=["Deploy the stack."],
            tool_calls=[
                ToolCall(name="Write", arguments={"file_path": "/a"}, result="ok"),
                ToolCall(name="Bash", arguments={"command": "b"}, result="ok"),
                ToolCall(name="Bash", arguments={"command": "c"}, result="ok"),
            ],
        )
    )
    report = await _distill(settings, worked.source_id)

    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        asset = await activate_asset(conn, repo, report.skill_id, approved_by="owner")
        edges = await repo.list_relationships(node_id=SELF_ID)
    assert asset.status == "active"
    assert asset.approved_by == "owner"
    assert asset.reviewed_at is not None
    assert any(
        edge.rel_type == "learned_skill" and edge.dst_id == report.skill_id
        for edge in edges
    )


@pytest.mark.asyncio
async def test_distillation_is_idempotent_for_the_same_source(env):
    settings, store = env
    result = await store.capture(_conversation())
    first = await _distill(settings, result.source_id)
    second = await _distill(settings, result.source_id)

    assert first.atoms_accepted == second.atoms_accepted
    async with sqlite_mod.get_db() as conn:
        atoms = await KnowledgeRepository(conn).list_objects(kind="memory_atom")
        versions = await MemoryAssetRegistry(conn).list_versions(
            f"memory:chat:{result.source_id}"
        )
        pending = await SuggestionRepository(conn).list_suggestions(
            target_id="wiki:default"
        )
    assert len(atoms) == 2
    # Same evidence, same content: no version churn on re-distillation.
    assert [v.version for v in versions] == [1]
    # Re-distilling the same source must not duplicate review cards.
    assert len(pending) == 2


@pytest.mark.asyncio
async def test_page_writer_produces_editable_markdown_views(env):
    settings, store = env
    result = await store.capture(_conversation())
    written: list[tuple[str, str]] = []

    async def page_writer(slug, title, markdown, tags):
        written.append((slug, markdown))

    loaded = await load_conversation(result.source_id, settings=settings)
    async with sqlite_mod.get_db() as conn:
        report = await distill_conversation(
            conn, loaded, wiki_id="default", page_writer=page_writer
        )

    slugs = [slug for slug, _ in written]
    assert "memory/sessions/s1" in slugs
    assert report.pages_written == slugs
    assert any("type: chat-memory" in markdown for _, markdown in written)


@pytest.mark.asyncio
async def test_page_writer_failure_does_not_block_canonical_memory(env):
    settings, store = env
    result = await store.capture(_conversation())

    async def broken_writer(slug, title, markdown, tags):
        raise RuntimeError("disk full")

    loaded = await load_conversation(result.source_id, settings=settings)
    async with sqlite_mod.get_db() as conn:
        report = await distill_conversation(
            conn, loaded, wiki_id="default", page_writer=broken_writer
        )
        atoms = await KnowledgeRepository(conn).list_objects(kind="memory_atom")

    assert report.pages_written == []
    assert len(atoms) == 2
