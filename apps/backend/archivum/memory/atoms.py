"""Deterministic L1 atom extraction from a captured conversation.

No LLM call is involved. Every atom is anchored to the exact sentence it came
from, so provenance survives into the canonical knowledge store. Rules are
ordered: the first matching rule wins, so `decision` beats `preference`, which
beats `constraint`, which beats `fact`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from archivum.capture.schema import Conversation

# The strategy's semantic memory taxonomy plus the deterministic extras
# (`constraint`, `outcome`) the rule extractor already emits. Deterministic
# rules produce a subset; the LLM-assisted evaluator may type atoms with any
# of these.
AtomType = Literal[
    "profile",
    "preference",
    "decision",
    "principle",
    "fact",
    "procedure",
    "skill",
    "relationship",
    "source_summary",
    "code_insight",
    "constraint",
    "outcome",
]

SEMANTIC_ATOM_TYPES: frozenset[str] = frozenset(
    {
        "profile",
        "preference",
        "decision",
        "principle",
        "fact",
        "procedure",
        "skill",
        "relationship",
        "source_summary",
        "code_insight",
        "constraint",
        "outcome",
    }
)

MIN_ATOM_CHARS = 8
MAX_ATOM_CHARS = 400

# Sentence boundary: terminal punctuation followed by whitespace, or a newline.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

_HEDGE_RE = re.compile(
    r"\b(?:maybe|might|probably|perhaps|possibly|i think|not sure|i guess)\b",
    re.IGNORECASE,
)

# Ordered rules. Each entry is (atom_type, pattern, base_confidence).
_RULES: tuple[tuple[AtomType, re.Pattern[str], float], ...] = (
    (
        "decision",
        re.compile(
            r"\b(?:we|i)\s+(?:decided|chose|settled\s+on|are\s+going\s+with|will\s+go\s+with)\b"
            r"|\blet'?s\s+go\s+with\b"
            r"|\bdecision:\s",
            re.IGNORECASE,
        ),
        0.85,
    ),
    (
        "preference",
        re.compile(
            r"\bi\s+(?:prefer|like|love|hate|dislike|usually|always|never|tend\s+to|want)\b"
            r"|\buse\s+.+\s+instead\s+of\s+.+"
            r"|\bmy\s+preference\b",
            re.IGNORECASE,
        ),
        0.8,
    ),
    (
        "constraint",
        re.compile(
            r"\b(?:must\s+not|never\s+(?:use|do|add|commit)|do\s+not|don'?t|has\s+to|have\s+to"
            r"|must|required\s+to|only\s+ever|make\s+sure)\b",
            re.IGNORECASE,
        ),
        0.7,
    ),
    (
        "fact",
        re.compile(
            r"\bi\s?(?:'m|\s+am)\b|\bmy\s+\w+\s+is\b|\bi\s+(?:work|live|run|own|study)\b",
            re.IGNORECASE,
        ),
        0.75,
    ),
)

# Only the owner's own turns carry first-person memory. Assistant turns are
# mined for decisions only, because that is the one atom type where the
# assistant restating a choice is still evidence of the choice.
_OWNER_ROLES = frozenset({"user"})
_DECISION_ROLES = frozenset({"user", "assistant"})


@dataclass(frozen=True, slots=True)
class Atom:
    """One cited memory atom extracted from a single conversation turn."""

    atom_type: AtomType
    text: str
    confidence: float
    turn_index: int
    char_start: int
    char_end: int
    rule: str

    @property
    def normalized(self) -> str:
        return normalize_atom_text(self.text)


def normalize_atom_text(text: str) -> str:
    """Collapse whitespace and casing so repeated statements dedupe."""
    return re.sub(r"\s+", " ", text).strip().casefold().rstrip(".!?")


def atom_id(scope: str, atom_type: str, text: str) -> str:
    """Stable id so the same statement in two sessions is one atom."""
    digest = hashlib.sha256(
        f"{scope}|{atom_type}|{normalize_atom_text(text)}".encode("utf-8")
    ).hexdigest()
    return f"memory:atom:{digest[:16]}"


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, sentence) spans relative to `text`."""
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for piece in _SENTENCE_SPLIT_RE.split(text):
        if piece == "":
            continue
        start = text.find(piece, cursor)
        if start < 0:
            continue
        end = start + len(piece)
        cursor = end
        stripped = piece.strip()
        if not stripped:
            continue
        offset = piece.find(stripped)
        spans.append((start + offset, start + offset + len(stripped), stripped))
    return spans


def _classify(sentence: str, role: str) -> tuple[AtomType, float, str] | None:
    for atom_type, pattern, base in _RULES:
        allowed = _DECISION_ROLES if atom_type == "decision" else _OWNER_ROLES
        if role not in allowed:
            continue
        match = pattern.search(sentence)
        if match is None:
            continue
        confidence = base * (0.6 if _HEDGE_RE.search(sentence) else 1.0)
        return atom_type, round(confidence, 4), pattern.pattern[:40]
    return None


def extract_atoms(conv: Conversation) -> list[Atom]:
    """Extract deduplicated, cited atoms from a conversation.

    Sentence-level so a citation quote is short enough to verify by eye.
    Explicit `Conversation.decisions` and `Conversation.outcomes` are trusted
    at full confidence because the capture connector recorded them structurally.
    """
    atoms: list[Atom] = []
    seen: set[tuple[str, str]] = set()

    for turn_index, turn in enumerate(conv.turns):
        for start, end, sentence in split_sentences(turn.text):
            if not MIN_ATOM_CHARS <= len(sentence) <= MAX_ATOM_CHARS:
                continue
            classified = _classify(sentence, turn.role)
            if classified is None:
                continue
            atom_type, confidence, rule = classified
            key = (atom_type, normalize_atom_text(sentence))
            if key in seen:
                continue
            seen.add(key)
            atoms.append(
                Atom(
                    atom_type=atom_type,
                    text=sentence,
                    confidence=confidence,
                    turn_index=turn_index,
                    char_start=start,
                    char_end=end,
                    rule=rule,
                )
            )

    atoms.extend(_structural_atoms(conv, seen))
    return atoms


def _structural_atoms(conv: Conversation, seen: set[tuple[str, str]]) -> list[Atom]:
    """Atoms the capture connector recorded explicitly, not inferred from prose."""
    atoms: list[Atom] = []
    for decision in conv.decisions:
        statement = decision.statement.strip()
        if not statement:
            continue
        key = ("decision", normalize_atom_text(statement))
        if key in seen:
            continue
        seen.add(key)
        turn_index = _clamp_turn(decision.turn_index, conv)
        atoms.append(
            Atom(
                atom_type="decision",
                text=statement,
                confidence=1.0,
                turn_index=turn_index,
                char_start=0,
                char_end=len(statement),
                rule="structural:decision",
            )
        )
    for outcome in conv.outcomes:
        task = outcome.task.strip()
        if not task:
            continue
        text = f"{task} — {outcome.status}" if outcome.status != "unknown" else task
        key = ("outcome", normalize_atom_text(text))
        if key in seen:
            continue
        seen.add(key)
        turn_index = _clamp_turn(outcome.turn_index, conv)
        atoms.append(
            Atom(
                atom_type="outcome",
                text=text,
                confidence=1.0 if outcome.status != "unknown" else 0.6,
                turn_index=turn_index,
                char_start=0,
                char_end=len(text),
                rule="structural:outcome",
            )
        )
    return atoms


def _clamp_turn(turn_index: int, conv: Conversation) -> int:
    if 0 <= turn_index < len(conv.turns):
        return turn_index
    return max(len(conv.turns) - 1, 0)
