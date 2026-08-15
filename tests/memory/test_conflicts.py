from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.memory.conflicts import content_tokens, find_related, has_negation


def _atom(object_id: str, text: str, atom_type: str = "preference") -> KnowledgeObject:
    return KnowledgeObject(
        id=object_id,
        kind="memory_atom",
        label=f"{atom_type}: {text}",
        scope="wiki:default",
        confidence=0.8,
        extraction_method="EXTRACTED",
        citations=[
            Citation(
                source_id="source:x",
                chunk_id="chunk:x",
                span_start=0,
                span_end=len(text),
                quote=text,
            )
        ],
        properties={"atom_type": atom_type, "text": text},
    )


def test_polarity_flip_is_a_conflict_even_with_identical_tokens():
    existing = [_atom("memory:atom:a", "I always use tabs for indentation")]
    related = find_related(
        "memory:atom:b",
        "I never use tabs for indentation",
        "preference",
        existing,
    )
    assert related.conflicts == ["memory:atom:a"]
    assert related.duplicates == []


def test_high_overlap_same_type_is_a_duplicate():
    existing = [_atom("memory:atom:a", "I prefer uv over pip for python installs")]
    related = find_related(
        "memory:atom:b",
        "I prefer uv over pip for my python installs",
        "preference",
        existing,
    )
    assert related.duplicates == ["memory:atom:a"]
    assert related.conflicts == []


def test_unrelated_statements_are_neither():
    existing = [_atom("memory:atom:a", "I prefer uv over pip")]
    related = find_related(
        "memory:atom:b", "My deploy target is Hetzner", "fact", existing
    )
    assert related.duplicates == []
    assert related.conflicts == []


def test_the_candidate_never_matches_itself():
    existing = [_atom("memory:atom:same", "I prefer uv over pip")]
    related = find_related(
        "memory:atom:same", "I prefer uv over pip", "preference", existing
    )
    assert related.duplicates == []
    assert related.conflicts == []


def test_token_and_negation_helpers():
    assert "tabs" in content_tokens("I never use tabs")
    assert "never" not in content_tokens("I never use tabs")
    assert has_negation("Do not commit secrets")
    assert not has_negation("Commit messages stay short")
