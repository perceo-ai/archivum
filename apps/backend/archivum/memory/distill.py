"""Assemble captured conversations into layered memory (L1 → L2 → L3).

Pure functions: they take atoms plus evidence anchors and return canonical
records and markdown. No database, no network, no LLM. The service layer
decides what gets written and what goes to human review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from archivum.capture.schema import Conversation
from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.memory.atoms import Atom, atom_id, normalize_atom_text

PERSONA_ID = "memory:persona:self"

# An atom must recur across at least this many distinct sessions before it is
# promoted into the persona layer. One offhand statement is not an identity.
PERSONA_MIN_SESSIONS = 2
PERSONA_ATOM_TYPES = frozenset({"preference", "fact", "constraint", "profile", "principle"})

# Render order for atom groups in markdown views: strategy semantic types
# first, deterministic extras last.
ATOM_RENDER_ORDER = (
    "profile",
    "decision",
    "preference",
    "principle",
    "procedure",
    "skill",
    "relationship",
    "source_summary",
    "code_insight",
    "constraint",
    "fact",
    "outcome",
)

SCENARIO_MAX_ATOMS = 40
PERSONA_MAX_TRAITS = 60


@dataclass(frozen=True, slots=True)
class TurnAnchor:
    """Where a turn's text lives inside the captured document."""

    chunk_id: str
    base_offset: int


@dataclass(frozen=True, slots=True)
class AtomRecord:
    """An atom paired with the canonical object it becomes."""

    atom: Atom
    object: KnowledgeObject
    accepted: bool


def turn_anchors(conv: Conversation, chunk_ids: list[str]) -> dict[int, TurnAnchor]:
    """Map each turn index to its chunk and the offset of its text.

    Mirrors `archivum.capture.transcript.render_transcript`: one chunk per turn,
    each block prefixed with `[role] `. Chunk start offsets are resolved by the
    caller, so this only needs the per-block prefix length.
    """
    anchors: dict[int, TurnAnchor] = {}
    for index, turn in enumerate(conv.turns):
        if index >= len(chunk_ids):
            break
        anchors[index] = TurnAnchor(
            chunk_id=chunk_ids[index], base_offset=len(f"[{turn.role}] ")
        )
    return anchors


def atom_citation(
    atom: Atom,
    *,
    source_id: str,
    anchors: dict[int, TurnAnchor],
    chunk_offsets: dict[str, int],
) -> Citation:
    anchor = anchors.get(atom.turn_index)
    if anchor is None:
        return Citation(
            source_id=source_id,
            chunk_id=source_id,
            span_start=None,
            span_end=None,
            quote=atom.text,
        )
    chunk_start = chunk_offsets.get(anchor.chunk_id, 0)
    start = chunk_start + anchor.base_offset + atom.char_start
    return Citation(
        source_id=source_id,
        chunk_id=anchor.chunk_id,
        span_start=start,
        span_end=start + (atom.char_end - atom.char_start),
        quote=atom.text,
    )


def build_atom_objects(
    atoms: list[Atom],
    *,
    scope: str,
    source_id: str,
    session_id: str,
    anchors: dict[int, TurnAnchor],
    chunk_offsets: dict[str, int],
    threshold: float,
    prior: dict[str, KnowledgeObject] | None = None,
) -> list[AtomRecord]:
    """Turn atoms into cited canonical objects, merging recurrence with priors.

    Atoms at or above `threshold` are accepted for direct canonical write;
    weaker atoms are returned with `accepted=False` so the caller can route
    them to the human review queue instead of writing them silently.
    """
    prior = prior or {}
    records: list[AtomRecord] = []
    for atom in atoms:
        object_id = atom_id(scope, atom.atom_type, atom.text)
        citation = atom_citation(
            atom, source_id=source_id, anchors=anchors, chunk_offsets=chunk_offsets
        )
        existing = prior.get(object_id)
        sessions = _merged_sessions(existing, session_id)
        citations = _merged_citations(existing, citation)
        confidence = _recurrence_confidence(atom.confidence, len(sessions))
        properties: dict[str, Any] = {
            "layer": "L1",
            "atom_type": atom.atom_type,
            "text": atom.text,
            "normalized": normalize_atom_text(atom.text),
            "sessions": sessions,
            "occurrences": len(sessions),
            "rule": atom.rule,
        }
        records.append(
            AtomRecord(
                atom=atom,
                object=KnowledgeObject(
                    id=object_id,
                    kind="memory_atom",
                    label=_atom_label(atom),
                    scope=scope,
                    confidence=confidence,
                    extraction_method="EXTRACTED",
                    citations=citations,
                    properties=properties,
                ),
                accepted=confidence >= threshold,
            )
        )
    return records


