import json
from pathlib import Path

from archivum.capture.importers.claude_code import ClaudeCodeImporter

FIX = Path(__file__).parent.parent / "fixtures" / "capture" / "claude_code_session.jsonl"


def test_can_handle_jsonl_only():
    imp = ClaudeCodeImporter()
    assert imp.can_handle(Path("s.jsonl")) is True
    assert imp.can_handle(Path("s.json")) is False


def test_parses_turns_tool_calls_and_session_id():
    res = ClaudeCodeImporter().parse(FIX)
    assert res.interface == "claude_code_import"
    conv = res.conversations[0]
    assert conv.session_id == "abc123"
    assert conv.turns[0].text == "add pytest config"
    assert conv.turns[1].tool_calls[0].name == "Edit"
    assert conv.turns[1].tool_calls[0].result == "file updated"


def test_no_thinking_in_parsed_turns():
    conv = ClaudeCodeImporter().parse(FIX).conversations[0]
    joined = " ".join(t.text for t in conv.turns)
    assert "internal plan" not in joined


def test_user_text_bundled_with_tool_result_is_preserved(tmp_path):
    """A user message with both tool_result and text blocks must emit a turn for the text."""
    lines = [
        json.dumps({
            "type": "assistant",
            "sessionId": "sess1",
            "timestamp": "2026-07-28T00:00:00Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "/x"}},
                ],
            },
        }),
        json.dumps({
            "type": "user",
            "sessionId": "sess1",
            "timestamp": "2026-07-28T00:00:01Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "done"},
                    {"type": "text", "text": "now do the next thing"},
                ],
            },
        }),
    ]
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text("\n".join(lines), encoding="utf-8")

    res = ClaudeCodeImporter().parse(jsonl)
    conv = res.conversations[0]

    # tool_result must be filled into the assistant turn's ToolCall
    assistant_turn = next(t for t in conv.turns if t.role == "assistant")
    assert assistant_turn.tool_calls[0].call_id == "t1"
    assert assistant_turn.tool_calls[0].result == "done"

    # visible user text must appear as a separate turn
    user_turns = [t for t in conv.turns if t.role == "user"]
    assert any(t.text == "now do the next thing" for t in user_turns), (
        f"Expected 'now do the next thing' in user turns, got: {[t.text for t in user_turns]}"
    )
