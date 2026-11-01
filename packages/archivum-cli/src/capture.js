import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";

import { parseOptions, writeFileAtomic } from "./util.js";

// Automatic capture, from the machine the sessions actually run on.
//
// The server's transcript watcher reads a directory the server can see. The
// owner's sessions run on a laptop, so that watcher never saw a single one of
// them and nothing the owner did reached the vault unless they remembered to
// call record_work. The transcript has to be shipped from here.
//
// This is a command, not a daemon: the Stop hook already observes the end of a
// session (scripts/archivum-stop-hook.sh), so it is also the cheapest place to
// hang the upload. Nothing runs between sessions.
//
// Parsing is a mirror of apps/backend/archivum/capture/importers/claude_code.py
// — the same JSONL shape, the same hidden-block rules — because only the client
// can read the file. Everything after parsing goes through the ordinary
// `POST /api/sources/capture`, so redaction, content addressing, dedup and the
// distillation queue are the ones every other capture path uses. There is no
// second write path into the store.

const STATE_DIR = ".archivum";
const UPLOADED_DIR = "captured-sessions";
const MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024;
const UPLOAD_TIMEOUT_MS = 20_000;
const INTERFACE = "claude_code_hook";

// Mirrors archivum.capture.redaction.HIDDEN_BLOCK_TYPES. Hidden reasoning is
// also stripped server-side; it is dropped here as well so it never crosses
// the network at all.
const HIDDEN_BLOCK_TYPES = new Set(["thinking", "reasoning", "redacted_thinking", "thoughts"]);

// Shapes, not a guarantee: a secret that looks like prose survives, which is
// why capture is opt-out per machine as well. Carried over from the deleted
// watcher, which stripped these before anything left the machine.
const SECRET_PATTERNS = [
  [/\bsk-ant-[A-Za-z0-9_-]{16,}\b/g, "sk-ant-REDACTED"],
  [/\bsk-[A-Za-z0-9_-]{16,}\b/g, "sk-REDACTED"],
  [/\bghp_[A-Za-z0-9]{20,}\b/g, "ghp_REDACTED"],
  [/\b(?:gho_|ghs_|ghu_|ghr_)[A-Za-z0-9]{20,}\b/g, "gh_REDACTED"],
  [/\bamk_[A-Za-z0-9_-]{20,}\b/g, "amk_REDACTED"],
  [/\barch1p?_[A-Za-z0-9_-]{20,}\b/g, "arch1_REDACTED"],
  [/\bAKIA[0-9A-Z]{16}\b/g, "AKIA_REDACTED"],
  [/\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, "xox-REDACTED"],
  [/\bAIza[0-9A-Za-z_-]{30,}\b/g, "AIza_REDACTED"],
  [
    /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
    "[PRIVATE KEY REDACTED]",
  ],
  // Assignments are how most other secrets appear: TOKEN=..., "api_key": "..."
  [
    /((?:api[_-]?key|secret|password|passwd|token)["']?\s*[:=]\s*["']?)([^\s"',;]{8,})/gi,
    "$1REDACTED",
  ],
];

export function redactSecrets(text) {
  let out = typeof text === "string" ? text : "";
  for (const [pattern, replacement] of SECRET_PATTERNS) out = out.replace(pattern, replacement);
  return out;
}

function visibleText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((block) => block && typeof block === "object" && block.type === "text")
    .map((block) => String(block.text ?? ""))
    .join("\n")
    .trim();
}

function toolUses(content) {
  if (!Array.isArray(content)) return [];
  return content
    .filter((block) => block && typeof block === "object" && block.type === "tool_use")
    .map((block) => ({
      name: String(block.name ?? ""),
      arguments: block.input && typeof block.input === "object" ? block.input : {},
      call_id: block.id ?? null,
    }));
}

function toolResults(content) {
  if (!Array.isArray(content)) return {};
  const out = {};
  for (const block of content) {
    if (!block || typeof block !== "object" || block.type !== "tool_result") continue;
    if (block.tool_use_id) out[block.tool_use_id] = String(block.content ?? "");
  }
  return out;
}

/** Turns from a Claude Code transcript, in the shape `/api/sources/capture` takes.
 *
 * A line that is not JSON is skipped rather than fatal. Claude Code appends to
 * this file while the session runs, so a hook firing mid-write reads a torn
 * last line — refusing the whole transcript for that would mean never
 * capturing a long session.
 */
export function parseTranscript(text) {
  const turns = [];
  let sessionId = "";
  let startedAt = "";
  const turnOfCall = new Map(); // tool_use id -> index in `turns`

  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let obj;
    try {
      obj = JSON.parse(trimmed);
    } catch {
      continue;
    }
    if (!obj || typeof obj !== "object" || obj.type === "summary") continue;
    sessionId = obj.sessionId ?? sessionId;
    startedAt = startedAt || obj.timestamp || "";

    const message = obj.message && typeof obj.message === "object" ? obj.message : {};
    const role = message.role ?? obj.type ?? "user";
    const content = message.content ?? "";

    // A tool_result answers a tool_use from an earlier turn: fill it in there
    // rather than emitting a turn of raw tool output, exactly as the server's
    // importer does.
    for (const [callId, result] of Object.entries(toolResults(content))) {
      const index = turnOfCall.get(callId);
      if (index === undefined) continue;
      for (const call of turns[index].tool_calls) {
        if (call.call_id === callId) call.result = redactSecrets(result);
      }
    }

    const calls = toolUses(content);
    const visible = visibleText(content);
    if (!visible && calls.length === 0) continue;

    turns.push({
      role: String(role),
      text: redactSecrets(visible),
      ts: String(obj.timestamp ?? ""),
      tool_calls: calls.map((call) => ({
        name: call.name,
        arguments: redactArguments(call.arguments),
        call_id: call.call_id,
        result: null,
      })),
    });
    for (const call of calls) {
      if (call.call_id) turnOfCall.set(call.call_id, turns.length - 1);
    }
  }

  return { sessionId, startedAt, turns };
}