def _atom_label(atom: Atom) -> str:
    text = atom.text if len(atom.text) <= 120 else atom.text[:119] + "…"
    return f"{atom.atom_type}: {text}"


def _merged_sessions(existing: KnowledgeObject | None, session_id: str) -> list[str]:
    prior_sessions = []
    if existing is not None:
        value = existing.properties.get("sessions")
        if isinstance(value, list):
            prior_sessions = [str(item) for item in value]
    if session_id and session_id not in prior_sessions:
        prior_sessions.append(session_id)
    return sorted(set(prior_sessions))


def _merged_citations(
    existing: KnowledgeObject | None, citation: Citation
) -> list[Citation]:
    citations = list(existing.citations) if existing is not None else []
    key = (citation.source_id, citation.chunk_id, citation.span_start)
    if all((c.source_id, c.chunk_id, c.span_start) != key for c in citations):
        citations.append(citation)
    return citations


def _recurrence_confidence(base: float, occurrences: int) -> float:
    """Recurrence is corroboration: repeated statements get a bounded lift."""
    bonus = min(max(occurrences - 1, 0) * 0.05, 0.15)
    return round(min(base + bonus, 1.0), 4)


# ── L2: scenario memory ───────────────────────────────────────────────────


def scenario_id(scope: str, key: str) -> str:
    return f"memory:scenario:{scope}:{key}"


def build_scenario(
    records: list[AtomRecord],
    *,
    scope: str,
    key: str,
    name: str,
    prior: KnowledgeObject | None = None,
) -> KnowledgeObject | None:
    """Aggregate accepted atoms into one project/scenario memory object."""
    accepted = [record for record in records if record.accepted]
    if not accepted:
        return None

    ranked = sorted(
        accepted,
        key=lambda record: (-record.object.confidence, record.object.id),
    )[:SCENARIO_MAX_ATOMS]

    prior_atom_ids: list[str] = []
    prior_citations: list[Citation] = []
    if prior is not None:
        value = prior.properties.get("atom_ids")
        if isinstance(value, list):
            prior_atom_ids = [str(item) for item in value]
        prior_citations = list(prior.citations)

    atom_ids = sorted({*prior_atom_ids, *(record.object.id for record in ranked)})
    citations = _dedupe_citations(
        [*prior_citations, *(record.object.citations[0] for record in ranked)]
    )
    by_type: dict[str, list[str]] = {}
    for record in ranked:
        by_type.setdefault(record.atom.atom_type, []).append(record.atom.text)

    return KnowledgeObject(
        id=scenario_id(scope, key),
        kind="memory_scenario",
        label=name,
        scope=scope,
        confidence=round(
            sum(record.object.confidence for record in ranked) / len(ranked), 4
        ),
        extraction_method="INFERRED",
        citations=citations,
        properties={
            "layer": "L2",
            "scenario_key": key,
            "atom_ids": atom_ids,
            "by_type": by_type,
            "atom_count": len(atom_ids),
        },
    )


# ── L3: persona memory ────────────────────────────────────────────────────


