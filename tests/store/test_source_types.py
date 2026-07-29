"""Tests for the source-type registry."""

from __future__ import annotations

import pytest

from archivum.store.source_types import SourceType, detect_source_type


def test_explicit_enum_wins():
    assert (
        detect_source_type(origin_uri="whatever", explicit=SourceType.DEPLOYMENT)
        == SourceType.DEPLOYMENT
    )


def test_explicit_string_is_coerced():
    assert (
        detect_source_type(origin_uri="whatever", explicit="repository")
        == SourceType.REPOSITORY
    )


def test_http_url_is_web_page():
    assert detect_source_type(origin_uri="https://example.com/x") == SourceType.WEB_PAGE


def test_git_uri_is_repository():
    assert detect_source_type(origin_uri="git@github.com:me/repo.git") == SourceType.REPOSITORY


def test_media_by_mime():
    assert detect_source_type(origin_uri="file:///a.mp4", mime="video/mp4") == SourceType.MEDIA


def test_message_by_mime():
    assert detect_source_type(origin_uri="file:///a.eml", mime="message/rfc822") == SourceType.MESSAGE


def test_default_is_document():
    assert detect_source_type(origin_uri="file:///notes.txt", mime="text/plain") == SourceType.DOCUMENT


def test_invalid_explicit_raises():
    with pytest.raises(ValueError):
        detect_source_type(origin_uri="x", explicit="not-a-type")
