import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { habitsCommand, HABITS_BLOCK, STOP_HOOK_SCRIPT } from "../src/habits.js";

function freshHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "archivum-habits-"));
}

function linkedHome() {
  const home = freshHome();
  fs.mkdirSync(path.join(home, ".archivum"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".archivum", "connection.json"),
    JSON.stringify({ base_url: "https://v.example", key: "amk_1" }),
  );
  return home;
}

const skillFetch = async (url) => {
  assert.equal(url, "https://v.example/api/mcp/skill");
  return { ok: true, text: async () => "# the skill\n" };
};

test("the embedded Stop hook cannot drift from scripts/archivum-stop-hook.sh", () => {
  const repoCopy = fs.readFileSync(
    fileURLToPath(new URL("../../../scripts/archivum-stop-hook.sh", import.meta.url)),
    "utf8",
  );
  assert.equal(STOP_HOOK_SCRIPT, repoCopy);
});

test("habits installs skill, block, and hook on a linked machine", async () => {
  const home = linkedHome();
  const summary = await habitsCommand([], { home, fetchImpl: skillFetch, log: () => {} });

  assert.equal(
    fs.readFileSync(path.join(home, ".claude", "skills", "archivum-memory", "SKILL.md"), "utf8"),
    "# the skill\n",
  );
  assert.ok(
    fs.readFileSync(path.join(home, ".claude", "CLAUDE.md"), "utf8").includes("# Archivum memory"),
  );
  const hook = path.join(home, ".claude", "hooks", "archivum-stop-hook.sh");
  assert.equal(fs.readFileSync(hook, "utf8"), STOP_HOOK_SCRIPT);
  assert.ok(fs.statSync(hook).mode & 0o100);
  const settings = JSON.parse(fs.readFileSync(path.join(home, ".claude", "settings.json"), "utf8"));
  assert.match(settings.hooks.Stop[0].hooks[0].command, /archivum-stop-hook\.sh$/);
  assert.equal(summary.skippedSkill, false);
});

test("habits is idempotent: a second run changes nothing", async () => {
  const home = linkedHome();
  await habitsCommand([], { home, fetchImpl: skillFetch, log: () => {} });
  const second = await habitsCommand([], { home, fetchImpl: skillFetch, log: () => {} });

  assert.deepEqual(second.blocks, []);
  assert.equal(second.hook.wired, false);
  const md = fs.readFileSync(path.join(home, ".claude", "CLAUDE.md"), "utf8");
  assert.equal(md.split("# Archivum memory").length, 2);
  const settings = JSON.parse(fs.readFileSync(path.join(home, ".claude", "settings.json"), "utf8"));
  assert.equal(settings.hooks.Stop.length, 1);
});

test("existing settings and instruction files are preserved, not replaced", async () => {
  const home = linkedHome();
  fs.mkdirSync(path.join(home, ".claude"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".claude", "settings.json"),
    JSON.stringify({ model: "opus", hooks: { Stop: [{ hooks: [{ type: "command", command: "mine.sh" }] }] } }),
  );
  fs.writeFileSync(path.join(home, ".claude", "CLAUDE.md"), "# Mine\n");

  await habitsCommand([], { home, fetchImpl: skillFetch, log: () => {} });

  const settings = JSON.parse(fs.readFileSync(path.join(home, ".claude", "settings.json"), "utf8"));
  assert.equal(settings.model, "opus");
  assert.equal(settings.hooks.Stop.length, 2);
  assert.equal(settings.hooks.Stop[0].hooks[0].command, "mine.sh");
  const md = fs.readFileSync(path.join(home, ".claude", "CLAUDE.md"), "utf8");
  assert.ok(md.startsWith("# Mine\n"));
  assert.ok(md.includes("# Archivum memory"));
});

test("an unparseable settings.json stops the run instead of being clobbered", async () => {
  const home = linkedHome();
  fs.mkdirSync(path.join(home, ".claude"), { recursive: true });
  fs.writeFileSync(path.join(home, ".claude", "settings.json"), "{not json");

  await assert.rejects(habitsCommand([], { home, fetchImpl: skillFetch, log: () => {} }));
  assert.equal(fs.readFileSync(path.join(home, ".claude", "settings.json"), "utf8"), "{not json");
});

