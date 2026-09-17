import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  addClaudeServerViaCli,
  detectClients,
  writeClaudeConfig,
  writeCursorConfig,
  writeCodexConfig,
  streamableHttpUrl,
} from "../src/clients.js";

function tempHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));
}

// Never let a test reach the real `claude` binary: it would rewrite the
// developer's own MCP config. `noClaudeCli` is what "claude is not installed"
// looks like to spawnSync, which is the file-writer path these tests cover.
const noClaudeCli = () => ({ error: Object.assign(new Error("spawn claude ENOENT"), { code: "ENOENT" }) });

const opts = (home) => ({
  home,
  sseUrl: "https://vault.example.com/sse",
  key: "amk_test",
  spawnImpl: noClaudeCli,
});

test("detectClients finds only the clients that are installed", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".cursor"), { recursive: true });

  assert.deepEqual(detectClients(home), ["cursor"]);
});

test("writeClaudeConfig adds an archivum server with the bearer header", () => {
  const home = tempHome();

  const written = writeClaudeConfig(opts(home));
  const config = JSON.parse(fs.readFileSync(written, "utf8"));

  assert.equal(config.mcpServers.archivum.url, "https://vault.example.com/sse");
  assert.equal(config.mcpServers.archivum.headers.Authorization, "Bearer amk_test");
});

test("writeClaudeConfig preserves other servers and is idempotent", () => {
  const home = tempHome();
  const target = path.join(home, ".claude.json");
  fs.writeFileSync(target, JSON.stringify({ mcpServers: { other: { url: "http://x" } } }));

  writeClaudeConfig(opts(home));
  writeClaudeConfig(opts(home));
  const config = JSON.parse(fs.readFileSync(target, "utf8"));

  assert.equal(config.mcpServers.other.url, "http://x");
  assert.equal(Object.keys(config.mcpServers).length, 2);
});

test("writeCursorConfig writes to .cursor/mcp.json", () => {
  const home = tempHome();

  const written = writeCursorConfig(opts(home));

  assert.equal(written, path.join(home, ".cursor", "mcp.json"));
  assert.match(fs.readFileSync(written, "utf8"), /amk_test/);
});

test("writeCodexConfig writes a toml block and replaces it on re-run", () => {
  const home = tempHome();

  writeCodexConfig(opts(home));
  const written = writeCodexConfig(opts(home));
  const toml = fs.readFileSync(written, "utf8");

  assert.equal(written, path.join(home, ".codex", "config.toml"));
  assert.equal(toml.match(/\[mcp_servers\.archivum\]/g).length, 1);
  // Codex only speaks streamable HTTP; the SSE endpoint answers its
  // `initialize` POST with 405.
  assert.match(toml, /url = "https:\/\/vault\.example\.com\/mcp"/);
});

test("streamableHttpUrl maps an SSE endpoint onto the streamable HTTP one", () => {
  assert.equal(streamableHttpUrl("https://vault.example.com/sse"), "https://vault.example.com/mcp");
  assert.equal(streamableHttpUrl("https://vault.example.com/sse/"), "https://vault.example.com/mcp");
  assert.equal(streamableHttpUrl("https://vault.example.com/mcp"), "https://vault.example.com/mcp");
  assert.equal(streamableHttpUrl("https://vault.example.com"), "https://vault.example.com/mcp");
});

test("writeCodexConfig leaves unrelated toml intact", () => {
  const home = tempHome();
  const target = path.join(home, ".codex", "config.toml");
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, 'model = "gpt-5"\n');

  writeCodexConfig(opts(home));

  assert.match(fs.readFileSync(target, "utf8"), /model = "gpt-5"/);
});

test("writeClaudeConfig writes file with mode 0o600 and tightens pre-existing files", () => {
  const home = tempHome();
  const target = path.join(home, ".claude.json");

  // Fresh file should have mode 0o600
  writeClaudeConfig(opts(home));
  let mode = fs.statSync(target).mode & 0o777;
  assert.equal(mode, 0o600);

  // Pre-existing file at 0o644 should be tightened to 0o600
  fs.chmodSync(target, 0o644);
  assert.equal(fs.statSync(target).mode & 0o777, 0o644);
  writeClaudeConfig(opts(home));
  mode = fs.statSync(target).mode & 0o777;
  assert.equal(mode, 0o600);
});

test("writeCursorConfig writes file with mode 0o600 and tightens pre-existing files", () => {
  const home = tempHome();
  const target = path.join(home, ".cursor", "mcp.json");

  // Fresh file should have mode 0o600
  writeCursorConfig(opts(home));
  let mode = fs.statSync(target).mode & 0o777;
  assert.equal(mode, 0o600);

  // Pre-existing file at 0o644 should be tightened to 0o600
  fs.chmodSync(target, 0o644);
  assert.equal(fs.statSync(target).mode & 0o777, 0o644);
  writeCursorConfig(opts(home));
  mode = fs.statSync(target).mode & 0o777;
  assert.equal(mode, 0o600);
});

