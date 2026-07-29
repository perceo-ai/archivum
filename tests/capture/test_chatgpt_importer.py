from pathlib import Path

import pytest

from archivum.capture.importers.chatgpt import ChatGptImporter

FIX = Path(__file__).parent.parent / "fixtures" / "capture" / "chatgpt_export.json"


def test_can_handle_matches_json_suffix_without_reading():
    imp = ChatGptImporter()
    assert imp.can_handle(FIX) is True
    assert imp.can_handle(Path("s.jsonl")) is False
    # Suffix-only dispatch: does not read the file, so a missing .json still matches.
    assert imp.can_handle(Path("does-not-exist.json")) is True


def test_parse_raises_valueerror_on_malformed_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all", encoding="utf-8")
    with pytest.raises(ValueError):
        ChatGptImporter().parse(bad)


def test_parse_raises_valueerror_on_non_export_shape(tmp_path):
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"not": "a list of mappings"}', encoding="utf-8")
    with pytest.raises(ValueError):
        ChatGptImporter().parse(wrong)


def test_parses_in_time_order_without_reasoning():
    conv = ChatGptImporter().parse(FIX).conversations[0]
    texts = [t.text for t in conv.turns]
    assert texts[0] == "is sqlite good for this?"
    assert any("SQLite fits" in t for t in texts)
    assert all("hidden reasoning" not in t for t in texts)
