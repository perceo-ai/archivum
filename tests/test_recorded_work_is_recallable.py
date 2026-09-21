"""What an agent explicitly records must come back.

`record_work` is an agent stating that something mattered. That statement was
being run through `classify_session`, a keyword classifier written to *infer*
intent from a raw transcript nobody annotated. If the agent's own words missed
the magic words — "bug", "error", "fail", "fix" — the knowledge was dropped and
`record_work` still answered `recorded: true`.

Two of the three things this product exists to remember failed that way: a
plainly described failure with no keyword in it, and a decision.

Inference is right for a transcript. It is wrong for a deliberate call, where
the caller already decided.
"""

from __future__ import annotations

import pytest

from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.fixes import extract_fix


def _stated(request: str, *, changed: str = "src/thing.py", verified: str = "pytest") -> Conversation:
    """A conversation shaped the way `record_work` synthesises one."""
    calls = (
        ToolCall(name="Bash", arguments={"command": verified}, result="failed", ok=False),
        ToolCall(name="Edit", arguments={"file_path": changed}, result="ok", ok=True),
        ToolCall(name="Bash", arguments={"command": verified}, result="ok", ok=True),
    )
    return Conversation(
        session_id="s1",
        interface="claude_code_native",
        started_at="2026-09-17T00:00:00Z",
        turns=(
            Turn(role="user", text=request, ts="2026-09-17T00:00:00Z"),
            Turn(role="assistant", text="Cause and outcome.", ts="2026-09-17T00:00:01Z", tool_calls=calls),
        ),
        scope="personal",
        origin_uri="",
    )


@pytest.mark.parametrize(
    "request_text",
    [
        # The exact phrasing that silently lost the transcript-upload bug.
        "Transcript watcher reported 'skipped session.jsonl - Not Found'",
        # A failure described plainly, with no keyword in it at all.
        "The upload returned 404 and the file was marked handled",
        # A decision, which is one of the three things this product is for.
        "Decided to store skills as vault pages rather than a new table",
        # Already worked, and must keep working.
        "Fix the 404 on capture upload",
    ],
)
def test_explicitly_recorded_work_is_always_kept(request_text):
    fix = extract_fix(_stated(request_text), stated=True)

    assert fix is not None, f"dropped: {request_text}"
    assert fix.symptom
    assert fix.changed_paths == ["src/thing.py"]


def test_inference_from_a_transcript_is_unchanged():
    """A captured transcript has nobody vouching for it, so the classifier
    still decides there. Only the deliberate call is exempt."""
    assert extract_fix(_stated("Rename the helper for clarity")) is None


def test_a_stated_record_still_needs_something_to_have_changed():
    """Saying work happened is not the same as work happening. Without a
    changed path there is no fix to come back to."""
    conversation = Conversation(
        session_id="s1",
        interface="claude_code_native",
        started_at="",
        turns=(Turn(role="user", text="Thought about the problem", ts=""),),
        scope="personal",
        origin_uri="",
    )

    assert extract_fix(conversation, stated=True) is None


def test_a_stated_record_that_ended_failing_is_not_kept():
    """A fix whose verification ended red is not a fix, however stated. This
    is what stops the store filling with claims that were never true."""
    calls = (
        ToolCall(name="Edit", arguments={"file_path": "src/thing.py"}, result="ok", ok=True),
        ToolCall(name="Bash", arguments={"command": "pytest"}, result="failed", ok=False),
    )
    conversation = Conversation(
        session_id="s1",
        interface="claude_code_native",
        started_at="",
        turns=(
            Turn(role="user", text="Tried to fix the crash", ts=""),
            Turn(role="assistant", text="", ts="", tool_calls=calls),
        ),
        scope="personal",
        origin_uri="",
    )

    assert extract_fix(conversation, stated=True) is None


# ── Recalling what was recorded ───────────────────────────────────────────────


def test_a_quoted_error_message_survives_keying():
    """Pasting an error in quotes is how everyone reports one.

    Quoted spans are stripped so `KeyError: 'slug'` and `KeyError: 'title'`
    read as one problem. When the quotes hold the whole message rather than a
    value inside it, that rule deletes every distinctive word and the fix
    becomes unmatchable — which is what happened to the first fix ever stored
    through `record_work`.
    """
    from archivum.fixes import symptom_key

    key = symptom_key("Transcript watcher reported 'skipped session.jsonl - Not Found'")

    assert "skipped" in key
    assert "found" in key


def test_a_short_quoted_value_is_still_dropped():
    """The behaviour the stripping exists for, which must not regress."""
    from archivum.fixes import symptom_key

    assert symptom_key("KeyError: 'slug'") == symptom_key("KeyError: 'title'")


def test_a_pasted_error_matches_the_report_it_was_recorded_from():
    """The whole point of recall: paste the error, find the story."""
    from archivum.fixes import match_score

    stored = "Transcript watcher reported 'skipped session.jsonl - Not Found'"
    pasted = "skipped session.jsonl Not Found"

    assert match_score(pasted, stored) >= 0.5


def test_unrelated_trouble_still_does_not_match():
    """A matcher that matches everything is worth nothing."""
    from archivum.fixes import match_score

    assert match_score(
        "qdrant connection refused on port 6333",
        "Transcript watcher reported 'skipped session.jsonl - Not Found'",
    ) < 0.5
