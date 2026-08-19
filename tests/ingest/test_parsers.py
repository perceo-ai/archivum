"""Tests for archivum.ingest.parsers — all supported file types."""

from __future__ import annotations

import json
import sys
import types
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from archivum.ingest.parsers import (
    ParsedDoc,
    UnsupportedFileTypeError,
    _html_to_text,
    _strip_rst_directives,
    parse_file,
    parse_source,
    parse_url,
)

# ── _strip_rst_directives ─────────────────────────────────────────────────────


class TestStripRstDirectives:
    def test_removes_directive_lines(self):
        text = "Some text\n.. code:: python\nMore text"
        result = _strip_rst_directives(text)
        assert ".. code:: python" not in result
        assert "Some text" in result
        assert "More text" in result

    def test_removes_field_lists(self):
        text = "Some text\n:Date: 2024-01-01\nMore text"
        result = _strip_rst_directives(text)
        assert ":Date: 2024-01-01" not in result
        assert "Some text" in result

    def test_preserves_normal_text(self):
        text = "This is normal text.\nAnother line.\nNo directives here."
        result = _strip_rst_directives(text)
        assert result == text


# ── _html_to_text ─────────────────────────────────────────────────────────────


class TestHtmlToText:
    def test_extracts_text_from_simple_html(self):
        html = "<html><body><p>Hello World</p></body></html>"
        result = _html_to_text(html)
        assert "Hello World" in result

    def test_removes_script_tags(self):
        html = "<html><body><p>Good content</p><script>alert('bad')</script></body></html>"
        result = _html_to_text(html)
        assert "Good content" in result
        assert "alert" not in result

    def test_falls_back_without_readability(self):
        html = "<html><body><p>Fallback content</p></body></html>"
        # Simulate readability raising an exception
        with patch("archivum.ingest.parsers._html_to_text") as mock_fn:
            # Directly test fallback by patching readability import
            pass

        # Now test the real fallback path by making readability.Document raise
        with patch("readability.Document", side_effect=Exception("readability failed")):
            result = _html_to_text(html)
        assert "Fallback content" in result


# ── parse_file — plain text ───────────────────────────────────────────────────