test("writeCodexConfig writes file with mode 0o600 and tightens pre-existing files", () => {
  const home = tempHome();
  const target = path.join(home, ".codex", "config.toml");

  // Fresh file should have mode 0o600
  writeCodexConfig(opts(home));
  let mode = fs.statSync(target).mode & 0o777;
  assert.equal(mode, 0o600);

  // Pre-existing file at 0o644 should be tightened to 0o600
  fs.chmodSync(target, 0o644);
  assert.equal(fs.statSync(target).mode & 0o777, 0o644);
  writeCodexConfig(opts(home));
  mode = fs.statSync(target).mode & 0o777;
  assert.equal(mode, 0o600);
});

test("writeClaudeConfig uses `claude mcp add` when the CLI is available", () => {
  const home = tempHome();
  const calls = [];
  const spawnImpl = (cmd, args) => {
    calls.push([cmd, ...args]);
    return { status: 0, stdout: "", stderr: "" };
  };

  const written = writeClaudeConfig({ ...opts(home), spawnImpl });

  assert.match(written, /claude mcp add/);
  // Probe, then a remove so a re-link is idempotent, then the add itself.
  assert.deepEqual(calls[0], ["claude", "mcp", "list"]);
  assert.deepEqual(calls[1], ["claude", "mcp", "remove", "archivum", "--scope", "user"]);
  assert.deepEqual(calls[2], [
    "claude",
    "mcp",
    "add",
    "--scope",
    "user",
    "--transport",
    "sse",
    "archivum",
    "https://vault.example.com/sse",
    "--header",
    "Authorization: Bearer amk_test",
  ]);
  // The live state file is left alone when the CLI did the work.
  assert.equal(fs.existsSync(path.join(home, ".claude.json")), false);
});

test("writeClaudeConfig falls back to the config file when `claude` is not installed", () => {
  const home = tempHome();

  const written = writeClaudeConfig(opts(home));

  assert.equal(written, path.join(home, ".claude.json"));
  const config = JSON.parse(fs.readFileSync(written, "utf8"));
  assert.equal(config.mcpServers.archivum.url, "https://vault.example.com/sse");
});

test("writeClaudeConfig falls back to the config file when `claude mcp add` fails", () => {
  const home = tempHome();
  const spawnImpl = (cmd, args) =>
    args[1] === "add" ? { status: 1, stderr: "unknown option --transport" } : { status: 0, stdout: "" };

  const written = writeClaudeConfig({ ...opts(home), spawnImpl });

  assert.equal(written, path.join(home, ".claude.json"));
  assert.match(fs.readFileSync(written, "utf8"), /amk_test/);
});

test("addClaudeServerViaCli does not run `mcp add` when the probe fails", () => {
  const calls = [];
  const spawnImpl = (cmd, args) => {
    calls.push(args[1]);
    return { status: 127, stderr: "command not found" };
  };

  const result = addClaudeServerViaCli({ sseUrl: "https://v/sse", key: "amk_test", spawnImpl });

  assert.equal(result, null);
  assert.deepEqual(calls, ["list"]);
});

test("the claude config writer never truncates the live state file it cannot replace", () => {
  const home = tempHome();
  const target = path.join(home, ".claude.json");
  const existing = { projects: { "/repo": { history: ["a", "b"] } }, mcpServers: {} };
  fs.writeFileSync(target, JSON.stringify(existing));
  // A rename onto a read-only *directory* is what a failed write looks like
  // from the caller's side; simulate the failure by making the temp write
  // impossible and assert the original file survived it intact.
  const spawnImpl = noClaudeCli;
  fs.chmodSync(home, 0o500);
  try {
    assert.throws(() => writeClaudeConfig({ ...opts(home), spawnImpl }));
  } finally {
    fs.chmodSync(home, 0o700);
  }

  assert.deepEqual(JSON.parse(fs.readFileSync(target, "utf8")), existing);
});

test("the claude config writer leaves no temp file behind on success", () => {
  const home = tempHome();

  writeClaudeConfig(opts(home));

  assert.deepEqual(
    fs.readdirSync(home).filter((name) => name.includes(".tmp")),
    [],
  );
});

// ── Manifest-driven writing ───────────────────────────────────────────────────

import { writeClientConfig, detectFromManifest } from "../src/clients.js";

const URLS = { sse: "https://v.example/sse", "streamable-http": "https://v.example/mcp" };

const hermesEntry = {
  id: "hermes",
  label: "Hermes Agent",
  detect: [".hermes"],
  method: "yaml",
  path: "~/.hermes/config.yaml",
  key_path: ["mcp_servers", "archivum"],
  transport: "streamable-http",
  env_file: "~/.hermes/.env",
  env_var: "ARCHIVUM_KEY",
};