test("other agents get the pieces they read, when present", async () => {
  const home = linkedHome();
  fs.mkdirSync(path.join(home, ".codex"), { recursive: true });
  fs.mkdirSync(path.join(home, ".hermes"), { recursive: true });
  fs.mkdirSync(path.join(home, ".openclaw", "workspace-the-nerd"), { recursive: true });
  fs.writeFileSync(path.join(home, ".openclaw", "workspace-the-nerd", "AGENTS.md"), "# Nerd\n");
  // A workspace without an AGENTS.md is OpenClaw's to create, not ours.
  fs.mkdirSync(path.join(home, ".openclaw", "workspace-empty"), { recursive: true });

  const summary = await habitsCommand([], { home, fetchImpl: skillFetch, log: () => {} });

  assert.ok(fs.existsSync(path.join(home, ".hermes", "skills", "archivum-memory", "SKILL.md")));
  assert.ok(fs.existsSync(path.join(home, ".openclaw", "skills", "archivum-memory", "SKILL.md")));
  assert.ok(
    fs.readFileSync(path.join(home, ".codex", "AGENTS.md"), "utf8").includes("# Archivum memory"),
  );
  assert.ok(
    fs
      .readFileSync(path.join(home, ".openclaw", "workspace-the-nerd", "AGENTS.md"), "utf8")
      .startsWith("# Nerd\n"),
  );
  assert.ok(!fs.existsSync(path.join(home, ".openclaw", "workspace-empty", "AGENTS.md")));
  assert.equal(summary.skills.length, 3);
});

test("no server known: block and hook still land, skill reports skipped", async () => {
  const home = freshHome();
  const summary = await habitsCommand([], {
    home,
    fetchImpl: async () => assert.fail("must not fetch"),
    log: () => {},
  });

  assert.equal(summary.skippedSkill, true);
  assert.deepEqual(summary.skills, []);
  assert.ok(fs.existsSync(path.join(home, ".claude", "hooks", "archivum-stop-hook.sh")));
  assert.ok(fs.existsSync(path.join(home, ".claude", "CLAUDE.md")));
});

test("--base wins over the stored connection", async () => {
  const home = linkedHome();
  let asked = null;
  await habitsCommand(["--base", "https://other.example/"], {
    home,
    fetchImpl: async (url) => {
      asked = url;
      return { ok: true, text: async () => "# s\n" };
    },
    log: () => {},
  });
  assert.equal(asked, "https://other.example/api/mcp/skill");
});

// The hook's behaviour, not just its bytes: run the shipped script against a
// fake transcript the way Claude Code would, and read back what it decided.
// Skipped where jq is missing, because the script deliberately does nothing
// there (rule 3) and there would be nothing to observe.
const hasJq = spawnSync("sh", ["-c", "command -v jq"]).status === 0;

function runHook(toolNames) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-hook-"));
  const script = path.join(dir, "hook.sh");
  fs.writeFileSync(script, STOP_HOOK_SCRIPT, { mode: 0o755 });
  const transcript = path.join(dir, "transcript.jsonl");
  fs.writeFileSync(
    transcript,
    toolNames.map((name) => JSON.stringify({ type: "tool_use", name })).join("\n") + "\n",
  );
  const payload = JSON.stringify({ session_id: "s1", transcript_path: transcript });
  const env = { ...process.env, TMPDIR: dir };
  const once = () => spawnSync("bash", [script], { input: payload, env, encoding: "utf8" });
  const first = once();
  const second = once();
  return {
    first: first.stdout ? JSON.parse(first.stdout) : null,
    second: second.stdout ? JSON.parse(second.stdout) : null,
  };
}

test("stop hook: edits without a record are asked to record, once", { skip: !hasJq }, () => {
  const { first, second } = runHook(["Read", "Edit"]);
  assert.equal(first.decision, "block");
  assert.match(first.reason, /call record_work now/);
  assert.match(first.reason, /write_page/);
  assert.equal(second, null);
});

test("stop hook: a record without a page edit asks about the page, once", { skip: !hasJq }, () => {
  const { first, second } = runHook(["Edit", "mcp__archivum__record_work"]);
  assert.equal(first.decision, "block");
  assert.match(first.reason, /project page now wrong/);
  assert.match(first.reason, /get_page/);
  assert.doesNotMatch(first.reason, /call record_work now/);
  assert.equal(second, null);
});

test("stop hook: a record and a page edit close the loop silently", { skip: !hasJq }, () => {
  const { first } = runHook(["Edit", "mcp__archivum__record_work", "mcp__archivum__write_page"]);
  assert.equal(first, null);
});

test("stop hook: a read-only session is never asked", { skip: !hasJq }, () => {
  const { first } = runHook(["Read", "Grep"]);
  assert.equal(first, null);
});
