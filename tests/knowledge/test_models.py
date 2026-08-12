from pydantic import ValidationError

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship


def test_knowledge_object_requires_citation_for_extracted_data():
    obj = KnowledgeObject(
        id="entity:alice",
        kind="entity",
        label="Alice",
        scope="wiki:default",
        confidence=0.9,
        extraction_method="EXTRACTED",
        citations=[
            Citation(
                source_id="source:note-1",
                chunk_id="chunk:note-1:0",
                span_start=0,
                span_end=5,
                quote="Alice",
            )
        ],
        properties={"entity_type": "person"},
    )
    assert obj.label == "Alice"


def test_knowledge_relationship_rejects_empty_citations():
    try:
        KnowledgeRelationship(
            id="rel:1",
            src_id="entity:a",
            dst_id="entity:b",
            rel_type="related_to",
            scope="wiki:default",
            confidence=0.8,
            extraction_method="INFERRED",
            citations=[],
            properties={},
        )
    except ValidationError as exc:
        assert "citations" in str(exc)
    else:
        raise AssertionError("expected citations validation error")
