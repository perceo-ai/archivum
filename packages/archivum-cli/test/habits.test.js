import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
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
