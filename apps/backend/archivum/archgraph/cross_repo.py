from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from archivum.archgraph.mapper import CandidateRelationship, Provenance

_ENTITY_KINDS: frozenset[str] = frozenset({"symbol", "type", "package", "module"})
_STRONG_KINDS: frozenset[str] = frozenset({"package", "type"})
_WEAK_KINDS: frozenset[str] = frozenset({"symbol", "module"})

# How many distinct scopes trigger AMBIGUOUS for weak keys
_WEAK_AMBIGUOUS_THRESHOLD = 3


def _match_key(kind: str, name: str) -> str:
    """Normalisation key for cross-repo identity: '<kind>:<lowercased-name>'."""
    return f"{kind}:{name.lower()}"


async def resolve_cross_repo(l1) -> list[CandidateRelationship]:
    """Read entity-like objects from *l1* and emit cross-repo identity edges."""
    objects = await l1.list_objects()

    # bucket: match_key → list of (scope, obj_id, kind)
    buckets: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for obj in objects:
        kind = obj.get("kind", "")
        if kind not in _ENTITY_KINDS:
            continue
        label = obj.get("label", "")
        key = _match_key(kind, label)
        buckets[key].append((obj["scope"], obj["id"], kind))

    results: list[CandidateRelationship] = []

    for match_key, entries in buckets.items():
        distinct_scopes = {scope for scope, _, _ in entries}
        if len(distinct_scopes) < 2:
            # all in same scope — no cross-repo edge
            continue

        # pick one representative kind (all entries share the same kind by key construction)
        rep_kind = entries[0][2]
        is_strong = rep_kind in _STRONG_KINDS

        if is_strong:
            method = "INFERRED"
        elif len(distinct_scopes) >= _WEAK_AMBIGUOUS_THRESHOLD:
            method = "AMBIGUOUS"
        else:
            # weak key but only 2 distinct scopes — still emit AMBIGUOUS (safer)
            method = "AMBIGUOUS"

        # emit one edge per distinct pair of object ids, deterministically ordered
        ids = sorted({obj_id for _, obj_id, _ in entries})
        for id_a, id_b in combinations(ids, 2):
            prov = Provenance(
                chunk_id=f"cross_repo:{match_key}",
                span="L0",
                extraction_method=method,
            )
            rel_id = f"{id_a}__same_symbol_as__{id_b}"
            results.append(
                CandidateRelationship(
                    id=rel_id,
                    src_id=id_a,
                    dst_id=id_b,
                    rel_type="same_symbol_as",
                    scope="cross_repo",
                    confidence=1.0 if method == "INFERRED" else 0.5,
                    extraction_method=method,
                    provenance=[prov],
                )
            )

    return results
