from archivum.capture.canonical import content_hash, to_canonical_bytes
from archivum.capture.schema import Conversation, Turn
from archivum.store.hashing import sha256_bytes


def _conv(meta):
    return Conversation(
        session_id="s1", interface="x", started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="hi", ts="2026-07-28T00:00:00Z"),),
        metadata=meta,
    )


def test_hash_is_stable_ignores_metadata_and_matches_sha256_of_bytes():
    a = content_hash(_conv({"a": 1}))
    b = content_hash(_conv({"b": 2}))
    assert a == b and len(a) == 64
    assert a == sha256_bytes(to_canonical_bytes(_conv({"a": 1})))


def test_bytes_are_sorted_compact_json():
    raw = to_canonical_bytes(_conv({}))
    assert raw.startswith(b"{") and b'"interface"' in raw
    assert b'"metadata"' not in raw
