import pytest

from archivum.capture.redaction import (
    HIDDEN_BLOCK_TYPES,
    redact_turn_text,
    visible_text_from_blocks,
)


def test_drops_thinking_blocks_keeps_text_and_tool_result():
    blocks = [
        {"type": "thinking", "thinking": "secret chain of thought"},
        {"type": "text", "text": "here is the answer"},
        {"type": "tool_result", "content": "file updated"},
    ]
    out = visible_text_from_blocks(blocks)
    assert "secret" not in out
    assert "here is the answer" in out
    assert "file updated" in out


def test_redacts_inline_reasoning_tags():
    assert "secret" not in redact_turn_text("a <thinking>secret</thinking> b")
    assert "why" not in redact_turn_text("x <reasoning>why</reasoning> y")


@pytest.mark.parametrize("tag", sorted(HIDDEN_BLOCK_TYPES))
def test_every_hidden_type_is_stripped_inline(tag):
    # Inline stripping must cover EVERY hidden block type (incl. thoughts,
    # redacted_thinking), not just thinking/reasoning — else it leaks to L0.
    assert "leak" not in redact_turn_text(f"pre <{tag}>leak</{tag}> post")
    assert redact_turn_text(f"<{tag.upper()}>leak</{tag.upper()}>") == ""


def test_plain_string_passthrough():
    assert visible_text_from_blocks("hello") == "hello"
