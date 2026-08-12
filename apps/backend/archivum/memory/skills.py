"""Deterministic skill extraction from completed agent work.

A skill is only produced when tool steps actually happened: prose describing a
procedure is not a procedure. Steps come from the recorded tool calls, in
order, so a replayed skill matches what the agent really did.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from archivum.capture.schema import Conversation, ToolCall

MIN_TOOL_CALLS = 3
MAX_STEPS = 24
MAX_ARG_CHARS = 160

# Tool names that read as verification rather than mutation.
_VALIDATION_RE = re.compile(
    r"\b(?:test|tests|pytest|verify|validate|lint|typecheck|build|check|smoke|assert)\b",
    re.IGNORECASE,
)

# Argument keys worth showing in a step summary, most-identifying first.
_SALIENT_ARG_KEYS = (
    "command",
    "cmd",
    "file_path",
    "path",
    "query",
    "pattern",
    "url",
    "name",
    "slug",
)


@dataclass(frozen=True, slots=True)
class SkillStep:
    order: int
    tool: str
    summary: str
    turn_index: int
    ok: bool


@dataclass(frozen=True, slots=True)
class SkillDraft:
    """A reusable procedure recovered from one completed session."""

    slug: str
    name: str
    trigger: str
    steps: tuple[SkillStep, ...]
    validation: tuple[str, ...]
    outcome_status: str
    tool_call_count: int
    confidence: float
    trigger_turn_index: int = 0
    tags: tuple[str, ...] = field(default=("skill",))


def _salient_argument(call: ToolCall) -> str:
    for key in _SALIENT_ARG_KEYS:
        value = call.arguments.get(key)
        if isinstance(value, str) and value.strip():
            return _truncate(value.strip())
    if not call.arguments:
        return ""
    return _truncate(json.dumps(call.arguments, sort_keys=True, ensure_ascii=False))


def _truncate(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value).strip()
    if len(collapsed) <= MAX_ARG_CHARS:
        return collapsed
    return collapsed[: MAX_ARG_CHARS - 1] + "…"


def skill_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return slug or "skill"


def _first_user_text(conv: Conversation) -> tuple[str, int]:
    for index, turn in enumerate(conv.turns):
        text = turn.text.strip()
        if turn.role == "user" and text:
            return text, index
    return "", 0


def _outcome_status(conv: Conversation) -> str:
    statuses = {outcome.status for outcome in conv.outcomes}
    for candidate in ("failure", "partial", "success"):
        if candidate in statuses:
            return candidate
    return "unknown"


def extract_skill(
    conv: Conversation, *, min_tool_calls: int = MIN_TOOL_CALLS
) -> SkillDraft | None:
    """Return a skill draft, or None when the session is not a real procedure.

    Gates, all of which must hold:
    - at least `min_tool_calls` successful tool calls were recorded
    - the session did not end in a recorded failure
    - a user request exists to serve as the trigger
    """
    calls: list[tuple[int, ToolCall]] = [
        (turn_index, call)
        for turn_index, turn in enumerate(conv.turns)
        for call in turn.tool_calls
    ]
    successful = [(index, call) for index, call in calls if call.ok]
    if len(successful) < max(min_tool_calls, 1):
        return None

    outcome_status = _outcome_status(conv)
    if outcome_status == "failure":
        return None

    trigger, trigger_turn_index = _first_user_text(conv)
    if not trigger:
        return None

    steps: list[SkillStep] = []
    seen: set[tuple[str, str]] = set()
    for turn_index, call in successful:
        argument = _salient_argument(call)
        key = (call.name, argument)
        if key in seen:
            continue
        seen.add(key)
        summary = f"{call.name}({argument})" if argument else call.name
        steps.append(
            SkillStep(
                order=len(steps) + 1,
                tool=call.name,
                summary=summary,
                turn_index=turn_index,
                ok=call.ok,
            )
        )
        if len(steps) >= MAX_STEPS:
            break

    validation = tuple(
        step.summary
        for step in steps
        if _VALIDATION_RE.search(step.tool) or _VALIDATION_RE.search(step.summary)
    )
    validation = validation + tuple(
        f"{outcome.task} — {outcome.status}"
        for outcome in conv.outcomes
        if outcome.status == "success"
    )

    name = _skill_name(trigger)
    confidence = 0.8 if outcome_status == "success" else 0.6
    if validation:
        confidence = min(confidence + 0.1, 1.0)

    return SkillDraft(
        slug=skill_slug(name),
        name=name,
        trigger=_truncate(trigger),
        steps=tuple(steps),
        validation=validation,
        outcome_status=outcome_status,
        tool_call_count=len(successful),
        confidence=round(confidence, 4),
        trigger_turn_index=trigger_turn_index,
    )


def _skill_name(trigger: str) -> str:
    """Derive a short imperative name from the triggering request."""
    first = split_first_sentence(trigger)
    words = re.sub(r"[^A-Za-z0-9\s-]", " ", first).split()
    if not words:
        return "Captured procedure"
    trimmed = words[:8]
    return " ".join(trimmed)[:80].strip().capitalize()


def split_first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip(), maxsplit=1)
    return parts[0].strip() if parts else text.strip()


def render_skill_markdown(draft: SkillDraft, *, provenance: str) -> str:
    """Markdown body so the skill stays editable by a human."""
    lines = [
        "---",
        "type: skill",
        f"slug: {draft.slug}",
        f"outcome: {draft.outcome_status}",
        f"tool_calls: {draft.tool_call_count}",
        "---",
        "",
        f"# {draft.name}",
        "",
        "## Trigger",
        "",
        draft.trigger,
        "",
        "## Steps",
        "",
    ]
    lines.extend(f"{step.order}. `{step.summary}`" for step in draft.steps)
    lines.extend(["", "## Validation", ""])
    if draft.validation:
        lines.extend(f"- {item}" for item in draft.validation)
    else:
        lines.append("- No verification step was recorded in this session.")
    lines.extend(["", "## Provenance", "", provenance, ""])
    return "\n".join(lines)
