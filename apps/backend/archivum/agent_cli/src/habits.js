import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { parseOptions, writeFileAtomic } from "./util.js";

// The habits layer: linking a machine writes MCP config, and an agent with 28
// tools and no reason to call any of them uses none (measured 2026-09-17:
// four subagents, real work, zero writes to the vault). What creates the habit
// is three small things per machine — the skill, an instruction block in each
// agent's global file, and a Stop hook that asks before a session ends. This
// command installs all three, idempotently, and `connect` runs it so a fresh
// link arrives with the habits and not just the wiring.

const MARKER = "# Archivum memory";

export const HABITS_BLOCK = `
${MARKER}

This machine is linked to Archivum (MCP server \`archivum\`), a shared memory
vault every agent on every machine reads and writes. Use it in every repository:

- **Before debugging an error**: \`recall_fix(symptom="<the error>")\`. An empty
  answer says so; that is also information.
- **Before changing unfamiliar code**: \`retrieve_code_context(query=..., repo=...)\`.
  If \`list_repositories\` does not show the repo, run \`archivum index\` in it first.
- **After work that mattered** — a non-obvious cause, a decision with a reason,
  a gotcha: \`record_work(request=..., outcome=..., changed_paths=[...], verified_by=...)\`.
  State the cause, not the symptom. Never paste secrets into it.

If Archivum is unreachable, say so and carry on.
`;

// Byte-for-byte copy of scripts/archivum-stop-hook.sh, embedded because the
// CLI tarball ships .js files only. test/habits.test.js compares the two, so
// they cannot drift silently.
export const STOP_HOOK_SCRIPT = `#!/usr/bin/env bash
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

marker_dir="\${TMPDIR:-/tmp}/archivum-stop-hook"
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
# \`"name":"mcp__archivum__record_work"\`, never a bare \`"name":"record_work"\`.
# Matching the bare form found nothing and nagged every session — including
# sessions that had just recorded twice.
if grep -qE '"name":"(mcp__[A-Za-z0-9_]+__)?record_work"' "$transcript" 2>/dev/null; then
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
    "Before finishing: this session changed files, and nothing has been recorded to Archivum.\\n\\n"
    + "If something here is worth knowing in six months — a non-obvious cause, a decision and "
    + "its reason, a gotcha that would cost the next person an hour — call record_work now:\\n\\n"
    + "  record_work(request=..., outcome=..., changed_paths=[...], verified_by=...)\\n\\n"
    + "Say what the *cause* was, not just the symptom. \\"Fixed the test\\" is worth nothing later.\\n\\n"
    + "If nothing here is worth keeping — a rename, a typo, a formatting pass — say so in one "
    + "line and stop. Not every session produces knowledge, and recording noise is worse than "
    + "recording nothing. You will not be asked again this session."
  )
}' 2>/dev/null || exit 0
`;

const HOOK_RELATIVE = ".claude/hooks/archivum-stop-hook.sh";
// Written with ~ rather than the expanded home so a settings.json synced
// between machines still points at the right file on each of them.
const HOOK_COMMAND = "~/" + HOOK_RELATIVE;

function appendBlockOnce(file) {
  const existing = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  if (existing.includes(MARKER)) return false;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  writeFileAtomic(file, existing + HABITS_BLOCK);
  return true;
}

function installSkillFile(dir, text) {
  const target = path.join(dir, "archivum-memory", "SKILL.md");
  fs.mkdirSync(path.dirname(target), { recursive: true });
  writeFileAtomic(target, text);
  return target;
}

function wireStopHook(home) {
  const hookPath = path.join(home, HOOK_RELATIVE);
  fs.mkdirSync(path.dirname(hookPath), { recursive: true });
  writeFileAtomic(hookPath, STOP_HOOK_SCRIPT);
  fs.chmodSync(hookPath, 0o755);

  const settingsPath = path.join(home, ".claude", "settings.json");
  let settings = {};
  if (fs.existsSync(settingsPath)) {
    // An unparseable settings.json is someone's live config mid-edit; writing
    // over it would destroy whatever they meant. Same rule as the MCP writers.
    settings = JSON.parse(fs.readFileSync(settingsPath, "utf8"));
  }
  const stop = settings.hooks?.Stop ?? [];
  const wired = JSON.stringify(stop).includes("archivum-stop-hook");
  if (!wired) {
    stop.push({ hooks: [{ type: "command", command: HOOK_COMMAND }] });
    settings.hooks = { ...(settings.hooks ?? {}), Stop: stop };
    writeFileAtomic(settingsPath, `${JSON.stringify(settings, null, 2)}\n`);
  }
  return { hookPath, wired: !wired };
}

export async function habitsCommand(
  args,
  { home = os.homedir(), fetchImpl = fetch, log = console.log } = {},
) {
  const { values } = parseOptions(args);

  const statePath = path.join(home, ".archivum", "connection.json");
  const state = fs.existsSync(statePath)
    ? JSON.parse(fs.readFileSync(statePath, "utf8"))
    : null;
  const base = values.get("base") ?? state?.base_url ?? null;

  const summary = { skills: [], blocks: [], hook: null, skippedSkill: false };

  // The skill needs the server; the block and the hook do not, so a machine
  // that is offline right now still gets two of the three.
  if (base) {
    const response = await fetchImpl(`${base.replace(/\/+$/, "")}/api/mcp/skill`).catch(() => null);
    if (response?.ok) {
      const text = await response.text();
      const dirs = [path.join(home, ".claude", "skills")];
      for (const agent of [".hermes", ".openclaw"]) {
        if (fs.existsSync(path.join(home, agent))) dirs.push(path.join(home, agent, "skills"));
      }
      for (const dir of dirs) summary.skills.push(installSkillFile(dir, text));
    } else {
      summary.skippedSkill = true;
    }
  } else {
    summary.skippedSkill = true;
  }

  const blockTargets = [path.join(home, ".claude", "CLAUDE.md")];
  if (fs.existsSync(path.join(home, ".codex"))) {
    blockTargets.push(path.join(home, ".codex", "AGENTS.md"));
  }
  // OpenClaw reads per-workspace AGENTS.md files; only ones that already
  // exist get the block, because creating a workspace is OpenClaw's job.
  const openclaw = path.join(home, ".openclaw");
  if (fs.existsSync(openclaw)) {
    for (const entry of fs.readdirSync(openclaw)) {
      if (!entry.startsWith("workspace")) continue;
      const agents = path.join(openclaw, entry, "AGENTS.md");
      if (fs.existsSync(agents)) blockTargets.push(agents);
    }
  }
  for (const target of blockTargets) {
    if (appendBlockOnce(target)) summary.blocks.push(target);
  }

  summary.hook = wireStopHook(home);

  for (const file of summary.skills) log(`habit: installed ${file}`);
  for (const file of summary.blocks) log(`habit: added memory instructions to ${file}`);
  if (summary.hook.wired) log(`habit: wired Stop hook ${summary.hook.hookPath}`);
  if (summary.skippedSkill) {
    log("habit: skill skipped - no server reachable (run `archivum habits --base <url>` later)");
  }
  return summary;
}
