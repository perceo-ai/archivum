import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { parseOptions, writeFileAtomic } from "./util.js";

// A skill is a repeatable procedure that currently lives in ~/.claude/skills on
// exactly one laptop. That is the same problem CLAUDE.md has, and the one this
// product exists to fix: write it once, have it on every machine you link.

const SKILL_DIR = path.join(".claude", "skills");
const SKILL_FILE = "SKILL.md";

// Matches the server: a name becomes a page slug under `skills/`, so anything
// with a separator in it would write outside that folder.
const VALID_NAME = /^[a-z0-9][a-z0-9-]{0,63}$/;

function loadState(home) {
  const statePath = path.join(home, ".archivum", "connection.json");
  if (!fs.existsSync(statePath)) {
    throw new Error("This machine is not linked. Run: archivum connect --auto");
  }
  return JSON.parse(fs.readFileSync(statePath, "utf8"));
}

/** Every skill installed on this machine, as {name, content}. */
export function localSkills(home) {
  const root = path.join(home, SKILL_DIR);
  if (!fs.existsSync(root)) return [];
  const found = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const file = path.join(root, entry.name, SKILL_FILE);
    if (!fs.existsSync(file)) continue;
    found.push({ name: entry.name, content: fs.readFileSync(file, "utf8") });
  }
  return found;
}

export function writeLocalSkill(home, name, content) {
  const target = path.join(home, SKILL_DIR, name, SKILL_FILE);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  writeFileAtomic(target, content);
  return target;
}

async function api(state, route, { method = "GET", body, fetchImpl = fetch } = {}) {
  const response = await fetchImpl(`${state.base_url}/api/skills${route}`, {
    method,
    headers: {
      Authorization: `Bearer ${state.key}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload?.detail?.detail ?? payload?.detail;
    throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
  }
  return response.json();
}

export async function pushSkills(
  { home = os.homedir(), only, fetchImpl = fetch, log = console.log } = {},
) {
  const state = loadState(home);
  const all = localSkills(home);
  const chosen = only ? all.filter((s) => [].concat(only).includes(s.name)) : all;

  if (chosen.length === 0) {
    log(only ? `archivum: no local skill named ${[].concat(only).join(", ")}` : "archivum: no local skills found");
    return { pushed: 0, skipped: 0 };
  }

  let pushed = 0;
  let skipped = 0;
  for (const skill of chosen) {
    // Refused rather than rewritten: a name quietly changed on the way up is a
    // skill you cannot find again by the name you gave it.
    if (!VALID_NAME.test(skill.name)) {
      log(`  skipped ${skill.name} — name must be lowercase letters, digits and hyphens`);
      skipped += 1;
      continue;
    }
    try {
      await api(state, "", { method: "POST", body: skill, fetchImpl });
      log(`  pushed ${skill.name}`);
      pushed += 1;
    } catch (error) {
      log(`  skipped ${skill.name} — ${error.message}`);
      skipped += 1;
    }
  }
  log(`archivum: ${pushed} skill${pushed === 1 ? "" : "s"} pushed${skipped ? `, ${skipped} skipped` : ""}`);
  return { pushed, skipped };
}

export async function pullSkills(
  { home = os.homedir(), fetchImpl = fetch, log = console.log } = {},
) {
  const state = loadState(home);
  const { skills } = await api(state, "", { fetchImpl });

  if (!skills?.length) {
    log("archivum: no skills stored in the vault yet. Push some with: archivum skills push");
    return { pulled: 0 };
  }

  let pulled = 0;
  for (const { name } of skills) {
    try {
      const skill = await api(state, `/${encodeURIComponent(name)}`, { fetchImpl });
      const target = writeLocalSkill(home, name, skill.content);
      log(`  installed ${target}`);
      pulled += 1;
    } catch (error) {
      // One bad skill must not cost the rest theirs.
      log(`  skipped ${name} — ${error.message}`);
    }
  }
  log(`archivum: ${pulled} skill${pulled === 1 ? "" : "s"} installed. Restart your agent to pick them up.`);
  return { pulled };
}

export async function skillsCommand(args, options = {}) {
  const { values, positionals } = parseOptions(args);
  const action = positionals[0];

  if (action === "push") {
    return pushSkills({ ...options, only: values.get("name") });
  }
  if (action === "pull") {
    return pullSkills(options);
  }
  throw new Error(
    "Usage: archivum skills push [--name NAME]   send this machine's skills to the vault\n" +
      "       archivum skills pull                 install the vault's skills here",
  );
}
