from pathlib import Path

from archivum.capture.importers.chatgpt import ChatGptImporter

FIX = Path(__file__).parent.parent / "fixtures" / "capture" / "chatgpt_export.json"


def test_can_handle_json_export():
    assert ChatGptImporter().can_handle(FIX) is True
    assert ChatGptImporter().can_handle(Path("s.jsonl")) is False


def test_parses_in_time_order_without_reasoning():
    conv = ChatGptImporter().parse(FIX).conversations[0]
    texts = [t.text for t in conv.turns]
    assert texts[0] == "is sqlite good for this?"
    assert any("SQLite fits" in t for t in texts)
    assert all("hidden reasoning" not in t for t in texts)
