import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

import { writeFileAtomic } from "./util.js";

const BEGIN = "# >>> archivum >>>";
const END = "# <<< archivum <<<";
const SERVER_NAME = "archivum";

// Everything this file writes is fenced between these markers, or confined to
// one key it owns. A setup tool that rewrites a config file wholesale destroys
// hand-written settings it never understood, and the user finds out later.

function readJson(file) {
  if (!fs.existsSync(file)) return {};
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    // A config we cannot parse is a config we must not overwrite silently.
    throw new Error(`${file} is not valid JSON. Fix or move it, then re-run.`);
  }
}

function expandHome(p, home) {
  return p.startsWith("~/") ? path.join(home, p.slice(2)) : p;
}

// ── Format writers ────────────────────────────────────────────────────────────
// Each takes the resolved file, the key path it owns, and the entry to place
// there. They know nothing about which client they are serving.

function writeJsonEntry(file, keyPath, entry) {
  const config = readJson(file);
  let cursor = config;
  for (const segment of keyPath.slice(0, -1)) {
    cursor[segment] = { ...(cursor[segment] ?? {}) };
    cursor = cursor[segment];
  }
  cursor[keyPath[keyPath.length - 1]] = entry;
  return writeFileAtomic(file, `${JSON.stringify(config, null, 2)}\n`);
}

function fencedBlock(lines, indent = "") {
  return [`${indent}${BEGIN}`, ...lines.map((l) => `${indent}${l}`), `${indent}${END}`, ""].join("\n");
}

function stripFence(text, indent = "") {
  return text.replace(
    new RegExp(`${indent}${BEGIN}[\\s\\S]*?${indent}${END}\\n?`, "g"),
    "",
  );
}

function writeTomlEntry(file, keyPath, { url, key }) {
  const existing = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  // A fenced block rather than a TOML parse: the CLI has no dependencies, and
  // rewriting only what we own keeps hand-written settings untouched.
  const stripped = stripFence(existing);
  const block = fencedBlock([
    `[${keyPath.join(".")}]`,
    `url = "${url}"`,
    `http_headers = { Authorization = "Bearer ${key}" }`,
  ]);
  return writeFileAtomic(
    file,
    `${stripped.trimEnd()}\n${stripped.trim() ? "\n" : ""}${block}`.trimStart(),
  );
}

// YAML without a parser, which is only safe because of how narrow this is: one
// fenced block, nested under one top-level key. Appending a second
// `mcp_servers:` would be a duplicate key and invalid YAML, so when the key
// already exists the block goes inside it rather than after it.
function writeYamlEntry(file, keyPath, { url, keyRef }) {
  const [root, name] = keyPath;
  const existing = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  const stripped = stripFence(existing, "  ");
  const block = fencedBlock(
    [
      `${name}:`,
      `  url: "${url}"`,
      "  headers:",
      `    Authorization: "Bearer ${keyRef}"`,
    ],
    "  ",
  );

  const lines = stripped.split("\n");
  const rootAt = lines.findIndex((line) => new RegExp(`^${root}\\s*:`).test(line));
  if (rootAt === -1) {
    const base = stripped.trim() ? `${stripped.trimEnd()}\n\n` : "";
    return writeFileAtomic(file, `${base}${root}:\n${block}`);
  }
  lines.splice(rootAt + 1, 0, block.replace(/\n$/, ""));
  return writeFileAtomic(file, lines.join("\n"));
}

// Secrets go here when the client can interpolate them, so the config file it
// syncs or shares holds a reference rather than a live key.
function writeEnvFile(file, variable, value) {
  const existing = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  const withoutOurs = existing
    .split("\n")
    .filter((line) => !new RegExp(`^\\s*(export\\s+)?${variable}\\s*=`).test(line))
    .join("\n")
    .trimEnd();
  const body = withoutOurs ? `${withoutOurs}\n` : "";
  writeFileAtomic(file, `${body}${variable}=${value}\n`);
}

// ── The generic engine ────────────────────────────────────────────────────────

