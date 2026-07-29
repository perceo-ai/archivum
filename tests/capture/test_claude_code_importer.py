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
