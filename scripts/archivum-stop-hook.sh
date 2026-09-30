#!/usr/bin/env bash
# Nudge the agent to record durable knowledge before a session ends.
#
# A record is one event. The project's vault page is the current truth, and
# it drifts unless a fix that changes setup or behaviour is also written there.
# So a session that recorded is asked one more question: is any statement on
# the project page now wrong?
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
#   2. Never ask for what the agent already did. A session that called
#      record_work is not asked to record, and one that also called write_page
#      is not asked about the page. Both checked in the session's own
#      transcript.
#   3. Never break a session. Any unexpected condition exits 0 and stays quiet.
#      A memory tool that stops someone working would be uninstalled by lunch.
#
# The transcript is read locally, only to answer "was record_work or
# write_page called". It is never uploaded, and nothing here sends it anywhere.

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

# The serialized tool-call field, not the bare word: reading this repository's
# CLAUDE.md, AGENTS.md or skill puts "record_work" in the transcript, and a
# substring match counted discussing the tool as calling it.
#
# The prefix is why this is a pattern and not a fixed string. Archivum's tools
# arrive over MCP, so the transcript records
# `"name":"mcp__archivum__record_work"`, never a bare `"name":"record_work"`.
# Matching the bare form found nothing and nagged every session — including
# sessions that had just recorded twice.
if grep -qE '"name":"(mcp__[A-Za-z0-9_]+__)?record_work"' "$transcript" 2>/dev/null; then
  : > "$marker" 2>/dev/null
  # Already edited a page this session: the loop is closed, say nothing.
  if grep -qE '"name":"(mcp__[A-Za-z0-9_]+__)?write_page"' "$transcript" 2>/dev/null; then
    exit 0
  fi
  jq -n '{
    decision: "block",
    reason: (
      "Before finishing: you recorded this work to Archivum. The record keeps the story; "
      + "the project page keeps the current truth.\n\n"
      + "Is any statement on the project page now wrong — how it is set up, how it is "
      + "operated, a known issue that is now fixed? If so:\n\n"
      + "  1. get_page(slug=...) for the project page.\n"
      + "  2. Change only the section that is wrong (Setup, Operations, Known issues, Decisions). "
      + "Leave every other section exactly as it was; other agents write to the same page.\n"
      + "  3. write_page(...) with the whole page, citing the record in the edited section.\n\n"
      + "State the current truth only; the history stays in the record.\n\n"
      + "If the fix changes nothing a page says — a bug in code that behaves as documented — "
      + "say so in one line and stop. You will not be asked again this session."
    )
  }' 2>/dev/null || exit 0
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
    + "If the finding changes how the project is set up or operated, also get_page the project "
    + "page, change only the section that is now wrong, and write_page it back citing the record.\n\n"
    + "If nothing here is worth keeping — a rename, a typo, a formatting pass — say so in one "
    + "line and stop. Not every session produces knowledge, and recording noise is worse than "
    + "recording nothing. You will not be asked again this session."
  )
}' 2>/dev/null || exit 0