/** Write one client's config from its manifest entry. Returns a description. */
export function writeClientConfig(entry, { home, urls, key, spawnImpl = spawnSync }) {
  const url = urls[entry.transport] ?? urls.sse;

  if (entry.method === "command") {
    const viaCommand = runClientCommand(entry, { url, key, spawnImpl });
    if (viaCommand) return viaCommand;
    if (!entry.fallback) return null;
    entry = { ...entry, ...entry.fallback };
  }

  const file = expandHome(entry.path, home);

  // The key is only referenced indirectly when the client resolves env vars.
  let keyRef = key;
  if (entry.env_file && entry.env_var) {
    writeEnvFile(expandHome(entry.env_file, home), entry.env_var, key);
    keyRef = `\${env:${entry.env_var}}`;
  }

  // Each writer returns the path it wrote, which is what `connect` reports:
  // naming the exact file is what lets someone check the result by opening it.
  if (entry.method === "json") {
    return writeJsonEntry(file, entry.key_path, {
      url,
      headers: { Authorization: `Bearer ${keyRef}` },
      ...(entry.transport === "streamable-http" ? { transport: "streamable-http" } : {}),
    });
  }
  if (entry.method === "toml") {
    return writeTomlEntry(file, entry.key_path, { url, key: keyRef });
  }
  if (entry.method === "yaml") {
    return writeYamlEntry(file, entry.key_path, { url, keyRef });
  }
  return null;
}

function runClientCommand(entry, { url, key, spawnImpl }) {
  const [bin, ...rest] = entry.command.map((arg) =>
    arg.replace("{url}", url).replace("{key}", key),
  );
  const run = (args) => spawnImpl(bin, args, { encoding: "utf8", stdio: "pipe" });
  const probe = run(["mcp", "list"]);
  // No binary on PATH (ENOENT) means the file writer is the only option.
  if (probe?.error || probe?.status !== 0) return null;
  // `add` refuses a name that already exists, so a re-link would fail; remove
  // first and ignore the result, which is also what makes this idempotent.
  run(["mcp", "remove", SERVER_NAME, "--scope", "user"]);
  const added = run(rest);
  if (added?.error || added?.status !== 0) return null;
  return `${entry.label} (${bin} mcp add --scope user)`;
}

/** Which clients from the manifest are present on this machine. */
export function detectFromManifest(home, clients) {
  return clients.filter((c) => (c.detect ?? []).some((m) => fs.existsSync(path.join(home, m))));
}

// ── Named writers, kept as the manifest's offline fallback ────────────────────
// A machine that cannot reach `GET /api/mcp/clients` — an older server, or a
// network that drops midway — still links the three clients that predate the
// registry rather than failing outright.

export function streamableHttpUrl(sseUrl) {
  const trimmed = sseUrl.replace(/\/+$/, "");
  if (trimmed.endsWith("/mcp")) return trimmed;
  if (trimmed.endsWith("/sse")) return `${trimmed.slice(0, -"/sse".length)}/mcp`;
  return `${trimmed}/mcp`;
}

export const BUILTIN_CLIENTS = [
  {
    id: "claude",
    label: "Claude Code",
    detect: [".claude.json", ".claude"],
    method: "command",
    command: [
      "claude", "mcp", "add", "--scope", "user",
      "--transport", "sse", SERVER_NAME, "{url}",
      "--header", "Authorization: Bearer {key}",
    ],
    fallback: { method: "json", path: "~/.claude.json", key_path: ["mcpServers", SERVER_NAME] },
    transport: "sse",
  },
  {
    id: "cursor",
    label: "Cursor",
    detect: [".cursor"],
    method: "json",
    path: "~/.cursor/mcp.json",
    key_path: ["mcpServers", SERVER_NAME],
    transport: "sse",
  },
  {
    id: "codex",
    label: "Codex",
    detect: [".codex"],
    method: "toml",
    path: "~/.codex/config.toml",
    key_path: ["mcp_servers", SERVER_NAME],
    transport: "streamable-http",
  },
];

const byId = (id) => BUILTIN_CLIENTS.find((c) => c.id === id);
const urlsFor = (sseUrl) => ({ sse: sseUrl, "streamable-http": streamableHttpUrl(sseUrl) });

export function addClaudeServerViaCli({ sseUrl, key, spawnImpl = spawnSync }) {
  return runClientCommand(byId("claude"), { url: sseUrl, key, spawnImpl });
}

export function writeClaudeConfig({ home, sseUrl, key, spawnImpl = spawnSync }) {
  return writeClientConfig(byId("claude"), { home, urls: urlsFor(sseUrl), key, spawnImpl });
}

export function writeCursorConfig({ home, sseUrl, key }) {
  return writeClientConfig(byId("cursor"), { home, urls: urlsFor(sseUrl), key });
}

export function writeCodexConfig({ home, sseUrl, key }) {
  return writeClientConfig(byId("codex"), { home, urls: urlsFor(sseUrl), key });
}

export const CLIENT_WRITERS = {
  claude: writeClaudeConfig,
  cursor: writeCursorConfig,
  codex: writeCodexConfig,
};

export function detectClients(home) {
  return detectFromManifest(home, BUILTIN_CLIENTS).map((c) => c.id);
}
