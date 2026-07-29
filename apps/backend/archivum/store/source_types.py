"""Source-type registry: the closed set of ingestible source kinds (spec §4)."""

from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    DOCUMENT = "document"
    WEB_PAGE = "web_page"
    CONVERSATION = "conversation"
    REPOSITORY = "repository"
    MESSAGE = "message"
    MEDIA = "media"
    TEST_RUN = "test_run"
    DEPLOYMENT = "deployment"


_MEDIA_MIME_PREFIXES = ("audio/", "video/", "image/")
_MESSAGE_MIMES = frozenset({"message/rfc822", "application/mbox"})


def detect_source_type(
    *,
    origin_uri: str,
    mime: str | None = None,
    explicit: SourceType | str | None = None,
) -> SourceType:
    """Resolve a SourceType from an explicit hint, else origin URI / mime."""
    if explicit is not None:
        return SourceType(explicit)  # raises ValueError on bad string

    uri = origin_uri.lower()
    if uri.startswith("git@") or uri.endswith(".git"):
        return SourceType.REPOSITORY
    if uri.startswith(("http://", "https://")):
        return SourceType.WEB_PAGE

    if mime:
        m = mime.lower()
        if m in _MESSAGE_MIMES:
            return SourceType.MESSAGE
        if m.startswith(_MEDIA_MIME_PREFIXES):
            return SourceType.MEDIA

    return SourceType.DOCUMENT
