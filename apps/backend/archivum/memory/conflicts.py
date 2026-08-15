"""Deterministic duplicate and conflict detection for memory candidates.

Conflicts create review candidates; the system never silently resolves a
non-trivial contradiction. This is the deterministic half of the evaluator's
conflict step: token overlap catches redundancy, polarity flips catch direct
contradictions. Word-order-blind by design — the LLM evaluator adds semantic
judgment on top when enabled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from archivum.knowledge.models import KnowledgeObject
from archivum.memory.atoms import normalize_atom_text

DUPLICATE_OVERLAP = 0.8
CONFLICT_OVERLAP = 0.5

# Words that carry no identity for overlap purposes.
_STOPWORDS = frozenset(
    "a an the i we my our you your it its is are was were be been being to of "
    "and or for with that this these those in on at by as from".split()
)

# Markers that flip the meaning of an otherwise-similar statement.
_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|don'?t|do\s+not|avoid|stop|without|must\s+not|won'?t)\b"
)


@dataclass(frozen=True)
class RelatedMemory:
    duplicates: list[str]
    conflicts: list[str]


def content_tokens(text: str) -> frozenset[str]:
    normalized = _NEGATION_RE.sub(" ", normalize_atom_text(text))
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9']+", normalized)
        if token not in _STOPWORDS
    )


def has_negation(text: str) -> bool:
    return _NEGATION_RE.search(normalize_atom_text(text)) is not None


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def find_related(
    candidate_id: str,
    candidate_text: str,
    candidate_type: str,
    existing: list[KnowledgeObject],
) -> RelatedMemory:
    """Compare one candidate atom against existing canonical atoms in scope.

    Polarity flips win over raw overlap: "never use tabs" vs "use tabs" is a
    conflict, not a duplicate, even though the content tokens match exactly.
    """
    tokens = content_tokens(candidate_text)
    polarity = has_negation(candidate_text)
    duplicates: list[str] = []
    conflicts: list[str] = []
    for obj in existing:
        if obj.id == candidate_id:
            continue
        other_text = str(obj.properties.get("text", obj.label))
        overlap = _jaccard(tokens, content_tokens(other_text))
        if overlap < CONFLICT_OVERLAP:
            continue
        if has_negation(other_text) != polarity:
            conflicts.append(obj.id)
        elif (
            overlap >= DUPLICATE_OVERLAP
            and obj.properties.get("atom_type") == candidate_type
        ):
            duplicates.append(obj.id)
    return RelatedMemory(duplicates=sorted(duplicates), conflicts=sorted(conflicts))
