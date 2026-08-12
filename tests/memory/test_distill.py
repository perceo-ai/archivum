import pytest

from archivum.capture.schema import Conversation, Turn
from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.memory import distill
from archivum.memory.atoms import Atom, extract_atoms


def _conv(texts, session_id="s1"):
    return Conversation(
        session_id=session_id,
        interface="claude_code_native",
        started_at="2026-08-12T00:00:00Z",
        turns=tuple(Turn(role="user", text=text) for text in texts),
    )


def _records(conv, *, threshold=0.7, prior=None, session_id=None):
    atoms = extract_atoms(conv)
    chunk_ids = [f"chunk:{i}" for i in range(len(conv.turns))]
    return distill.build_atom_objects(
        atoms,
        scope="wiki:default",
        source_id="source:1",
        session_id=session_id or conv.session_id,
        anchors=distill.turn_anchors(conv, chunk_ids),
        chunk_offsets={chunk_id: index * 100 for index, chunk_id in enumerate(chunk_ids)},
        threshold=threshold,
        prior=prior,
    )


def test_atom_citation_offsets_account_for_the_role_prefix():
    conv = _conv(["I prefer uv over pip."])
    record = _records(conv)[0]
    citation = record.object.citations[0]
    # chunk 0 starts at offset 0, the rendered block is prefixed with "[user] ".
    assert citation.chunk_id == "chunk:0"
    assert citation.span_start == len("[user] ")
    assert citation.span_end == citation.span_start + len("I prefer uv over pip.")
    assert citation.quote == "I prefer uv over pip."


def test_weak_atoms_are_not_accepted_for_canonical_write():
    conv = _conv(["I think I prefer uv over pip."])
    record = _records(conv, threshold=0.7)[0]
    assert record.object.confidence < 0.7
    assert record.accepted is False


def test_recurrence_across_sessions_raises_confidence_and_occurrences():
    conv = _conv(["I prefer uv over pip."], session_id="s1")
    first = _records(conv)[0]
    assert first.object.properties["occurrences"] == 1

    second = _records(
        _conv(["I prefer uv over pip."], session_id="s2"),
        prior={first.object.id: first.object},
        session_id="s2",
    )[0]
    assert second.object.properties["sessions"] == ["s1", "s2"]
    assert second.object.confidence > first.object.confidence
    assert len(second.object.citations) == 1  # same source, same span, deduped


def test_scenario_aggregates_only_accepted_atoms():
    conv = _conv(["I prefer uv over pip.", "I think I prefer tabs."])
    records = _records(conv)
    scenario = distill.build_scenario(
        records, scope="wiki:default", key="archivum", name="Archivum"
    )
    assert scenario is not None
    assert scenario.properties["atom_count"] == 1
    assert scenario.properties["by_type"]["preference"] == ["I prefer uv over pip."]
    assert scenario.extraction_method == "INFERRED"


def test_scenario_is_none_when_nothing_was_accepted():
    records = _records(_conv(["I think I prefer tabs."]))
    assert distill.build_scenario(
        records, scope="wiki:default", key="k", name="K"
    ) is None


def _atom_object(object_id, *, atom_type, occurrences, text="statement"):
    return KnowledgeObject(
        id=object_id,
        kind="memory_atom",
        label=f"{atom_type}: {text}",
        scope="wiki:default",
        confidence=0.8,
        extraction_method="EXTRACTED",
        citations=[
            Citation(
                source_id="source:1",
                chunk_id="chunk:0",
                span_start=0,
                span_end=1,
                quote=text,
            )
        ],
        properties={
            "layer": "L1",
            "atom_type": atom_type,
            "text": text,
            "occurrences": occurrences,
        },
    )


def test_persona_requires_recurrence_across_sessions():
    once = [_atom_object("a", atom_type="preference", occurrences=1)]
    assert distill.build_persona(once, scope="wiki:default") is None

    twice = [_atom_object("a", atom_type="preference", occurrences=2)]
    persona = distill.build_persona(twice, scope="wiki:default")
    assert persona is not None
    assert persona.id == distill.PERSONA_ID
    assert persona.properties["trait_count"] == 1
    assert persona.properties["revision"] == 1


def test_persona_ignores_decision_and_outcome_atoms():
    atoms = [
        _atom_object("d", atom_type="decision", occurrences=5),
        _atom_object("o", atom_type="outcome", occurrences=5),
    ]
    assert distill.build_persona(atoms, scope="wiki:default") is None


def test_persona_revision_increments_from_prior():
    atoms = [_atom_object("a", atom_type="fact", occurrences=3)]
    first = distill.build_persona(atoms, scope="wiki:default")
    second = distill.build_persona(atoms, scope="wiki:default", prior=first)
    assert second.properties["revision"] == 2


def test_chat_markdown_flags_pending_review_items():
    conv = _conv(["I prefer uv over pip.", "I think I prefer tabs."])
    markdown = distill.render_chat_memory_markdown(
        session_id="s1",
        interface="claude_code_native",
        records=_records(conv),
        source_id="source:1",
    )
    assert "type: chat-memory" in markdown
    assert "I prefer uv over pip." in markdown
    assert "_(pending review)_" in markdown


def test_turn_anchors_stop_at_the_available_chunks():
    conv = _conv(["one two three", "four five six"])
    anchors = distill.turn_anchors(conv, ["chunk:0"])
    assert set(anchors) == {0}


def test_citation_falls_back_to_the_source_when_a_turn_has_no_chunk():
    atom = Atom(
        atom_type="fact",
        text="I am here",
        confidence=0.8,
        turn_index=9,
        char_start=0,
        char_end=9,
        rule="test",
    )
    citation = distill.atom_citation(
        atom, source_id="source:1", anchors={}, chunk_offsets={}
    )
    assert citation.chunk_id == "source:1"
    assert citation.span_start is None


@pytest.mark.parametrize("renderer", [distill.render_scenario_markdown])
def test_scenario_markdown_lists_atoms_by_type(renderer):
    conv = _conv(["I prefer uv over pip.", "We decided to use Kuzu."])
    scenario = distill.build_scenario(
        _records(conv), scope="wiki:default", key="archivum", name="Archivum"
    )
    markdown = renderer(scenario)
    assert "## Preferences" in markdown
    assert "## Decisions" in markdown