function redactArguments(args) {
  const out = {};
  for (const [key, value] of Object.entries(args)) {
    out[key] = typeof value === "string" ? redactSecrets(value) : value;
  }
  return out;
}

/** `off` disables capture; anything else (including unset) leaves it on.
 *
 * Two switches because they answer different questions: the env var turns one
 * session or one shell off, and `"capture": false` in connection.json turns the
 * machine off for good.
 */
export function captureDisabled({ env, state }) {
  const flag = String(env?.ARCHIVUM_CAPTURE ?? "").trim().toLowerCase();
  if (["off", "0", "false", "no", "none"].includes(flag)) return "ARCHIVUM_CAPTURE";
  if (state && state.capture === false) return "connection.json";
  return null;
}

function stateDir(home, env) {
  return env?.ARCHIVUM_STATE_DIR || path.join(home, STATE_DIR);
}

export async function uploadConversation({ baseUrl, key, body, fetchImpl = fetch }) {
  const response = await fetchImpl(`${baseUrl.replace(/\/+$/, "")}/api/sources/capture`, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function capture(args, { home, env, fetchImpl }) {
  const { values } = parseOptions(args);
  const transcript = values.get("transcript");
  if (!transcript) return { status: "skipped", reason: "no-transcript" };

  const dir = stateDir(home, env);
  let state = null;
  try {
    state = JSON.parse(fs.readFileSync(path.join(dir, "connection.json"), "utf8"));
  } catch {
    return { status: "skipped", reason: "not-linked" };
  }
  if (!state?.base_url || !state?.key) return { status: "skipped", reason: "not-linked" };

  const disabled = captureDisabled({ env, state });
  if (disabled) return { status: "skipped", reason: "opted-out", by: disabled };

  const stats = fs.statSync(transcript);
  // A transcript this large is a runaway tool loop, not a conversation worth
  // remembering, and reading it would cost more memory than the session did.
  if (stats.size > MAX_TRANSCRIPT_BYTES) return { status: "skipped", reason: "too-large" };

  const parsed = parseTranscript(fs.readFileSync(transcript, "utf8"));
  if (parsed.turns.length === 0) return { status: "skipped", reason: "no-turns" };

  const body = {
    session_id: values.get("session-id") || parsed.sessionId || path.basename(transcript, ".jsonl"),
    interface: INTERFACE,
    started_at: parsed.startedAt,
    turns: parsed.turns,
    scope: values.get("scope") ?? "personal",
    // The absolute path, because that is what the server's own importer uses as
    // the origin of this file. Capture dedupes on (origin_uri, content_hash),
    // so re-sending an unchanged transcript — or importing the same file later
    // — lands on the Source that is already there instead of a second one.
    origin_uri: path.resolve(transcript),
  };

  const digest = createHash("sha256").update(JSON.stringify(body)).digest("hex");
  const marker = path.join(dir, UPLOADED_DIR, encodeURIComponent(body.session_id));
  // Server-side dedup makes a repeat upload harmless, but not free: the
  // endpoint queues distillation whether or not the content was new, and the
  // Stop hook fires at the end of every turn, so without this a long session
  // would re-distil the same transcript a dozen times.
  try {
    if (fs.readFileSync(marker, "utf8").trim() === digest) {
      return { status: "skipped", reason: "unchanged" };
    }
  } catch {
    // No marker, or an unreadable one: upload and let the server dedupe.
  }

  const result = await uploadConversation({
    baseUrl: state.base_url,
    key: state.key,
    body,
    fetchImpl,
  });
  writeFileAtomic(marker, `${digest}\n`);
  return {
    status: "uploaded",
    sourceId: result?.source_id ?? null,
    deduplicated: result?.deduplicated ?? null,
    turns: parsed.turns.length,
  };
}

/** Upload one session's transcript. Never throws, never prints.
 *
 * Rule 3 of the Stop hook, in JavaScript: a vault that is down, a key that is
 * gone, a half-written transcript. Every one of those has to end the same way —
 * nothing happens, exit 0 — because a session blocked or slowed by the memory
 * tool is a memory tool that gets uninstalled by lunch.
 */
export async function captureSessionCommand(
  args,
  { home = os.homedir(), env = process.env, fetchImpl = fetch } = {},
) {
  try {
    return await capture(args, { home, env, fetchImpl });
  } catch (error) {
    return { status: "skipped", reason: "failed", detail: error?.message ?? String(error) };
  }
}
