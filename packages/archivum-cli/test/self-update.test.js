import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { resolveInstallUrl, selfUpdateCommand } from "../src/self-update.js";

function homeLinkedTo(baseUrl) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-self-update-"));
  if (baseUrl) {
    fs.mkdirSync(path.join(home, ".archivum"));
    fs.writeFileSync(path.join(home, ".archivum", "connection.json"), JSON.stringify({ base_url: baseUrl }));
  }
  return home;
}

test("updates from the server this machine is linked to", () => {
  const home = homeLinkedTo("https://vault.example/");
  assert.equal(resolveInstallUrl([], { home, env: {} }), "https://vault.example/install");
});

test("--base beats ARCHIVUM_URL beats the link", () => {
  const home = homeLinkedTo("https://linked.example");
  const env = { ARCHIVUM_URL: "https://env.example" };
  assert.equal(resolveInstallUrl([], { home, env }), "https://env.example/install");
  assert.equal(resolveInstallUrl(["--base", "http://10.0.0.5:8000"], { home, env }), "http://10.0.0.5:8000/install");
});

test("an unlinked machine with no URL is told what to pass", () => {
  const home = homeLinkedTo(null);
  assert.throws(() => selfUpdateCommand([], { home, env: {}, log() {} }), /--base <url>/);
});

test("runs the served installer, passing the URL as an argument rather than splicing it in", { skip: process.platform === "win32" }, () => {
  const home = homeLinkedTo("https://vault.example");
  const calls = [];
  selfUpdateCommand([], { home, env: {}, log() {}, run: (cmd, argv) => { calls.push([cmd, argv]); return { status: 0 }; } });
  assert.equal(calls.length, 1);
  const [cmd, argv] = calls[0];
  assert.equal(cmd, "sh");
  assert.equal(argv[argv.length - 1], "https://vault.example/install");
  // Download, then run. Piping curl into sh reported sh's exit status, and sh
  // exits 0 on the empty input a failed download leaves behind.
  assert.match(argv[1], /curl -fsSL "\$1" -o/);
  assert.doesNotMatch(argv[1], /curl[^|]*\| *sh/);
});

test("a corrupt connection.json does not block --base or ARCHIVUM_URL", () => {
  const home = homeLinkedTo(null);
  fs.mkdirSync(path.join(home, ".archivum"));
  fs.writeFileSync(path.join(home, ".archivum", "connection.json"), "{not json");
  assert.equal(
    resolveInstallUrl(["--base", "https://fresh.example"], { home, env: {} }),
    "https://fresh.example/install",
  );
  assert.equal(
    resolveInstallUrl([], { home, env: { ARCHIVUM_URL: "https://env.example" } }),
    "https://env.example/install",
  );
  // With no override either, the corrupt file reads as unlinked, which ends
  // in the "pass --base" error rather than a JSON stack trace.
  assert.equal(resolveInstallUrl([], { home, env: {} }), null);
});

test("a failed install is an error, not a silent success", { skip: process.platform === "win32" }, () => {
  const home = homeLinkedTo("https://vault.example");
  assert.throws(
    () => selfUpdateCommand([], { home, env: {}, log() {}, run: () => ({ status: 22 }) }),
    /failed/,
  );
});
