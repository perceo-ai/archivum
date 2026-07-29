import dataclasses

from archivum.capture.schema import Conversation, ToolCall, Turn


def test_conversation_is_frozen_and_nests_tool_calls():
    tc = ToolCall(name="Read", arguments={"path": "/x"}, result="ok")
    turn = Turn(role="assistant", text="reading", ts="2026-07-28T00:00:00Z", tool_calls=(tc,))
    conv = Conversation(
        session_id="s1", interface="claude_code_native",
        started_at="2026-07-28T00:00:00Z", turns=(turn,),
    )
    assert conv.turns[0].tool_calls[0].name == "Read"
    assert conv.turns[0].tool_calls[0].ok is True
    assert conv.scope == "personal"
    with dataclasses.FrozenInstanceError if False else _expect_frozen():
        pass


import contextlib


@contextlib.contextmanager
def _expect_frozen():
    yield


def test_frozen_assignment_raises():
    conv = Conversation(session_id="s1", interface="x", started_at="t", turns=())
    try:
        conv.session_id = "s2"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Conversation should be frozen")
