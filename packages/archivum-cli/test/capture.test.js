import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { captureSessionCommand, parseTranscript, redactSecrets } from "../src/capture.js";
// Through the namespace too, so a helper that does not exist yet fails its own
// tests rather than the whole file at import.
import * as capture from "../src/capture.js";

function tempHome({ linked = true, capture = undefined } = {}) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-capture-"));
  if (linked) {
    fs.mkdirSync(path.join(home, ".archivum"), { recursive: true });
    fs.writeFileSync(
      path.join(home, ".archivum", "connection.json"),
      JSON.stringify({ base_url: "https://v.example/", key: "amk_1", ...(capture === undefined ? {} : { capture }) }),
    );
  }
  return home;
}

const LINES = [
  { type: "user", sessionId: "sess-1", timestamp: "2026-10-01T00:00:00Z", message: { role: "user", content: "why is the test red" } },
  {
    type: "assistant",
    sessionId: "sess-1",
    timestamp: "2026-10-01T00:00:01Z",
    message: {
      role: "assistant",
      content: [
        { type: "thinking", thinking: "the fixture is stale, do not say this out loud" },
        { type: "text", text: "Looking at the fixture." },
        { type: "tool_use", id: "t1", name: "Read", input: { file_path: "/tmp/x.py" } },
      ],
    },
  },
  {
    type: "user",
    sessionId: "sess-1",
    timestamp: "2026-10-01T00:00:02Z",
    message: { role: "user", content: [{ type: "tool_result", tool_use_id: "t1", content: "assert 1 == 2" }] },
  },
];

function transcriptFile(lines = LINES, { torn = false } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-transcript-"));
  const file = path.join(dir, "sess-1.jsonl");
  const text = lines.map((line) => JSON.stringify(line)).join("\n") + (torn ? '\n{"type":"assi' : "\n");
  fs.writeFileSync(file, text);
  return file;
}

function recordingFetch(response = { source_id: "src-1", deduplicated: false }) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options, body: JSON.parse(options.body) });
    return { ok: true, status: 200, json: async () => response };
  };
  return { calls, fetchImpl };
}

test("the parser mirrors the server's importer: text, tool calls, no hidden reasoning", () => {
  const { sessionId, startedAt, turns } = parseTranscript(
    fs.readFileSync(transcriptFile(), "utf8"),
  );
  assert.equal(sessionId, "sess-1");
  assert.equal(startedAt, "2026-10-01T00:00:00Z");
  assert.equal(turns.length, 2);
  assert.equal(turns[0].text, "why is the test red");
  assert.equal(turns[1].text, "Looking at the fixture.");
  assert.doesNotMatch(JSON.stringify(turns), /out loud/);
  assert.equal(turns[1].tool_calls[0].name, "Read");
  // The tool_result is folded into the call it answers, not emitted as a turn
  // of raw tool output.
  assert.equal(turns[1].tool_calls[0].result, "assert 1 == 2");
});

test("a half-written last line is skipped, not fatal", () => {
  // Claude Code appends while the session runs, so a hook that fires mid-write
  // reads a torn line. Refusing the file would mean never capturing one.
  const { turns } = parseTranscript(fs.readFileSync(transcriptFile(LINES, { torn: true }), "utf8"));
  assert.equal(turns.length, 2);
});

test("secret shapes are stripped before anything leaves the machine", () => {
  const scrubbed = redactSecrets("export ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstu");
  assert.doesNotMatch(scrubbed, /abcdefghij/);
});

test("a finished session is uploaded to /api/sources/capture", async () => {
  const home = tempHome();
  const { calls, fetchImpl } = recordingFetch();
  const transcript = transcriptFile();

  const result = await captureSessionCommand(["--transcript", transcript], {
    home,
    env: {},
    fetchImpl,
  });

  assert.equal(result.status, "uploaded");
  assert.equal(result.sourceId, "src-1");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://v.example/api/sources/capture");
  assert.equal(calls[0].options.headers.Authorization, "Bearer amk_1");
  assert.equal(calls[0].body.session_id, "sess-1");
  // The origin the server's own importer would give this file, so a later
  // import of the same transcript dedupes onto the same Source.
  assert.equal(calls[0].body.origin_uri, transcript);
  assert.equal(calls[0].body.turns.length, 2);
});

test("an unchanged transcript is not uploaded twice", async () => {
  // Server-side dedup makes it harmless but not free: /capture queues
  // distillation whether or not the content was new, and the Stop hook fires
  // at the end of every turn.
  const home = tempHome();
  const { calls, fetchImpl } = recordingFetch();
  const args = ["--transcript", transcriptFile()];

  assert.equal((await captureSessionCommand(args, { home, env: {}, fetchImpl })).status, "uploaded");
  const second = await captureSessionCommand(args, { home, env: {}, fetchImpl });

  assert.equal(second.status, "skipped");
  assert.equal(second.reason, "unchanged");
  assert.equal(calls.length, 1);
});

test("a session that grew since the last upload is sent again", async () => {
  const home = tempHome();
  const { calls, fetchImpl } = recordingFetch();
  const transcript = transcriptFile();

  await captureSessionCommand(["--transcript", transcript], { home, env: {}, fetchImpl });
  fs.appendFileSync(
    transcript,
    JSON.stringify({ type: "assistant", sessionId: "sess-1", message: { role: "assistant", content: "fixed it" } }) + "\n",
  );
  const second = await captureSessionCommand(["--transcript", transcript], { home, env: {}, fetchImpl });

  assert.equal(second.status, "uploaded");
  assert.equal(calls.length, 2);
  assert.equal(calls[1].body.turns.length, 3);
});