test("a yaml client gets its entry nested under an existing top-level key", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".hermes"), { recursive: true });
  // A duplicate `mcp_servers:` would be invalid YAML, so an existing key must
  // be merged into rather than appended after.
  fs.writeFileSync(
    path.join(home, ".hermes", "config.yaml"),
    "model: hermes-4\nmcp_servers:\n  fs:\n    command: npx\n",
  );

  writeClientConfig(hermesEntry, { home, urls: URLS, key: "amk_abc" });

  const written = fs.readFileSync(path.join(home, ".hermes", "config.yaml"), "utf8");
  assert.equal(written.match(/^mcp_servers:/gm).length, 1);
  assert.match(written, /model: hermes-4/);
  assert.match(written, /fs:/);
  assert.match(written, /archivum:/);
});

test("a yaml client with no config at all gets the top-level key created", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".hermes"), { recursive: true });

  writeClientConfig(hermesEntry, { home, urls: URLS, key: "amk_abc" });

  const written = fs.readFileSync(path.join(home, ".hermes", "config.yaml"), "utf8");
  assert.match(written, /^mcp_servers:/m);
  assert.match(written, /url: "https:\/\/v\.example\/mcp"/);
});

test("a client that resolves env vars gets a reference, never the key itself", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".hermes"), { recursive: true });

  writeClientConfig(hermesEntry, { home, urls: URLS, key: "amk_secret" });

  const config = fs.readFileSync(path.join(home, ".hermes", "config.yaml"), "utf8");
  const env = fs.readFileSync(path.join(home, ".hermes", ".env"), "utf8");
  // The config is the file people paste into issues and sync to dotfile repos.
  assert.ok(!config.includes("amk_secret"));
  assert.match(config, /\$\{env:ARCHIVUM_KEY\}/);
  assert.match(env, /^ARCHIVUM_KEY=amk_secret$/m);
});

test("re-linking replaces the key in the env file rather than appending a second", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".hermes"), { recursive: true });
  fs.writeFileSync(path.join(home, ".hermes", ".env"), "OTHER=1\nARCHIVUM_KEY=amk_old\n");

  writeClientConfig(hermesEntry, { home, urls: URLS, key: "amk_new" });

  const env = fs.readFileSync(path.join(home, ".hermes", ".env"), "utf8");
  assert.ok(!env.includes("amk_old"));
  assert.match(env, /OTHER=1/);
  assert.equal(env.match(/ARCHIVUM_KEY=/g).length, 1);
});

test("re-linking a yaml client does not stack duplicate blocks", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".hermes"), { recursive: true });

  writeClientConfig(hermesEntry, { home, urls: URLS, key: "amk_1" });
  writeClientConfig(hermesEntry, { home, urls: URLS, key: "amk_2" });

  const written = fs.readFileSync(path.join(home, ".hermes", "config.yaml"), "utf8");
  assert.equal(written.match(/archivum:/g).length, 1);
});

test("a streamable-http json client records the transport it needs", () => {
  const home = tempHome();
  const entry = {
    id: "openclaw",
    label: "OpenClaw",
    method: "json",
    path: "~/.openclaw/openclaw.json",
    key_path: ["mcpServers", "archivum"],
    transport: "streamable-http",
  };

  writeClientConfig(entry, { home, urls: URLS, key: "amk_abc" });

  const written = JSON.parse(fs.readFileSync(path.join(home, ".openclaw", "openclaw.json"), "utf8"));
  // Omitting this leaves the client on SSE, where it fails with 405 rather
  // than degrading to something that works.
  assert.equal(written.mcpServers.archivum.transport, "streamable-http");
  assert.equal(written.mcpServers.archivum.url, "https://v.example/mcp");
});

test("a json client merges into a nested key path without dropping siblings", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".openclaw"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".openclaw", "openclaw.json"),
    JSON.stringify({ mcp: { servers: { other: { url: "x" } } }, theme: "dark" }),
  );
  const entry = {
    id: "openclaw", label: "OpenClaw", method: "json",
    path: "~/.openclaw/openclaw.json",
    key_path: ["mcp", "servers", "archivum"], transport: "sse",
  };

  writeClientConfig(entry, { home, urls: URLS, key: "amk_abc" });

  const written = JSON.parse(fs.readFileSync(path.join(home, ".openclaw", "openclaw.json"), "utf8"));
  assert.equal(written.theme, "dark");
  assert.equal(written.mcp.servers.other.url, "x");
  assert.ok(written.mcp.servers.archivum);
});

test("detection reads the manifest, so a new client needs no code change", () => {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".hermes"), { recursive: true });

  const found = detectFromManifest(home, [hermesEntry, { id: "nope", detect: [".nope"] }]);

  assert.deepEqual(found.map((c) => c.id), ["hermes"]);
});
