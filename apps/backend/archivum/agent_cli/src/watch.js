import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";

import { parseOptions, writeFileAtomic } from "./util.js";

// The server's transcript watcher reads a bind mount. The mount is on the
// server; the transcripts are here. A mount does not cross machines, so the
// watcher runs where the files are and ships them over the wire instead.
//
// Parsing stays on the server: it already has an importer per client, and a
// second implementation in JavaScript would drift from it immediately. This
// file decides *what* to send and *what to strip*, and nothing more.

const STATE_DIR = ".archivum";
const SEEN_FILE = "captured.json";
const DEFAULT_INTERVAL_MS = 60_000;
const MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024;

// Redaction happens before anything leaves the machine. These are shapes, not
// a guarantee: a secret that looks like prose survives, which is why the
// transcript upload is opt-out per directory as well.
const SECRET_PATTERNS = [
  [/\b(sk-[A-Za-z0-9_-]{16,})\b/g, "sk-REDACTED"],
  [/\b(sk-ant-[A-Za-z0-9_-]{16,})\b/g, "sk-ant-REDACTED"],
  [/\b(ghp_[A-Za-z0-9]{20,})\b/g, "ghp_REDACTED"],
  [/\b(gho_|ghs_|ghu_|ghr_)[A-Za-z0-9]{20,}\b/g, "gh_REDACTED"],
  [/\b(amk_[A-Za-z0-9_-]{20,})\b/g, "amk_REDACTED"],
  [/\b(arch1p?_[A-Za-z0-9_-]{20,})\b/g, "arch1_REDACTED"],
  [/\b(AKIA[0-9A-Z]{16})\b/g, "AKIA_REDACTED"],
  [/\b(xox[baprs]-[A-Za-z0-9-]{10,})\b/g, "xox-REDACTED"],
  [/\bAIza[0-9A-Za-z_-]{30,}\b/g, "AIza_REDACTED"],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, "[PRIVATE KEY REDACTED]"],
  // Assignments are how most other secrets appear: TOKEN=..., "api_key": "..."
  [/((?:api[_-]?key|secret|password|passwd|token)["']?\s*[:=]\s*["']?)([^\s"',;]{8,})/gi, "$1REDACTED"],
];

export function redactSecrets(text) {
  let out = text;
  for (const [pattern, replacement] of SECRET_PATTERNS) out = out.replace(pattern, replacement);
  return out;
}

function seenPath(home) {
  return path.join(home, STATE_DIR, SEEN_FILE);
}

export function readSeen(home) {
  const file = seenPath(home);
  if (!fs.existsSync(file)) return {};
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    // A corrupt ledger means re-uploading, which capture deduplicates by
    // content hash. Losing the ledger is cheap; refusing to run is not.
    return {};
  }
}

export function writeSeen(home, seen) {
  writeFileAtomic(seenPath(home), `${JSON.stringify(seen, null, 2)}\n`);
}

function expandHome(p, home) {
  return p.startsWith("~/") ? path.join(home, p.slice(2)) : p;
}

/** Every transcript file under the directories the manifest named. */
export function findTranscripts(home, directories) {
  const found = [];
  for (const directory of directories) {
    const root = expandHome(directory, home);
    if (!fs.existsSync(root)) continue;
    const stack = [root];
    while (stack.length) {
      const current = stack.pop();
      let entries;
      try {
        entries = fs.readdirSync(current, { withFileTypes: true });
      } catch {
        continue;
      }
      for (const entry of entries) {
        const full = path.join(current, entry.name);
        if (entry.isSymbolicLink()) continue;
        if (entry.isDirectory()) stack.push(full);
        else if (entry.isFile() && /\.(jsonl|json)$/.test(entry.name)) found.push(full);
      }
    }
  }
  return found;
}

export async function uploadTranscript({ baseUrl, key, file, text, fetchImpl = fetch }) {
  const form = new FormData();
  form.append("transcript", new Blob([text], { type: "application/json" }), path.basename(file));
  form.append("filename", path.basename(file));
  const response = await fetchImpl(`${baseUrl}/api/capture/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}` },
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail?.detail ?? body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Upload failed (HTTP ${response.status}).`);
  }
  return response.json();
}

/** One pass: send transcripts that changed since the last pass. */
export async function sweep({ home, state, directories, fetchImpl = fetch, log = console.log }) {
  const seen = readSeen(home);
  const files = findTranscripts(home, directories);
  let sent = 0;
  let failed = 0;

  for (const file of files) {
    let stats;
    try {
      stats = fs.statSync(file);
    } catch {
      continue;
    }
    if (stats.size > MAX_TRANSCRIPT_BYTES) continue;

    // Size plus mtime rather than a hash of every file on every pass: hashing
    // a few hundred megabytes each minute to find nothing changed is the kind
    // of background process people uninstall.
    const stamp = `${stats.size}:${Math.floor(stats.mtimeMs)}`;
    if (seen[file] === stamp) continue;

    let text;
    try {
      text = fs.readFileSync(file, "utf8");
    } catch {
      continue;
    }
    try {
      await uploadTranscript({
        baseUrl: state.base_url,
        key: state.key,
        file,
        text: redactSecrets(text),
        fetchImpl,
      });
      seen[file] = stamp;
      sent += 1;
    } catch (error) {
      // One unparseable transcript must not stop the rest, and must not be
      // retried forever: record it so the next pass moves on.
      failed += 1;
      seen[file] = stamp;
      log(`archivum: skipped ${path.basename(file)} — ${error.message}`);
    }
  }

  writeSeen(home, seen);
  return { sent, failed, scanned: files.length };
}

export async function watchCommand(
  args,
  { home = os.homedir(), fetchImpl = fetch, log = console.log, sleep } = {},
) {
  const { flags, values } = parseOptions(args);

  const statePath = path.join(home, STATE_DIR, "connection.json");
  if (!fs.existsSync(statePath)) {
    throw new Error("This machine is not linked. Run: archivum connect --auto");
  }
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));

  // Recorded at link time from the server's manifest, so the directories a
  // client writes to are described in one place rather than two.
  const directories = state.transcript_dirs ?? [];
  if (directories.length === 0) {
    throw new Error(
      "No transcript directories are known for this machine. Re-run `archivum connect --auto` " +
        "against a server that serves the client registry.",
    );
  }

  const once = flags.has("once");
  const interval = Number(values.get("interval") ?? 0) * 1000 || DEFAULT_INTERVAL_MS;
  const wait = sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));

  do {
    const result = await sweep({ home, state, directories, fetchImpl, log });
    if (result.sent > 0 || once) {
      log(
        `archivum: ${result.sent} of ${result.scanned} transcripts captured` +
          (result.failed ? `, ${result.failed} skipped` : ""),
      );
    }
    if (!once) await wait(interval);
  } while (!once);
}

export { createHash };
