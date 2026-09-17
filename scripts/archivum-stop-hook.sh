#!/usr/bin/env bash
# Nudge the agent to record durable knowledge before a session ends.
#
# Measured on 2026-09-17: four subagents did real work in this repository with
# the tools and the skill both available, and none of them wrote anything to
# the vault. Guidance in files is necessary and not sufficient. A hook fires
# whether or not an agent remembers, which is the point.
#
# Three rules this script must never break:
#
#   1. Nudge at most once per session. A Stop hook that blocks every time
#      loops forever, because the turn it forces ends in another Stop.
#   2. Never nudge when the agent already recorded. Checked by looking for a
#      record_work call in the session's own transcript.
#   3. Never break a session. Any unexpected condition exits 0 and stays quiet.
#      A memory tool that stops someone working would be uninstalled by lunch.
#
# The transcript is read locally, only to answer "was record_work called". It
# is never uploaded, and nothing here sends it anywhere.

set -uo pipefail

# Rule 3: without jq we cannot read the payload, so do nothing at all.
command -v jq >/dev/null 2>&1 || exit 0

payload="$(cat 2>/dev/null)" || exit 0
[ -n "$payload" ] || exit 0

session_id="$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)" || exit 0
transcript="$(printf '%s' "$payload" | jq -r '.transcript_path // empty' 2>/dev/null)" || exit 0

[ -n "$session_id" ] || exit 0

marker_dir="${TMPDIR:-/tmp}/archivum-stop-hook"
mkdir -p "$marker_dir" 2>/dev/null || exit 0
marker="$marker_dir/$session_id"

# Rule 1.
[ -e "$marker" ] && exit 0

# Rule 2. No transcript means no evidence either way; say nothing rather than
# nag a session we cannot see.
[ -n "$transcript" ] && [ -r "$transcript" ] || exit 0

# The serialized tool-call field, not the bare word. Reading this repository's
# CLAUDE.md, AGENTS.md or skill puts "record_work" in the transcript, so a
# substring match counted discussing the tool as calling it — and then
# suppressed the reminder for the rest of the session.
if grep -q '"name":"record_work"' "$transcript" 2>/dev/null; then
  : > "$marker" 2>/dev/null
  exit 0
fi

# Only worth asking if the session actually changed something. A session that
# read files and answered a question has nothing durable to record, and being
# asked anyway is how a hook teaches people to ignore it.
if ! grep -qE '"name":"(Edit|Write|NotebookEdit)"' "$transcript" 2>/dev/null; then
  : > "$marker" 2>/dev/null
  exit 0
fi

: > "$marker" 2>/dev/null

jq -n '{
  decision: "block",
  reason: (
    "Before finishing: this session changed files, and nothing has been recorded to Archivum.\n\n"
    + "If something here is worth knowing in six months — a non-obvious cause, a decision and "
    + "its reason, a gotcha that would cost the next person an hour — call record_work now:\n\n"
    + "  record_work(request=..., outcome=..., changed_paths=[...], verified_by=...)\n\n"
    + "Say what the *cause* was, not just the symptom. \"Fixed the test\" is worth nothing later.\n\n"
    + "If nothing here is worth keeping — a rename, a typo, a formatting pass — say so in one "
    + "line and stop. Not every session produces knowledge, and recording noise is worse than "
    + "recording nothing. You will not be asked again this session."
  )
}' 2>/dev/null || exit 0
