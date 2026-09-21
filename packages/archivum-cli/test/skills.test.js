import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { localSkills, pullSkills, pushSkills, writeLocalSkill } from "../src/skills.js";

function linkedHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));
  fs.mkdirSync(path.join(home, ".archivum"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".archivum", "connection.json"),
    JSON.stringify({ base_url: "https://v.example", key: "amk_1" }),
  );
  return home;
}

function installSkill(home, name, content = "# Skill\n") {
  const file = path.join(home, ".claude", "skills", name, "SKILL.md");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
}

test("local skills are found by their directory name", () => {
  const home = linkedHome();
  installSkill(home, "deploy-runbook", "# Deploy\n");
  // A directory without a SKILL.md is not a skill.
  fs.mkdirSync(path.join(home, ".claude", "skills", "empty"), { recursive: true });

  const found = localSkills(home);

  assert.deepEqual(found.map((s) => s.name), ["deploy-runbook"]);
  assert.equal(found[0].content, "# Deploy\n");
});

test("push sends every local skill", async () => {
  const home = linkedHome();
  installSkill(home, "one");
  installSkill(home, "two");
  const sent = [];

  const result = await pushSkills({
    home,
    log: () => {},
    fetchImpl: async (_url, init) => {
      sent.push(JSON.parse(init.body).name);
      return { ok: true, json: async () => ({ name: "x" }) };
    },
  });

  assert.equal(result.pushed, 2);
  assert.deepEqual(sent.sort(), ["one", "two"]);
});

test("push can send a single named skill", async () => {
  const home = linkedHome();
  installSkill(home, "one");
  installSkill(home, "two");
  const sent = [];

  await pushSkills({
    home,
    only: "two",
    log: () => {},
    fetchImpl: async (_url, init) => {
      sent.push(JSON.parse(init.body).name);
      return { ok: true, json: async () => ({ name: "two" }) };
    },
  });

  assert.deepEqual(sent, ["two"]);
});

test("a name the server would reject is refused here, not rewritten", async () => {
  const home = linkedHome();
  installSkill(home, "Not_Valid");
  const logs = [];

  const result = await pushSkills({
    home,
    log: (line) => logs.push(line),
    fetchImpl: async () => {
      throw new Error("should not have been called");
    },
  });

  // Silently renaming it would produce a skill you cannot find again.
  assert.equal(result.pushed, 0);
  assert.equal(result.skipped, 1);
  assert.match(logs.join("\n"), /lowercase/);
});

test("one rejected skill does not stop the others", async () => {
  const home = linkedHome();
  installSkill(home, "good");
  installSkill(home, "bad");

  const result = await pushSkills({
    home,
    log: () => {},
    fetchImpl: async (_url, init) => {
      const { name } = JSON.parse(init.body);
      if (name === "bad") {
        return { ok: false, status: 400, json: async () => ({ detail: { detail: "nope" } }) };
      }
      return { ok: true, json: async () => ({ name }) };
    },
  });

  assert.equal(result.pushed, 1);
  assert.equal(result.skipped, 1);
});

test("pull installs the vault's skills onto this machine", async () => {
  const home = linkedHome();

  const result = await pullSkills({
    home,
    log: () => {},
    fetchImpl: async (url) => {
      if (url.endsWith("/api/skills")) {
        return { ok: true, json: async () => ({ skills: [{ name: "runbook" }] }) };
      }
      return { ok: true, json: async () => ({ name: "runbook", content: "# Runbook\n" }) };
    },
  });

  assert.equal(result.pulled, 1);
  const installed = path.join(home, ".claude", "skills", "runbook", "SKILL.md");
  assert.equal(fs.readFileSync(installed, "utf8"), "# Runbook\n");
});

test("pull overwrites a stale local copy so an edit propagates", async () => {
  const home = linkedHome();
  installSkill(home, "runbook", "# old\n");

  await pullSkills({
    home,
    log: () => {},
    fetchImpl: async (url) =>
      url.endsWith("/api/skills")
        ? { ok: true, json: async () => ({ skills: [{ name: "runbook" }] }) }
        : { ok: true, json: async () => ({ name: "runbook", content: "# new\n" }) },
  });

  const installed = path.join(home, ".claude", "skills", "runbook", "SKILL.md");
  assert.equal(fs.readFileSync(installed, "utf8"), "# new\n");
});

test("pull says what to do when the vault has no skills yet", async () => {
  const home = linkedHome();
  const logs = [];

  await pullSkills({
    home,
    log: (line) => logs.push(line),
    fetchImpl: async () => ({ ok: true, json: async () => ({ skills: [] }) }),
  });

  assert.match(logs.join("\n"), /archivum skills push/);
});

test("skills commands refuse to run on a machine that is not linked", async () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));

  await assert.rejects(pushSkills({ home, log: () => {} }), /not linked/);
  await assert.rejects(pullSkills({ home, log: () => {} }), /not linked/);
});

test("writeLocalSkill creates the directory a client expects", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));

  const target = writeLocalSkill(home, "thing", "# Thing\n");

  assert.equal(target, path.join(home, ".claude", "skills", "thing", "SKILL.md"));
  assert.equal(fs.readFileSync(target, "utf8"), "# Thing\n");
});