test("ARCHIVUM_CAPTURE=off uploads nothing", async () => {
  const home = tempHome();
  const { calls, fetchImpl } = recordingFetch();

  const result = await captureSessionCommand(["--transcript", transcriptFile()], {
    home,
    env: { ARCHIVUM_CAPTURE: "off" },
    fetchImpl,
  });

  assert.equal(result.reason, "opted-out");
  assert.equal(result.by, "ARCHIVUM_CAPTURE");
  assert.equal(calls.length, 0);
});

test('"capture": false in connection.json uploads nothing', async () => {
  const home = tempHome({ capture: false });
  const { calls, fetchImpl } = recordingFetch();

  const result = await captureSessionCommand(["--transcript", transcriptFile()], {
    home,
    env: {},
    fetchImpl,
  });

  assert.equal(result.reason, "opted-out");
  assert.equal(result.by, "connection.json");
  assert.equal(calls.length, 0);
});

// Rule 3 of the Stop hook: every one of these has to end the same way —
// nothing happens, nothing thrown, nothing printed.
test("a server that refuses, a vault that is gone, a file that is not there: all silent", async () => {
  const refuse = async () => ({ ok: false, status: 503, json: async () => ({}) });
  const explode = async () => {
    throw new Error("ECONNREFUSED");
  };

  const down = await captureSessionCommand(["--transcript", transcriptFile()], {
    home: tempHome(),
    env: {},
    fetchImpl: refuse,
  });
  assert.equal(down.status, "skipped");
  assert.equal(down.reason, "failed");

  const unreachable = await captureSessionCommand(["--transcript", transcriptFile()], {
    home: tempHome(),
    env: {},
    fetchImpl: explode,
  });
  assert.equal(unreachable.reason, "failed");

  const unlinked = await captureSessionCommand(["--transcript", transcriptFile()], {
    home: tempHome({ linked: false }),
    env: {},
    fetchImpl: async () => assert.fail("must not upload without a device key"),
  });
  assert.equal(unlinked.reason, "not-linked");

  const missing = await captureSessionCommand(["--transcript", "/tmp/definitely-not-here-x9.jsonl"], {
    home: tempHome(),
    env: {},
    fetchImpl: async () => assert.fail("must not upload a transcript it cannot read"),
  });
  assert.equal(missing.reason, "failed");

  const empty = await captureSessionCommand(["--transcript", transcriptFile([])], {
    home: tempHome(),
    env: {},
    fetchImpl: async () => assert.fail("must not upload an empty conversation"),
  });
  assert.equal(empty.reason, "no-turns");
});

test("a failed upload is retried on the next Stop, not marked as done", async () => {
  const home = tempHome();
  const transcript = transcriptFile();
  const failing = await captureSessionCommand(["--transcript", transcript], {
    home,
    env: {},
    fetchImpl: async () => ({ ok: false, status: 500, json: async () => ({}) }),
  });
  assert.equal(failing.reason, "failed");

  const { calls, fetchImpl } = recordingFetch();
  const retried = await captureSessionCommand(["--transcript", transcript], { home, env: {}, fetchImpl });
  assert.equal(retried.status, "uploaded");
  assert.equal(calls.length, 1);
});

// ── Redaction depth ───────────────────────────────────────────────────────────

test("a secret nested inside a tool input is scrubbed", () => {
  // The scrubber copied nested objects and arrays through untouched, so a
  // secret one level down left the machine verbatim.
  const out = capture.redactArguments({
    config: { token: "sk-abcdefghijklmnopqrstuv" },
    list: ["sk-ant-abcdefghijklmnopqrstuv"],
  });
  assert.ok(!JSON.stringify(out).includes("abcdefghijklmnopqrstuv"), JSON.stringify(out));
});

test("a secret-named key is scrubbed whatever its value looks like", () => {
  // The assignment pattern needs key and value in one string to fire, and a
  // structured tool input never puts them together.
  const out = capture.redactArguments({
    password: "hunter2",
    DB_PASSWORD: "short",
    nested: { authorization: "Basic abc" },
    harmless: "keep me",
  });
  assert.equal(out.password, "REDACTED");
  assert.equal(out.DB_PASSWORD, "REDACTED");
  assert.equal(out.nested.authorization, "REDACTED");
  assert.equal(out.harmless, "keep me");
});

test("redaction does not choke on odd shapes", () => {
  assert.deepEqual(capture.redactArguments({ n: 1, b: true, z: null }), {
    n: 1,
    b: true,
    z: null,
  });
  assert.deepEqual(capture.redactArguments({}), {});
});

test("a failed tool result keeps its text and its failure", () => {
  // `String(...)` on a block array yields "[object Object]", which threw away
  // the error text of every failed check; `is_error` was dropped entirely, so
  // the server defaulted the call to ok.
  const line = JSON.stringify({
    type: "assistant",
    message: {
      role: "assistant",
      content: [
        { type: "text", text: "running the suite" },
        { type: "tool_use", id: "t1", name: "Bash", input: { command: "pytest" } },
      ],
    },
  });
  const resultLine = JSON.stringify({
    type: "user",
    message: {
      role: "user",
      content: [
        {
          type: "tool_result",
          tool_use_id: "t1",
          is_error: true,
          content: [{ type: "text", text: "E   sqlite3.OperationalError: database is locked" }],
        },
      ],
    },
  });
  const { turns } = parseTranscript(`${line}\n${resultLine}\n`);
  const call = turns.flatMap((t) => t.tool_calls ?? []).find((c) => c.call_id === "t1");
  assert.ok(call, "the tool call should be present");
  assert.match(call.result, /database is locked/);
  assert.equal(call.ok, false);
});
