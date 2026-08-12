from archivum.capture.schema import Conversation, Decision, Outcome, Turn
from archivum.memory.atoms import (
    atom_id,
    extract_atoms,
    normalize_atom_text,
    split_sentences,
)


def _conv(turns, **kwargs):
    return Conversation(
        session_id=kwargs.pop("session_id", "s1"),
        interface="claude_code_native",
        started_at="2026-08-12T00:00:00Z",
        turns=tuple(turns),
        **kwargs,
    )


def test_split_sentences_preserves_offsets():
    text = "I prefer tabs. Never commit secrets."
    spans = split_sentences(text)
    assert [sentence for _, _, sentence in spans] == [
        "I prefer tabs.",
        "Never commit secrets.",
    ]
    for start, end, sentence in spans:
        assert text[start:end] == sentence


def test_preference_and_constraint_are_classified_from_user_turns():
    conv = _conv(
        [
            Turn(role="user", text="I prefer uv over pip. Never commit secrets to git."),
            Turn(role="assistant", text="Understood."),
        ]
    )
    atoms = extract_atoms(conv)
    by_type = {atom.atom_type: atom.text for atom in atoms}
    assert by_type["preference"] == "I prefer uv over pip."
    assert by_type["constraint"] == "Never commit secrets to git."


def test_assistant_prose_does_not_become_owner_memory():
    conv = _conv([Turn(role="assistant", text="I prefer uv over pip.")])
    assert extract_atoms(conv) == []


def test_decision_wins_over_preference_when_both_match():
    conv = _conv([Turn(role="user", text="We decided I prefer Postgres for this.")])
    atoms = extract_atoms(conv)
    assert [atom.atom_type for atom in atoms] == ["decision"]


def test_assistant_decisions_are_still_evidence_of_a_choice():
    conv = _conv([Turn(role="assistant", text="We decided to use Kuzu for the graph.")])
    assert [atom.atom_type for atom in extract_atoms(conv)] == ["decision"]


def test_hedged_statements_lose_confidence():
    plain = extract_atoms(_conv([Turn(role="user", text="I prefer uv over pip.")]))[0]
    hedged = extract_atoms(
        _conv([Turn(role="user", text="I think I prefer uv over pip.")])
    )[0]
    assert hedged.confidence < plain.confidence


def test_atom_spans_point_at_the_quoted_sentence():
    text = "Hello there friend. I prefer uv over pip."
    conv = _conv([Turn(role="user", text=text)])
    atom = next(a for a in extract_atoms(conv) if a.atom_type == "preference")
    assert text[atom.char_start : atom.char_end] == "I prefer uv over pip."


def test_repeated_sentences_dedupe_within_a_conversation():
    conv = _conv(
        [
            Turn(role="user", text="I prefer uv over pip."),
            Turn(role="user", text="I prefer uv over pip."),
        ]
    )
    assert len(extract_atoms(conv)) == 1


def test_structural_decisions_and_outcomes_are_trusted():
    conv = _conv(
        [Turn(role="user", text="ship it")],
        decisions=(Decision(statement="Adopt Kuzu", rationale="", turn_index=0),),
        outcomes=(Outcome(task="Migrate graph", status="success", turn_index=0),),
    )
    atoms = extract_atoms(conv)
    decision = next(a for a in atoms if a.atom_type == "decision")
    outcome = next(a for a in atoms if a.atom_type == "outcome")
    assert decision.confidence == 1.0
    assert outcome.text == "Migrate graph — success"


def test_short_and_overlong_sentences_are_ignored():
    conv = _conv(
        [
            Turn(role="user", text="I am."),
            Turn(role="user", text="I prefer " + "x" * 500 + "."),
        ]
    )
    assert extract_atoms(conv) == []


def test_atom_id_is_stable_across_casing_and_whitespace():
    left = atom_id("wiki:default", "preference", "I prefer  UV over pip.")
    right = atom_id("wiki:default", "preference", "i prefer uv over pip")
    assert left == right
    assert left != atom_id("wiki:other", "preference", "I prefer uv over pip.")


def test_normalize_strips_terminal_punctuation():
    assert normalize_atom_text("  I Prefer   UV!! ") == "i prefer uv"