def build_persona(
    atom_objects: list[KnowledgeObject],
    *,
    scope: str,
    min_sessions: int = PERSONA_MIN_SESSIONS,
    prior: KnowledgeObject | None = None,
) -> KnowledgeObject | None:
    """Promote recurring preferences, facts, and constraints into a persona.

    Only atoms observed in at least `min_sessions` distinct sessions qualify,
    so the owner profile reflects durable identity rather than one-off asides.
    """
    qualifying = [
        obj
        for obj in atom_objects
        if obj.properties.get("atom_type") in PERSONA_ATOM_TYPES
        and int(obj.properties.get("occurrences", 0) or 0) >= min_sessions
    ]
    if not qualifying:
        return None

    ranked = sorted(
        qualifying,
        key=lambda obj: (
            -int(obj.properties.get("occurrences", 0) or 0),
            -obj.confidence,
            obj.id,
        ),
    )[:PERSONA_MAX_TRAITS]

    traits = [
        {
            "atom_id": obj.id,
            "atom_type": obj.properties.get("atom_type"),
            "text": obj.properties.get("text", obj.label),
            "occurrences": int(obj.properties.get("occurrences", 0) or 0),
            "confidence": obj.confidence,
        }
        for obj in ranked
    ]
    citations = _dedupe_citations(
        [citation for obj in ranked for citation in obj.citations[:1]]
    )
    prior_version = int((prior.properties.get("revision") if prior else 0) or 0)

    return KnowledgeObject(
        id=PERSONA_ID,
        kind="memory_persona",
        label="Owner profile",
        scope=scope,
        confidence=round(sum(obj.confidence for obj in ranked) / len(ranked), 4),
        extraction_method="INFERRED",
        citations=citations,
        properties={
            "layer": "L3",
            "traits": traits,
            "trait_count": len(traits),
            "min_sessions": min_sessions,
            "revision": prior_version + 1,
        },
    )


def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
    unique: list[Citation] = []
    seen: set[tuple[str, str, int | None, int | None]] = set()
    for citation in citations:
        key = (citation.source_id, citation.chunk_id, citation.span_start, citation.span_end)
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique


# ── Markdown views ────────────────────────────────────────────────────────


def render_chat_memory_markdown(
    *, session_id: str, interface: str, records: list[AtomRecord], source_id: str
) -> str:
    lines = [
        "---",
        "type: chat-memory",
        f"session: {session_id}",
        f"interface: {interface}",
        f"source: {source_id}",
        "---",
        "",
        f"# Session memory — {session_id}",
        "",
    ]
    by_type: dict[str, list[AtomRecord]] = {}
    for record in records:
        by_type.setdefault(record.atom.atom_type, []).append(record)
    for atom_type in ATOM_RENDER_ORDER:
        group = by_type.get(atom_type)
        if not group:
            continue
        lines.extend([f"## {atom_type.capitalize()}s", ""])
        for record in group:
            state = "" if record.accepted else " _(pending review)_"
            lines.append(
                f"- {record.atom.text} "
                f"`confidence {record.object.confidence:.2f}`{state}"
            )
        lines.append("")
    if not records:
        lines.extend(["No durable memory was extracted from this session.", ""])
    return "\n".join(lines)


def render_scenario_markdown(scenario: KnowledgeObject) -> str:
    by_type = scenario.properties.get("by_type", {})
    lines = [
        "---",
        "type: scenario-memory",
        f"scenario_key: {scenario.properties.get('scenario_key', '')}",
        "---",
        "",
        f"# {scenario.label}",
        "",
        f"{scenario.properties.get('atom_count', 0)} atoms, "
        f"average confidence {scenario.confidence:.2f}.",
        "",
    ]
    for atom_type in ATOM_RENDER_ORDER:
        items = by_type.get(atom_type) if isinstance(by_type, dict) else None
        if not items:
            continue
        lines.extend([f"## {atom_type.capitalize()}s", ""])
        lines.extend(f"- {item}" for item in items)
        lines.append("")
    return "\n".join(lines)


def render_persona_markdown(persona: KnowledgeObject) -> str:
    traits = persona.properties.get("traits", [])
    lines = [
        "---",
        "type: persona-memory",
        f"revision: {persona.properties.get('revision', 1)}",
        "---",
        "",
        "# Owner profile",
        "",
        "Durable statements observed across at least "
        f"{persona.properties.get('min_sessions', PERSONA_MIN_SESSIONS)} sessions.",
        "",
    ]
    for trait in traits if isinstance(traits, list) else []:
        lines.append(
            f"- **{trait.get('atom_type')}** — {trait.get('text')} "
            f"`seen in {trait.get('occurrences')} sessions`"
        )
    lines.append("")
    return "\n".join(lines)
