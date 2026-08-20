"""Wire distillation, skills, and asset governance into the stores.

The rule this module enforces: durable memory promotion requires review.
High-confidence atoms may be written to the canonical layer as provisional
records, but every atom gets a review card, every distilled asset starts as
a draft, and every written record keeps the citation it was extracted from.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace

import aiosqlite

from archivum.capture.canonical import from_canonical_bytes
from archivum.capture.schema import Conversation
from archivum.config import Settings, get_settings
from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository
from archivum.knowledge.suggestions import SuggestionRepository
from archivum.memory import distill
from archivum.memory.atoms import Atom, atom_id, extract_atoms, split_sentences
from archivum.memory.conflicts import RelatedMemory, find_related
from archivum.memory.evaluator import (
    AtomEvaluation,
    EvaluationResult,
    blend_confidence,
    evaluate_conversation,
)
from archivum.memory.models import MemoryAsset
from archivum.memory.registry import MemoryAssetRegistry
from archivum.memory.skills import (
    MIN_TOOL_CALLS,
    SkillDraft,
    extract_skill,
    render_skill_markdown,
)
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore

logger = logging.getLogger(__name__)

DEFAULT_ATOM_THRESHOLD = 0.7

_ASSET_RELATIONSHIPS = {
    "chat": "remembers",
    "scenario": "remembers",
    "persona": "describes_self",
    "skill": "learned_skill",
}

_CHAT_MEMORY_FOLDER = "memory/sessions"
_SCENARIO_FOLDER = "memory/scenarios"
_PERSONA_SLUG = "memory/persona"
_SKILL_FOLDER = "skills"


class DistillationError(RuntimeError):
    """Raised when a source cannot be distilled."""


@dataclass
class DistillationReport:
    source_id: str
    session_id: str
    scope: str
    atoms_total: int = 0
    atoms_accepted: int = 0
    atoms_pending_review: int = 0
    conflicts_flagged: int = 0
    sentences_scanned: int = 0
    asset_ids: list[str] = field(default_factory=list)
    scenario_id: str | None = None
    persona_updated: bool = False
    skill_id: str | None = None
    skill_reason: str | None = None
    pages_written: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LoadedConversation:
    conversation: Conversation
    source_id: str
    chunk_ids: list[str]
    chunk_offsets: dict[str, int]


# ── Loading captured evidence ─────────────────────────────────────────────


async def load_conversation(
    source_id: str, *, wiki_id: str | None = None, settings: Settings | None = None
) -> LoadedConversation:
    """Rehydrate a captured conversation and its chunk anchors from L0/L1.

    Pass `wiki_id` whenever the source id came from a request. Distillation
    reads a source's full text and writes it into memory, so an unscoped lookup
    would let a caller name another vault's source id and pull its contents
    into their own memory.
    """
    settings = settings or get_settings()
    store = SourceStore()
    source = await store.get_source(source_id, wiki_id=wiki_id)
    if source is None:
        raise DistillationError(f"Source '{source_id}' not found")
    document = await store.get_document_for_source(source_id)
    if document is None:
        raise DistillationError(f"Source '{source_id}' has no document")
    chunks = await store.list_chunks(document.id)

    blobs = BlobStore(settings.blob_dir)
    try:
        raw = blobs.get(source.content_hash)
    except KeyError as exc:
        raise DistillationError(
            f"Evidence blob for source '{source_id}' is missing"
        ) from exc
    try:
        conversation = from_canonical_bytes(raw)
    except (ValueError, KeyError) as exc:
        raise DistillationError(
            f"Source '{source_id}' is not a captured conversation"
        ) from exc

    return LoadedConversation(
        conversation=conversation,
        source_id=source_id,
        chunk_ids=[chunk.id for chunk in chunks],
        chunk_offsets={chunk.id: chunk.start_offset for chunk in chunks},
    )


# ── Distillation ──────────────────────────────────────────────────────────


async def distill_conversation(
    conn: aiosqlite.Connection,
    loaded: LoadedConversation,
    *,
    wiki_id: str,
    threshold: float = DEFAULT_ATOM_THRESHOLD,
    scenario_key: str | None = None,
    scenario_name: str | None = None,
    persona_min_sessions: int = distill.PERSONA_MIN_SESSIONS,
    skill_min_tool_calls: int = MIN_TOOL_CALLS,
    page_writer=None,
) -> DistillationReport:
    """Promote one captured conversation through L1, L2, and L3.

    `page_writer` is an optional async callback `(slug, title, markdown, tags)`
    so markdown views stay editable; distillation itself never requires it.
    """
    conversation = loaded.conversation
    scope = f"wiki:{wiki_id}"
    repo = KnowledgeRepository(conn)
    registry = MemoryAssetRegistry(conn)
    suggestions = SuggestionRepository(conn)
    report = DistillationReport(
        source_id=loaded.source_id,
        session_id=conversation.session_id,
        scope=scope,
    )

    await ensure_personal_root(repo, wiki_id=wiki_id)

    atoms = extract_atoms(conversation)
    report.atoms_total = len(atoms)
    report.sentences_scanned = sum(
        len(split_sentences(turn.text)) for turn in conversation.turns
    )
    evaluation = await _maybe_evaluate(conversation, atoms)
    if evaluation is not None:
        atoms = _blend_evaluated_atoms(atoms, evaluation)
    anchors = distill.turn_anchors(conversation, loaded.chunk_ids)
    prior = await _load_prior_atoms(repo, atoms, scope)
    records = distill.build_atom_objects(
        atoms,
        scope=scope,
        source_id=loaded.source_id,
        session_id=conversation.session_id,
        anchors=anchors,
        chunk_offsets=loaded.chunk_offsets,
        threshold=threshold,
        prior=prior,
    )

    queued = await _pending_atom_suggestion_ids(suggestions, wiki_id)
    existing_atoms = await repo.list_objects(
        kind="memory_atom", scope=scope, limit=10_000
    )
    for index, record in enumerate(records):
        atom_evaluation = (
            evaluation.evaluations.get(index) if evaluation is not None else None
        )
        if atom_evaluation is not None and atom_evaluation.semantic_type:
            record.object.properties["semantic_type"] = atom_evaluation.semantic_type
        related = find_related(
            record.object.id, record.atom.text, record.atom.atom_type, existing_atoms
        )
        if related.conflicts:
            record.object.properties["conflicts"] = related.conflicts
            report.conflicts_flagged += 1
        prior_object = prior.get(record.object.id)
        prior_state = (
            prior_object.properties.get("review_state") if prior_object else None
        )
        if record.accepted:
            state = "accepted" if prior_state == "accepted" else "pending"
            record.object.properties["review_state"] = state
            await repo.upsert_object(record.object)
            report.atoms_accepted += 1
            if state == "pending":
                await _ensure_atom_suggestion(
                    suggestions,
                    record,
                    wiki_id=wiki_id,
                    queued=queued,
                    evaluation=atom_evaluation,
                    related=related,
                )
                report.atoms_pending_review += 1
        else:
            await _ensure_atom_suggestion(
                suggestions,
                record,
                wiki_id=wiki_id,
                queued=queued,
                evaluation=atom_evaluation,
                related=related,
            )
            report.atoms_pending_review += 1

    report.atoms_pending_review += await _suggest_proposed_atoms(
        suggestions,
        evaluation,
        loaded=loaded,
        scope=scope,
        wiki_id=wiki_id,
        anchors=anchors,
        queued=queued,
    )

    # ── L1 asset: this session's chat memory ──
    chat_asset = await _register_chat_memory(
        repo,
        registry,
        records=records,
        loaded=loaded,
        wiki_id=wiki_id,
        scope=scope,
        page_writer=page_writer,
        report=report,
    )
    if chat_asset is not None:
        report.asset_ids.append(chat_asset.id)

    # ── L2 asset: scenario memory ──
    key = scenario_key or _default_scenario_key(conversation)
    if key:
        prior_scenario = await repo.get_object(distill.scenario_id(scope, key))
        scenario = distill.build_scenario(
            records,
            scope=scope,
            key=key,
            name=scenario_name or f"Scenario memory — {key}",
            prior=prior_scenario,
        )
        if scenario is not None:
            scenario.properties["review_state"] = _derived_review_state(prior_scenario)
            await repo.upsert_object(scenario)
            await link_to_self(
                repo, scenario.id, "remembers", citation=scenario.citations[0]
            )
            await _link_atoms(
                repo,
                parent=scenario,
                atom_ids=[
                    str(atom) for atom in scenario.properties.get("atom_ids", [])
                ],
                scope=scope,
            )
            asset = await _register_object_asset(
                registry,
                obj=scenario,
                asset_type="scenario",
                wiki_id=wiki_id,
                markdown=distill.render_scenario_markdown(scenario),
                page_slug=f"{_SCENARIO_FOLDER}/{key}",
                page_writer=page_writer,
                report=report,
            )
            report.scenario_id = scenario.id
            report.asset_ids.append(asset.id)

    # ── L3 asset: owner persona ──
    persona = await _rebuild_persona(
        repo,
        registry,
        scope=scope,
        wiki_id=wiki_id,
        min_sessions=persona_min_sessions,
        page_writer=page_writer,
        report=report,
    )
    if persona is not None:
        report.persona_updated = True
        report.asset_ids.append(persona.id)

    # ── Skill memory ──
    skill_asset, skill_reason = await _register_skill(
        repo,
        registry,
        loaded=loaded,
        wiki_id=wiki_id,
        scope=scope,
        min_tool_calls=skill_min_tool_calls,
        page_writer=page_writer,
        report=report,
    )
    report.skill_id = skill_asset.id if skill_asset is not None else None
    report.skill_reason = skill_reason
    if skill_asset is not None:
        report.asset_ids.append(skill_asset.id)

    return report


async def _maybe_evaluate(
    conversation: Conversation, atoms: list[Atom]
) -> EvaluationResult | None:
    """Run the optional LLM half of the hybrid evaluator when configured."""
    settings = get_settings()
    if not settings.memory_llm_evaluator_enabled:
        return None
    return await evaluate_conversation(conversation, atoms, settings=settings)


def _blend_evaluated_atoms(
    atoms: list[Atom], evaluation: EvaluationResult
) -> list[Atom]:
    """Blend deterministic and LLM confidence per atom, preserving order."""
    blended: list[Atom] = []
    for index, atom in enumerate(atoms):
        atom_evaluation = evaluation.evaluations.get(index)
        if atom_evaluation is None:
            blended.append(atom)
            continue
        blended.append(
            replace(
                atom,
                confidence=blend_confidence(atom.confidence, atom_evaluation),
            )
        )
    return blended


async def _suggest_proposed_atoms(
    suggestions: SuggestionRepository,
    evaluation: EvaluationResult | None,
    *,
    loaded: LoadedConversation,
    scope: str,
    wiki_id: str,
    anchors: dict[int, distill.TurnAnchor],
    queued: set[str],
) -> int:
    """Route LLM-proposed atoms straight to review; they never write directly."""
    if evaluation is None or not evaluation.proposed:
        return 0
    turn_count = len(loaded.conversation.turns)
    proposed_atoms = [
        Atom(
            atom_type=proposal.semantic_type,
            text=proposal.text,
            confidence=0.5,
            turn_index=min(max(proposal.turn_index, 0), max(turn_count - 1, 0)),
            char_start=0,
            char_end=len(proposal.text),
            rule="llm:proposed",
        )
        for proposal in evaluation.proposed
    ]
    records = distill.build_atom_objects(
        proposed_atoms,
        scope=scope,
        source_id=loaded.source_id,
        session_id=loaded.conversation.session_id,
        anchors=anchors,
        chunk_offsets=loaded.chunk_offsets,
        threshold=2.0,  # > any confidence: proposals are review-only
    )
    created = 0
    for record, proposal in zip(records, evaluation.proposed):
        record.object.properties["semantic_type"] = proposal.semantic_type
        if await _ensure_atom_suggestion(
            suggestions,
            record,
            wiki_id=wiki_id,
            queued=queued,
            rationale=proposal.rationale
            or "Proposed by the LLM evaluator; needs human review.",
        ):
            created += 1
    return created


async def _pending_atom_suggestion_ids(
    suggestions: SuggestionRepository, wiki_id: str
) -> set[str]:
    """Collect atom object ids that already have a pending review card."""
    pending = await suggestions.list_suggestions(
        target_id=f"wiki:{wiki_id}", status="pending"
    )
    queued: set[str] = set()
    for suggestion in pending:
        if suggestion.suggestion_type != "memory_atom":
            continue
        for raw in suggestion.proposed_objects:
            if isinstance(raw, dict) and raw.get("id"):
                queued.add(str(raw["id"]))
    return queued


async def _ensure_atom_suggestion(
    suggestions: SuggestionRepository,
    record,
    *,
    wiki_id: str,
    queued: set[str],
    evaluation: AtomEvaluation | None = None,
    rationale: str | None = None,
    related: RelatedMemory | None = None,
) -> bool:
    """Create one review card per atom; re-distillation must not duplicate."""
    if record.object.id in queued:
        return False
    scores: dict[str, float] = {"confidence": record.object.confidence}
    durability = ""
    if evaluation is not None:
        scores.update(evaluation.scores)
        durability = evaluation.durability_estimate
        rationale = rationale or evaluation.rationale
    await suggestions.create_suggestion(
        target_id=f"wiki:{wiki_id}",
        suggestion_type="memory_atom",
        proposed_markdown=f"- {record.atom.text}",
        proposed_objects=[record.object.model_dump()],
        citations=[c.model_dump() for c in record.object.citations],
        proposed_scopes=[record.object.scope],
        scores=scores,
        duplicates=related.duplicates if related is not None else [],
        conflicts=related.conflicts if related is not None else [],
        rationale=rationale
        or (
            "Above-threshold extraction; promotion still requires review."
            if record.accepted
            else "Extraction confidence below threshold; needs human review."
        ),
        estimated_durability=durability,
    )
    queued.add(record.object.id)
    return True


async def _load_prior_atoms(
    repo: KnowledgeRepository, atoms: list[Atom], scope: str
) -> dict[str, KnowledgeObject]:
    prior: dict[str, KnowledgeObject] = {}
    for atom in atoms:
        object_id = atom_id(scope, atom.atom_type, atom.text)
        existing = await repo.get_object(object_id)
        if existing is not None:
            prior[object_id] = existing
    return prior


def _derived_review_state(prior: KnowledgeObject | None) -> str:
    """Derived memory summaries stay provisional until their asset is activated."""
    if prior is not None and prior.properties.get("review_state") == "accepted":
        return "accepted"
    return "pending"


def _default_scenario_key(conversation: Conversation) -> str | None:
    """Prefer an explicit project key; otherwise group by capture interface."""
    metadata = conversation.metadata or {}
    for candidate in ("project_key", "project", "scenario"):
        value = metadata.get(candidate)
        if isinstance(value, str) and value.strip():
            return _slug(value)
    return _slug(conversation.interface) or None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


async def _register_chat_memory(
    repo: KnowledgeRepository,
    registry: MemoryAssetRegistry,
    *,
    records,
    loaded: LoadedConversation,
    wiki_id: str,
    scope: str,
    page_writer,
    report: DistillationReport,
) -> MemoryAsset | None:
    conversation = loaded.conversation
    citations = [
        record.object.citations[0] for record in records if record.object.citations
    ] or [
        Citation(
            source_id=loaded.source_id,
            chunk_id=loaded.chunk_ids[0] if loaded.chunk_ids else loaded.source_id,
            span_start=None,
            span_end=None,
            quote=conversation.session_id,
        )
    ]
    object_id = f"memory:chat:{loaded.source_id}"
    prior_chat = await repo.get_object(object_id)
    obj = KnowledgeObject(
        id=object_id,
        kind="memory_chat",
        label=f"Session memory — {conversation.session_id}",
        scope=scope,
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=citations[:20],
        properties={
            "layer": "L1",
            "session_id": conversation.session_id,
            "interface": conversation.interface,
            "source_id": loaded.source_id,
            "atom_ids": sorted({record.object.id for record in records}),
            "accepted": report.atoms_accepted,
            "pending_review": report.atoms_pending_review,
            "review_state": _derived_review_state(prior_chat),
        },
    )
    await repo.upsert_object(obj)
    await link_to_self(repo, object_id, "remembers", citation=obj.citations[0])
    await _link_atoms(
        repo,
        parent=obj,
        atom_ids=[record.object.id for record in records if record.accepted],
        scope=scope,
    )

    markdown = distill.render_chat_memory_markdown(
        session_id=conversation.session_id,
        interface=conversation.interface,
        records=list(records),
        source_id=loaded.source_id,
    )
    return await _register_object_asset(
        registry,
        obj=obj,
        asset_type="chat",
        wiki_id=wiki_id,
        markdown=markdown,
        page_slug=f"{_CHAT_MEMORY_FOLDER}/{_slug(conversation.session_id)}",
        page_writer=page_writer,
        report=report,
    )


async def _rebuild_persona(
    repo: KnowledgeRepository,
    registry: MemoryAssetRegistry,
    *,
    scope: str,
    wiki_id: str,
    min_sessions: int,
    page_writer,
    report: DistillationReport,
) -> MemoryAsset | None:
    atom_objects = await repo.list_objects(kind="memory_atom", scope=scope, limit=10_000)
    prior_persona = await repo.get_object(distill.PERSONA_ID)
    persona = distill.build_persona(
        atom_objects,
        scope=scope,
        min_sessions=min_sessions,
        prior=prior_persona,
    )
    if persona is None:
        return None
    persona.properties["review_state"] = _derived_review_state(prior_persona)
    await repo.upsert_object(persona)
    await link_to_self(
        repo, persona.id, "describes_self", citation=persona.citations[0]
    )
    return await _register_object_asset(
        registry,
        obj=persona,
        asset_type="persona",
        wiki_id=wiki_id,
        markdown=distill.render_persona_markdown(persona),
        page_slug=_PERSONA_SLUG,
        page_writer=page_writer,
        report=report,
    )


async def _register_skill(
    repo: KnowledgeRepository,
    registry: MemoryAssetRegistry,
    *,
    loaded: LoadedConversation,
    wiki_id: str,
    scope: str,
    min_tool_calls: int,
    page_writer,
    report: DistillationReport,
) -> tuple[MemoryAsset | None, str | None]:
    draft = extract_skill(loaded.conversation, min_tool_calls=min_tool_calls)
    if draft is None:
        return None, "No reusable procedure: the session had no completed tool steps."
    return (
        await register_skill_draft(
            repo,
            registry,
            draft=draft,
            loaded=loaded,
            wiki_id=wiki_id,
            scope=scope,
            page_writer=page_writer,
            report=report,
        ),
        None,
    )


async def register_skill_draft(
    repo: KnowledgeRepository,
    registry: MemoryAssetRegistry,
    *,
    draft: SkillDraft,
    loaded: LoadedConversation,
    wiki_id: str,
    scope: str,
    page_writer=None,
    report: DistillationReport | None = None,
) -> MemoryAsset:
    """Persist a skill as a draft asset; activation stays a human decision."""
    anchors = distill.turn_anchors(loaded.conversation, loaded.chunk_ids)
    citations = [
        _step_citation(
            loaded, anchors, turn_index=draft.trigger_turn_index, quote=draft.trigger
        )
    ]
    citations.extend(
        _step_citation(loaded, anchors, turn_index=step.turn_index, quote=step.summary)
        for step in draft.steps[:20]
    )
    object_id = f"memory:skill:{draft.slug}"
    prior_skill = await repo.get_object(object_id)
    obj = KnowledgeObject(
        id=object_id,
        kind="memory_skill",
        label=draft.name,
        scope=scope,
        confidence=draft.confidence,
        extraction_method="EXTRACTED",
        citations=citations,
        properties={
            "review_state": _derived_review_state(prior_skill),
            "layer": "L2",
            "slug": draft.slug,
            "trigger": draft.trigger,
            "steps": [
                {"order": step.order, "tool": step.tool, "summary": step.summary}
                for step in draft.steps
            ],
            "validation": list(draft.validation),
            "outcome_status": draft.outcome_status,
            "tool_call_count": draft.tool_call_count,
            "source_id": loaded.source_id,
        },
    )
    await repo.upsert_object(obj)
    await link_to_self(
        repo, object_id, "learned_skill", citation=obj.citations[0], confidence=draft.confidence
    )
    markdown = render_skill_markdown(
        draft, provenance=f"Extracted from captured source `{loaded.source_id}`."
    )
    return await _register_object_asset(
        registry,
        obj=obj,
        asset_type="skill",
        wiki_id=wiki_id,
        markdown=markdown,
        page_slug=f"{_SKILL_FOLDER}/{draft.slug}",
        page_writer=page_writer,
        report=report,
        # A recovered procedure is a proposal until the owner activates it.
        status="draft",
    )


async def _link_atoms(
    repo: KnowledgeRepository,
    *,
    parent: KnowledgeObject,
    atom_ids: list[str],
    scope: str,
) -> None:
    """Make distilled memory traversable: parent → each atom it summarises."""
    if not parent.citations:
        return
    for atom_object_id in sorted(set(atom_ids)):
        await repo.upsert_relationship(
            KnowledgeRelationship(
                id=f"rel:{parent.id}:contains_atom:{atom_object_id}",
                src_id=parent.id,
                dst_id=atom_object_id,
                rel_type="contains_atom",
                scope=scope,
                confidence=1.0,
                extraction_method="EXTRACTED",
                citations=[parent.citations[0]],
                properties={},
            )
        )


def _step_citation(
    loaded: LoadedConversation,
    anchors: dict[int, distill.TurnAnchor],
    *,
    turn_index: int,
    quote: str,
) -> Citation:
    anchor = anchors.get(turn_index)
    chunk_id = anchor.chunk_id if anchor is not None else loaded.source_id
    return Citation(
        source_id=loaded.source_id,
        chunk_id=chunk_id,
        span_start=None,
        span_end=None,
        quote=quote,
    )


async def _register_object_asset(
    registry: MemoryAssetRegistry,
    *,
    obj: KnowledgeObject,
    asset_type: str,
    wiki_id: str,
    markdown: str,
    page_slug: str,
    page_writer,
    report: DistillationReport | None,
    status: str = "draft",
) -> MemoryAsset:
    """Register the canonical object as a governed asset sharing its id.

    Assets start as drafts: activation is a human review decision, so nothing
    distillation produces becomes agent-loadable on its own.
    """
    layer = str(obj.properties.get("layer", "L1"))
    if page_writer is not None:
        try:
            await page_writer(page_slug, obj.label, markdown, [asset_type, "memory"])
            if report is not None:
                report.pages_written.append(page_slug)
        except Exception as exc:  # editable views are a convenience, not a gate
            logger.warning(
                "Memory page write failed", extra={"slug": page_slug, "error": str(exc)}
            )
    return await registry.register_asset(
        id=obj.id,
        wiki_id=wiki_id,
        asset_type=asset_type,
        layer=layer,
        name=obj.label,
        scope=obj.scope,
        status=status,
        summary=_summary_for(obj),
        body=markdown,
        tags=[asset_type, "memory"],
        page_slug=page_slug,
        metadata={"knowledge_id": obj.id, "kind": obj.kind, **_asset_metadata(obj)},
        citations=obj.citations,
        change_note=f"Distilled from {obj.properties.get('source_id', obj.id)}",
    )


def _asset_metadata(obj: KnowledgeObject) -> dict:
    keys = ("session_id", "interface", "scenario_key", "trait_count", "tool_call_count",
            "outcome_status", "atom_count", "revision")
    return {key: obj.properties[key] for key in keys if key in obj.properties}


def _summary_for(obj: KnowledgeObject) -> str:
    if obj.kind == "memory_chat":
        return (
            f"{len(obj.properties.get('atom_ids', []))} atoms from session "
            f"{obj.properties.get('session_id', '')}."
        )
    if obj.kind == "memory_scenario":
        return f"{obj.properties.get('atom_count', 0)} atoms of scenario memory."
    if obj.kind == "memory_persona":
        return f"{obj.properties.get('trait_count', 0)} durable owner traits."
    if obj.kind == "memory_skill":
        return (
            f"{len(obj.properties.get('steps', []))} recorded steps, outcome "
            f"{obj.properties.get('outcome_status', 'unknown')}."
        )
    return obj.label


# ── Asset governance helpers ──────────────────────────────────────────────


async def activate_asset(
    conn: aiosqlite.Connection,
    repo: KnowledgeRepository,
    asset_id: str,
    *,
    approved_by: str | None = None,
) -> MemoryAsset:
    """Activate an asset and make sure the owner link exists for its type.

    Activation is the human promotion gate, so the approver is recorded on
    the asset when known.
    """
    registry = MemoryAssetRegistry(conn)
    asset = await registry.set_status(asset_id, "active")
    if approved_by is not None:
        asset = await registry.mark_reviewed(asset_id, approved_by=approved_by)
    relationship = _ASSET_RELATIONSHIPS.get(asset.asset_type, "owns_asset")
    obj = await repo.get_object(asset.id)
    if obj is not None:
        # Activation is the review decision: the canonical record it governs
        # becomes accepted and context-visible together with the asset.
        obj.properties["review_state"] = "accepted"
        await repo.upsert_object(obj)
        if asset.citations:
            await link_to_self(repo, asset.id, relationship, citation=asset.citations[0])
    return asset
