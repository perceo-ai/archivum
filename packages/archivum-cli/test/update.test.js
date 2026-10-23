import test from "node:test";
import assert from "node:assert/strict";
import cp from "node:child_process";
import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import os from "node:os";
import path from "node:path";

import { parseEnv, secretDefault } from "../src/env.js";
import { updateCommand } from "../src/update.js";

// Compose interpolates ${INTERNAL_GRAPH_TOKEN:?} whenever it loads the file,
// for every subcommand, `stop` included. So the token has to be on disk before
// the update path's first compose call, and that is the backup's `stop`. The
// env.test.js cases prove the helper alone; this pins where updateCommand
// calls it.

function installPredatingTheToken() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-update-"));
  fs.writeFileSync(path.join(root, "docker-compose.yml"), "services: {}\n", "utf8");
  fs.writeFileSync(
    path.join(root, ".env"),
    "JWT_SECRET=jwt-existing\nOWNER_PASSWORD=owner-existing\nMCP_API_KEY=mcp-existing\n",
    "utf8",
  );
  return root;
}

function tokenOnDisk(root) {
  const values = parseEnv(fs.readFileSync(path.join(root, ".env"), "utf8"));
  return Boolean(secretDefault(values.INTERNAL_GRAPH_TOKEN ?? ""));
}

function isComposeCall(command, args) {
  if (command === "docker-compose") return args[0] !== "version" && args[0] !== "--version";
  return command === "docker" && args[0] === "compose" && args[1] !== "version";
}

test("update writes INTERNAL_GRAPH_TOKEN before its first compose call", async (t) => {
  const root = installPredatingTheToken();
  const cwd = process.cwd();
  process.chdir(root);
  t.after(() => {
    process.chdir(cwd);
    t.mock.restoreAll();
    syncBuiltinESMExports();
    fs.rmSync(root, { recursive: true, force: true });
  });

  const composeCalls = [];
  t.mock.method(cp, "spawnSync", (command, args = []) => {
    if (isComposeCall(command, args)) {
      composeCalls.push({ argv: [command, ...args].join(" "), tokenPresent: tokenOnDisk(root) });
    }
    return { status: 0, stdout: "", stderr: "" };
  });
  // docker.js and update.js take spawnSync as a named import; this pushes the
  // mock through to those bindings.
  syncBuiltinESMExports();
  t.mock.method(console, "log", () => {});

  await updateCommand([]);

  const firstStop = composeCalls.findIndex((call) => / stop backend mcp$/.test(call.argv));
  assert.notEqual(firstStop, -1, "the backup never ran `compose stop`");
  const tooEarly = composeCalls.filter((call) => !call.tokenPresent).map((call) => call.argv);
  assert.deepEqual(tooEarly, [], "compose ran before INTERNAL_GRAPH_TOKEN was written to .env");
  assert.ok(tokenOnDisk(root));
});
