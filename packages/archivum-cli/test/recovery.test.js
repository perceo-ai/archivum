import test from "node:test";
import assert from "node:assert/strict";

import {
  PRECIOUS_VOLUME_MOUNTS,
  buildBackupPlan,
  buildRestorePlan,
  dockerVolumeName,
  formatPlanCommands,
  runBackupPlan,
  validateBackupDir,
} from "../src/recovery.js";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

test("backup plan captures env, compose files, manifest, and precious volumes", () => {
  const plan = buildBackupPlan({
    root: "/srv/archivum",
    backupDir: "/srv/archivum/backups/pre-update-20260811",
    compose: ["docker", "compose"],
  });

  assert.deepEqual(plan.files, [".env", "docker-compose.yml", "docker-compose.images.yml", "caddy/Caddyfile"]);
  assert.deepEqual(plan.volumes, PRECIOUS_VOLUME_MOUNTS);
  assert.equal(plan.manifest.name, "pre-update-20260811");
  assert.match(plan.commands[0].join(" "), /docker compose .* stop backend mcp/);
  assert.match(plan.commands.at(-1).join(" "), /docker compose .* start backend mcp/);
  assert.ok(plan.commands.some((cmd) => cmd.join(" ").includes("wiki_data") && cmd.join(" ").includes("wiki_data.tar.gz")));
  assert.ok(plan.commands.some((cmd) => cmd.join(" ").includes("db_data") && cmd.join(" ").includes("db_data.tar.gz")));
});

test("backup plan uses resolved compose project name for volume mounts", () => {
  const plan = buildBackupPlan({
    root: "/srv/renamed-install",
    backupDir: "/srv/renamed-install/backups/latest",
    compose: ["docker", "compose"],
    projectName: "archivum-prod",
  });

  const wikiCommand = plan.commands.find((command) => command.join(" ").includes("wiki_data.tar.gz"));

  assert.ok(wikiCommand);
  assert.ok(wikiCommand.join(" ").includes("archivum-prod_wiki_data:/volume:ro"));
});

test("dockerVolumeName falls back to install directory when project name is absent", () => {
  assert.equal(dockerVolumeName("/srv/archivum", "db_data"), "archivum_db_data");
});

test("restore plan stops stack before restoring precious volumes and restarts after", () => {
  const plan = buildRestorePlan({
    root: "/srv/archivum",
    backupDir: "/srv/archivum/backups/pre-update-20260811",
    compose: ["docker", "compose"],
  });

  assert.deepEqual(plan.volumes, PRECIOUS_VOLUME_MOUNTS);
  assert.match(plan.commands[0].join(" "), /docker compose .* down/);
  assert.ok(plan.commands.some((cmd) => cmd.join(" ").includes("wiki_data") && cmd.join(" ").includes("wiki_data.tar.gz")));
  assert.ok(plan.commands.some((cmd) => cmd.join(" ").includes("raw_data") && cmd.join(" ").includes("raw_data.tar.gz")));
  assert.match(plan.commands.at(-1).join(" "), /docker compose .* up -d/);
});

test("backup runner restarts stopped services when volume archive fails", () => {
  const plan = buildBackupPlan({
    root: "/srv/archivum",
    backupDir: "/srv/archivum/backups/pre-update-20260811",
    compose: ["docker", "compose"],
  });
  const calls = [];

  assert.throws(() => runBackupPlan(plan, (command) => {
    calls.push(command.join(" "));
    if (command.includes("docker") && command.includes("run")) throw new Error("tar failed");
  }), /tar failed/);

  assert.match(calls[0], /stop backend mcp/);
  assert.match(calls.at(-1), /start backend mcp/);
});

test("backup validation reports missing manifest and tarballs before restore", () => {
  const backupDir = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-backup-"));
  fs.writeFileSync(path.join(backupDir, "wiki_data.tar.gz"), "not-empty");

  const result = validateBackupDir(backupDir);

  assert.equal(result.ok, false);
  assert.ok(result.missing.includes("manifest.json"));
  assert.ok(result.missing.includes("raw_data.tar.gz"));
  assert.ok(result.missing.includes("db_data.tar.gz"));
});

test("formatPlanCommands prints shell-safe command lines for dry runs", () => {
  const plan = buildRestorePlan({
    root: "/srv/archivum",
    backupDir: "/srv/archivum/backups/with space",
    compose: ["docker", "compose"],
  });

  const text = formatPlanCommands(plan.commands);

  assert.match(text, /docker compose .* down/);
  assert.match(text, /'\/srv\/archivum\/backups\/with space:\/backup:ro'/);
  assert.match(text, /docker compose .* up -d/);
});
