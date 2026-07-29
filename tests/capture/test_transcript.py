from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.capture.transcript import render_transcript


def _conv():
    tc = ToolCall(name="Edit", arguments={"path": "/a.py"}, result="written")
    return Conversation(
        session_id="s1", interface="x", started_at="t",
        turns=(
            Turn(role="user", text="do X", ts="t"),
            Turn(role="assistant", text="did X", ts="t", tool_calls=(tc,)),
        ),
    )


def test_one_span_per_turn_and_offsets_are_exact():
    text, spans = render_transcript(_conv())
    assert len(spans) == 2
    for start, end, block in spans:
        assert text[start:end] == block
    assert "[user] do X" in spans[0][2]
    assert "Edit" in spans[1][2] and "written" in spans[1][2]


def test_empty_conversation_renders_empty():
    conv = Conversation(session_id="s", interface="x", started_at="t", turns=())
    text, spans = render_transcript(conv)
    assert text == "" and spans == []