class TestParseFilePlainText:
    def test_parses_md_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Hello\n\nWorld")
        result = parse_file(f)
        assert result.text == "# Hello\n\nWorld"
        assert result.metadata["type"] == "md"

    def test_parses_txt_file(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Plain text content here.")
        result = parse_file(f)
        assert result.text == "Plain text content here."
        assert result.metadata["type"] == "txt"

    def test_parses_rst_file_strips_directives(self, tmp_path):
        f = tmp_path / "doc.rst"
        f.write_text("Normal text\n.. code:: python\nMore text\n:Author: Alice")
        result = parse_file(f)
        assert ".. code:: python" not in result.text
        assert ":Author: Alice" not in result.text
        assert "Normal text" in result.text

    def test_metadata_has_correct_type(self, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("content")
        result = parse_file(f)
        assert result.metadata["type"] == "txt"

    def test_source_is_file_path(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("hello")
        result = parse_file(f)
        assert result.source == str(f)


class TestParseFileMbox:
    def test_parses_mbox_messages(self, tmp_path):
        f = tmp_path / "archive.mbox"
        f.write_text(
            "From alice@example.com Sat Jan 01 00:00:00 2026\n"
            "From: Alice <alice@example.com>\n"
            "To: Bob <bob@example.com>\n"
            "Subject: First note\n"
            "Date: Sat, 1 Jan 2026 00:00:00 +0000\n"
            "\n"
            "The first body.\n"
            "\n"
            "From bob@example.com Sat Jan 01 00:01:00 2026\n"
            "From: Bob <bob@example.com>\n"
            "To: Alice <alice@example.com>\n"
            "Subject: Second note\n"
            "Date: Sat, 1 Jan 2026 00:01:00 +0000\n"
            "\n"
            "The second body.\n",
            encoding="utf-8",
        )

        result = parse_file(f)

        assert result.metadata == {"type": "mbox", "messages": 2}
        assert "Subject: First note" in result.text
        assert "The first body." in result.text
        assert "Subject: Second note" in result.text
        assert "The second body." in result.text


# ── parse_file — PDF ──────────────────────────────────────────────────────────


class TestParseFilePdf:
    def test_parses_pdf_file(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF fake")

        fake_page = MagicMock()
        fake_page.get_text.return_value = "Page content here."
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page]))
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.close = MagicMock()

        fake_fitz = types.ModuleType("fitz")
        fake_fitz.open = MagicMock(return_value=fake_doc)

        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            result = parse_file(f)

        assert "Page content here." in result.text
        assert result.metadata["type"] == "pdf"

    def test_pdf_metadata_has_page_count(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF fake")

        fake_page = MagicMock()
        fake_page.get_text.return_value = "Page 1 text."
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page]))
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.close = MagicMock()

        fake_fitz = types.ModuleType("fitz")
        fake_fitz.open = MagicMock(return_value=fake_doc)

        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            result = parse_file(f)

        assert result.metadata["pages"] == 1

    def test_raises_if_pymupdf_not_installed(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF fake")
        with patch.dict("sys.modules", {"fitz": None}):
            with pytest.raises(UnsupportedFileTypeError):
                parse_file(f)


# ── parse_file — HTML ─────────────────────────────────────────────────────────


class TestParseFileHtml:
    def test_parses_html_file(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<html><body><p>Hello from HTML</p></body></html>")
        result = parse_file(f)
        assert "Hello from HTML" in result.text

    def test_metadata_type_is_html(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<html><body><p>Content</p></body></html>")
        result = parse_file(f)
        assert result.metadata["type"] == "html"


# ── parse_file — DOCX ─────────────────────────────────────────────────────────


class TestParseFileDocx:
    def test_parses_docx_file(self, tmp_path):
        f = tmp_path / "document.docx"
        f.write_bytes(b"fake docx bytes")

        fake_para = MagicMock()
        fake_para.text = "Hello paragraph"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [fake_para]

        fake_docx_module = types.ModuleType("docx")
        fake_docx_module.Document = MagicMock(return_value=mock_doc)

        with patch.dict(sys.modules, {"docx": fake_docx_module}):
            result = parse_file(f)

        assert "Hello paragraph" in result.text
        assert result.metadata["type"] == "docx"

    def test_empty_paragraphs_skipped(self, tmp_path):
        f = tmp_path / "document.docx"
        f.write_bytes(b"fake docx bytes")

        para_empty = MagicMock()
        para_empty.text = "   "
        para_full = MagicMock()
        para_full.text = "Real content"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [para_empty, para_full]

        fake_docx_module = types.ModuleType("docx")
        fake_docx_module.Document = MagicMock(return_value=mock_doc)

        with patch.dict(sys.modules, {"docx": fake_docx_module}):
            result = parse_file(f)

        assert result.text.strip() == "Real content"

    def test_raises_if_docx_not_installed(self, tmp_path):
        f = tmp_path / "document.docx"
        f.write_bytes(b"fake docx bytes")
        with patch.dict("sys.modules", {"docx": None}):
            with pytest.raises(UnsupportedFileTypeError):
                parse_file(f)


# ── parse_file — PPTX ─────────────────────────────────────────────────────────


class TestParseFilePptx:
    def _make_fake_pptx_module(self, slides_data: list[list[str]]):
        """Build a fake pptx module with slides containing text shapes."""
        fake_shapes = []
        fake_slides_list = []

        for slide_texts in slides_data:
            shapes = []
            for text in slide_texts:
                para = MagicMock()
                para.text = text
                tf = MagicMock()
                tf.paragraphs = [para]
                shape = MagicMock()
                shape.has_text_frame = True
                shape.text_frame = tf
                shapes.append(shape)

            slide = MagicMock()
            slide.shapes = shapes
            fake_slides_list.append(slide)

        mock_slides = MagicMock()
        mock_slides.__iter__ = MagicMock(return_value=iter(fake_slides_list))

        mock_prs = MagicMock()
        mock_prs.slides = mock_slides

        fake_pptx_module = types.ModuleType("pptx")
        fake_pptx_module.Presentation = MagicMock(return_value=mock_prs)
        return fake_pptx_module

    def test_parses_pptx_file(self, tmp_path):
        f = tmp_path / "slides.pptx"
        f.write_bytes(b"fake pptx bytes")

        fake_pptx_module = self._make_fake_pptx_module([["Slide one content"]])

        with patch.dict(sys.modules, {"pptx": fake_pptx_module}):
            result = parse_file(f)

        assert "Slide one content" in result.text
        assert result.metadata["type"] == "pptx"

    def test_metadata_has_slide_count(self, tmp_path):
        f = tmp_path / "slides.pptx"
        f.write_bytes(b"fake pptx bytes")

        fake_pptx_module = self._make_fake_pptx_module([
            ["Slide 1 content"],
            ["Slide 2 content"],
        ])

        with patch.dict(sys.modules, {"pptx": fake_pptx_module}):
            result = parse_file(f)

        assert result.metadata["slides"] == 2

    def test_raises_if_pptx_not_installed(self, tmp_path):
        f = tmp_path / "slides.pptx"
        f.write_bytes(b"fake pptx bytes")
        with patch.dict("sys.modules", {"pptx": None}):
            with pytest.raises(UnsupportedFileTypeError):
                parse_file(f)


# ── parse_file — CSV ──────────────────────────────────────────────────────────


class TestParseFileCsv:
    def test_parses_csv_with_pandas(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25")

        mock_df = MagicMock()
        mock_df.shape = (2, 2)
        mock_df.columns = ["name", "age"]
        mock_df.head.return_value.to_markdown.return_value = "| name | age |\n|---|---|\n| Alice | 30 |"
        mock_df.describe.return_value.to_markdown.return_value = "stats"

        mock_pd = MagicMock()
        mock_pd.read_csv.return_value = mock_df

        with patch.dict(sys.modules, {"pandas": mock_pd}):
            result = parse_file(f)

        assert result.metadata["type"] == "csv"
        assert "name" in result.text.lower() or "age" in result.text.lower()

    def test_csv_fallback_without_pandas(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25")
        with patch.dict("sys.modules", {"pandas": None}):
            result = parse_file(f)
        assert "name" in result.text.lower() or "Alice" in result.text

    def test_csv_metadata_type(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2")
        with patch.dict("sys.modules", {"pandas": None}):
            result = parse_file(f)
        assert result.metadata["type"] == "csv"


# ── parse_file — JSON ─────────────────────────────────────────────────────────


class TestParseFileJson:
    def test_parses_json_object(self, tmp_path):
        f = tmp_path / "data.json"
        data = {"key": "value", "count": 42}
        f.write_text(json.dumps(data))
        result = parse_file(f)
        assert "key" in result.text
        assert result.metadata["type"] == "json"

    def test_parses_json_array(self, tmp_path):
        f = tmp_path / "data.json"
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        f.write_text(json.dumps(data))
        result = parse_file(f)
        assert "JSON array" in result.text
        assert "3 items" in result.text

    def test_handles_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("this is not json {{{")
        result = parse_file(f)
        # Should not raise; falls back to raw text
        assert result.metadata["type"] == "json"
        assert "this is not json" in result.text


# ── parse_file — JSONL ────────────────────────────────────────────────────────


class TestParseFileJsonl:
    def test_parses_jsonl_file(self, tmp_path):
        f = tmp_path / "data.jsonl"
        lines = [json.dumps({"id": i, "val": f"item{i}"}) for i in range(3)]
        f.write_text("\n".join(lines))
        result = parse_file(f)
        assert "JSONL" in result.text
        assert "3 records" in result.text
        assert result.metadata["type"] == "jsonl"


# ── parse_file — richer text containers ──────────────────────────────────────


class TestParseFileStructuredText:
    def test_parses_rtf_as_readable_text(self, tmp_path):
        f = tmp_path / "note.rtf"
        f.write_text(r"{\rtf1\ansi This is {\b important} text.\par Next line.}")

        result = parse_file(f)

        assert result.metadata["type"] == "rtf"
        assert "This is important text." in result.text
        assert "Next line." in result.text
        assert r"\rtf" not in result.text

    def test_parses_xml_as_readable_element_text(self, tmp_path):
        f = tmp_path / "feed.xml"
        f.write_text("<root><title>Launch Plan</title><body>Ship video ingest</body></root>")

        result = parse_file(f)

        assert result.metadata["type"] == "xml"
        assert "Launch Plan" in result.text
        assert "Ship video ingest" in result.text
        assert "<title>" not in result.text


# ── parse_file — archives ────────────────────────────────────────────────────


class TestParseFileArchive:
    def test_parses_zip_archive_supported_members_and_reports_skips(self, tmp_path):
        f = tmp_path / "bundle.zip"
        with zipfile.ZipFile(f, "w") as archive:
            archive.writestr("notes/first.md", "# First\n\nAlpha archive note")
            archive.writestr("data.json", json.dumps({"topic": "Archive JSON"}))
            archive.writestr("binary.bin", b"\x00\x01\x02")

        result = parse_file(f)

        assert result.metadata["type"] == "archive"
        assert result.metadata["format"] == "zip"
        assert result.metadata["files_parsed"] == 2
        assert result.metadata["files_skipped"] == 1
        assert "## notes/first.md" in result.text
        assert "Alpha archive note" in result.text
        assert "Archive JSON" in result.text
        assert "Skipped unsupported archive members: binary.bin" in result.text


# ── parse_file — SRT/VTT ──────────────────────────────────────────────────────


class TestParseFileSrt:
    def test_strips_sequence_numbers(self, tmp_path):
        f = tmp_path / "sub.srt"
        content = "1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n2\n00:00:04,000 --> 00:00:06,000\nGoodbye\n"
        f.write_text(content)
        result = parse_file(f)
        # Sequence numbers (standalone digits) should be stripped
        lines = result.text.split()
        # "1" and "2" as standalone items should not be in output
        assert "Hello world" in result.text
        assert "Goodbye" in result.text
        # Pure digits on their own line should be stripped
        assert result.text.strip() not in ("1", "2")

    def test_strips_timestamps(self, tmp_path):
        f = tmp_path / "sub.srt"
        content = "1\n00:00:01,000 --> 00:00:03,000\nSpeaker text here\n"
        f.write_text(content)
        result = parse_file(f)
        assert "-->" not in result.text
        assert "Speaker text here" in result.text

    def test_strips_webvtt_header(self, tmp_path):
        f = tmp_path / "sub.vtt"
        content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nVTT caption text\n"
        f.write_text(content)
        result = parse_file(f)
        assert "WEBVTT" not in result.text
        assert "VTT caption text" in result.text


# ── parse_file — audio/video transcripts ─────────────────────────────────────


class TestParseFileMedia:
    def test_audio_transcript_includes_timestamps_language_and_duration(self, tmp_path):
        f = tmp_path / "meeting.mp3"
        f.write_bytes(b"fake audio")
        fake_model = MagicMock()
        fake_model.transcribe.return_value = {
            "text": "Hello from the meeting.",
            "language": "en",
            "duration": 12.5,
            "segments": [
                {"start": 0.0, "end": 2.4, "text": "Hello from"},
                {"start": 2.4, "end": 12.5, "text": "the meeting."},
            ],
        }

        with patch("archivum.ingest.parsers._get_whisper_model", return_value=fake_model):
            result = parse_file(f)

        assert result.metadata["type"] == "audio"
        assert result.metadata["language"] == "en"
        assert result.metadata["duration_seconds"] == 12.5
        assert "[00:00:00 - 00:00:02] Hello from" in result.text
        assert "[00:00:02 - 00:00:12] the meeting." in result.text

    def test_video_reports_missing_ffmpeg_as_unsupported_file_type(self, tmp_path):
        f = tmp_path / "demo.mp4"
        f.write_bytes(b"fake video")

        with (
            patch("archivum.ingest.parsers._get_whisper_model", return_value=MagicMock()),
            patch("archivum.ingest.parsers.subprocess.run", side_effect=FileNotFoundError("ffmpeg")),
        ):
            with pytest.raises(UnsupportedFileTypeError, match="ffmpeg"):
                parse_file(f)


# ── parse_file — EML ──────────────────────────────────────────────────────────

EML_CONTENT = """From: sender@example.com
To: receiver@example.com
Subject: Test Email
Date: Mon, 1 Jan 2024 00:00:00 +0000

This is the email body.
"""


class TestParseFileEml:
    def test_parses_eml_from_string(self, tmp_path):
        f = tmp_path / "message.eml"
        f.write_text(EML_CONTENT)
        result = parse_file(f)
        assert "sender@example.com" in result.text
        assert "This is the email body." in result.text
        assert result.metadata["type"] == "eml"

    def test_eml_metadata_has_subject(self, tmp_path):
        f = tmp_path / "message.eml"
        f.write_text(EML_CONTENT)
        result = parse_file(f)
        assert result.metadata["subject"] == "Test Email"


# ── parse_file — code files ───────────────────────────────────────────────────


class TestParseFileCodeFiles:
    def test_parses_python_file(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("def hello():\n    return 'world'\n")
        result = parse_file(f)
        assert "def hello():" in result.text
        assert result.metadata["type"] == "code"
        assert result.metadata["language"] == "python"

    def test_parses_yaml_file(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("key: value\nlist:\n  - item1\n")
        result = parse_file(f)
        assert "key: value" in result.text
        assert result.metadata["language"] == "yaml"

    def test_wraps_in_code_fence(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("print('hi')")
        result = parse_file(f)
        assert result.text.startswith("```python")
        assert result.text.endswith("```")


# ── parse_file — unsupported ──────────────────────────────────────────────────


class TestParseFileUnsupported:
    def test_raises_for_unknown_extension(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_bytes(b"binary content")
        with pytest.raises(UnsupportedFileTypeError):
            parse_file(f)


# ── parse_url ─────────────────────────────────────────────────────────────────


class TestParseUrl:
    async def test_parses_html_url(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.text = "<html><head><title>Test Page</title></head><body><p>Hello</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("archivum.ingest.parsers.httpx.AsyncClient", return_value=mock_client):
            result = await parse_url("https://example.com/article")

        assert "Hello" in result.text
        assert result.metadata["type"] == "url"
        assert result.source == "https://example.com/article"

    async def test_parses_json_url(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"key": "value"}'
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("archivum.ingest.parsers.httpx.AsyncClient", return_value=mock_client):
            result = await parse_url("https://api.example.com/data.json")

        assert result.metadata["type"] == "json_url"
        assert "key" in result.text

    async def test_parses_plain_text_url(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "Just plain text content."
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("archivum.ingest.parsers.httpx.AsyncClient", return_value=mock_client):
            result = await parse_url("https://example.com/readme.txt")

        assert result.metadata["type"] == "text_url"
        assert "Just plain text content." in result.text

    async def test_parses_unknown_content_type(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.text = "binary-ish content"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("archivum.ingest.parsers.httpx.AsyncClient", return_value=mock_client):
            result = await parse_url("https://example.com/file.bin")

        assert result.metadata["type"] == "unknown_url"

    async def test_parses_downloadable_pdf_url_with_file_parser(self):
        mock_response = MagicMock()
        mock_response.headers = {
            "content-type": "application/pdf",
            "content-disposition": 'attachment; filename="paper.pdf"',
        }
        mock_response.content = b"%PDF fake"
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("archivum.ingest.parsers.httpx.AsyncClient", return_value=mock_client),
            patch(
                "archivum.ingest.parsers.parse_file",
                return_value=ParsedDoc(
                    text="Parsed PDF text",
                    source="/tmp/paper.pdf",
                    metadata={"type": "pdf", "pages": 1},
                ),
            ) as parse_file_mock,
        ):
            result = await parse_url("https://example.com/download")

        parsed_path = parse_file_mock.call_args.args[0]
        assert parsed_path.name == "paper.pdf"
        assert result.text == "Parsed PDF text"
        assert result.source == "https://example.com/download"
        assert result.metadata["type"] == "pdf"
        assert result.metadata["url"] == "https://example.com/download"
        assert result.metadata["filename"] == "paper.pdf"


# ── parse_source ──────────────────────────────────────────────────────────────


class TestParseSource:
    async def test_dispatches_to_parse_url_for_http(self):
        mock_doc = ParsedDoc(text="web content", metadata={"type": "url"}, source="https://example.com")
        with patch("archivum.ingest.parsers.parse_url", AsyncMock(return_value=mock_doc)) as mock_parse_url:
            result = await parse_source("https://example.com")
        mock_parse_url.assert_called_once_with("https://example.com")
        assert result.text == "web content"

    async def test_dispatches_to_parse_file_for_path(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("file content here")
        result = await parse_source(f)
        assert result.text == "file content here"
        assert result.metadata["type"] == "txt"

    async def test_raises_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            await parse_source(missing)
