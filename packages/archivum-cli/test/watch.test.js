import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  findTranscripts,
  readSeen,
  redactSecrets,
  sweep,
  uploadTranscript,
  watchCommand,
} from "../src/watch.js";

function tempHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));
}

function linkedHome({ transcriptDirs = ["~/.claude/projects"] } = {}) {
  const home = tempHome();
  fs.mkdirSync(path.join(home, ".archivum"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".archivum", "connection.json"),
    JSON.stringify({
      base_url: "https://v.example",
      key: "amk_1",
      transcript_dirs: transcriptDirs,
    }),
  );
  return home;
}

function writeTranscript(home, name, content) {
  const file = path.join(home, ".claude", "projects", name);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
  return file;
}

// ── Redaction ─────────────────────────────────────────────────────────────────
// Transcripts are the largest privacy surface in the product: everything ever
// typed in a session. These run before anything leaves the machine.

test("provider API keys are stripped", () => {
  const out = redactSecrets('key is sk-ant-api03-AAAABBBBCCCCDDDDEEEE and sk-proj-1234567890abcdefgh');

  assert.ok(!out.includes("AAAABBBBCCCCDDDDEEEE"));
  assert.ok(!out.includes("1234567890abcdefgh"));
});

test("github and slack tokens are stripped", () => {
  const out = redactSecrets("ghp_abcdefghijklmnopqrstuvwxyz0123 and xoxb-123456789012-abcdefgh");

  assert.ok(!out.includes("abcdefghijklmnopqrstuvwxyz0123"));
  assert.ok(!out.includes("xoxb-123456789012-abcdefgh"));
});

test("archivum's own keys are stripped, including the provisioning token", () => {
  const out = redactSecrets("amk_aaaaaaaaaaaaaaaaaaaaaaaa arch1p_bbbbbbbbbbbbbbbbbbbbbbbb");

  assert.ok(!out.includes("amk_aaaaaaaaaaaaaaaaaaaaaaaa"));
  // A transcript that captured the setup command would otherwise upload the
  // credential that links every machine.
  assert.ok(!out.includes("arch1p_bbbbbbbbbbbbbbbbbbbbbbbb"));
});

test("private keys are stripped whole, not line by line", () => {
  const pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\nMIIdef\n-----END RSA PRIVATE KEY-----";

  const out = redactSecrets(`here: ${pem}`);

  assert.ok(!out.includes("MIIabc"));
  assert.match(out, /PRIVATE KEY REDACTED/);
});

test("assignments are stripped whatever the secret looks like", () => {
  const out = redactSecrets('DATABASE_PASSWORD=hunter2hunter2 and "api_key": "zzzzzzzzzzzz"');

  assert.ok(!out.includes("hunter2hunter2"));
  assert.ok(!out.includes("zzzzzzzzzzzz"));
});

test("ordinary prose survives redaction", () => {
  const text = "The fix was to check the token expiry with <= rather than <.";

  assert.equal(redactSecrets(text), text);
});

// ── Finding and sending ───────────────────────────────────────────────────────

test("transcripts are found recursively under the directories the manifest named", () => {
  const home = linkedHome();
  writeTranscript(home, "project-a/session.jsonl", "{}\n");
  writeTranscript(home, "project-b/nested/other.jsonl", "{}\n");
  writeTranscript(home, "project-a/notes.txt", "not a transcript");

  const found = findTranscripts(home, ["~/.claude/projects"]);

  assert.equal(found.length, 2);
  assert.ok(found.every((f) => f.endsWith(".jsonl")));
});

test("a directory that does not exist is not an error", () => {
  const home = tempHome();

  assert.deepEqual(findTranscripts(home, ["~/.nothing/here"]), []);
});

test("uploads are redacted, not raw", async () => {
  const home = linkedHome();
  writeTranscript(home, "a/session.jsonl", '{"text":"my key is sk-ant-api03-SECRETSECRETSECRET"}\n');
  let uploaded = null;

  await sweep({
    home,
    state: { base_url: "https://v.example", key: "amk_1" },
    directories: ["~/.claude/projects"],
    log: () => {},
    fetchImpl: async (_url, init) => {
      uploaded = await init.body.get("transcript").text();
      return { ok: true, json: async () => ({ interface: "claude_code_import", results: [] }) };
    },
  });

  assert.ok(uploaded);
  assert.ok(!uploaded.includes("SECRETSECRETSECRET"));
});

test("an unchanged transcript is not sent twice", async () => {
  const home = linkedHome();
  writeTranscript(home, "a/session.jsonl", "{}\n");
  let uploads = 0;
  const fetchImpl = async () => {
    uploads += 1;
    return { ok: true, json: async () => ({ interface: "x", results: [] }) };
  };
  const options = {
    home,
    state: { base_url: "https://v.example", key: "amk_1" },
    directories: ["~/.claude/projects"],
    log: () => {},
    fetchImpl,
  };

  await sweep(options);
  await sweep(options);

  assert.equal(uploads, 1);
});

test("a transcript that grew is sent again", async () => {
  const home = linkedHome();
  const file = writeTranscript(home, "a/session.jsonl", "{}\n");
  let uploads = 0;
  const options = {
    home,
    state: { base_url: "https://v.example", key: "amk_1" },
    directories: ["~/.claude/projects"],
    log: () => {},
    fetchImpl: async () => {
      uploads += 1;
      return { ok: true, json: async () => ({ interface: "x", results: [] }) };
    },
  };

  await sweep(options);
  fs.writeFileSync(file, '{}\n{"more":true}\n');
  fs.utimesSync(file, new Date(Date.now() + 5000), new Date(Date.now() + 5000));
  await sweep(options);

  assert.equal(uploads, 2);
});

test("one rejected transcript does not stop the others and is not retried forever", async () => {
  const home = linkedHome();
  writeTranscript(home, "a/bad.jsonl", "not json\n");
  writeTranscript(home, "a/good.jsonl", "{}\n");
  const attempts = [];
  const options = {
    home,
    state: { base_url: "https://v.example", key: "amk_1" },
    directories: ["~/.claude/projects"],
    log: () => {},
    fetchImpl: async (_url, init) => {
      const name = init.body.get("filename");
      attempts.push(name);
      if (name === "bad.jsonl") {
        return { ok: false, status: 400, json: async () => ({ detail: { detail: "cannot parse transcript" } }) };
      }
      return { ok: true, json: async () => ({ interface: "x", results: [] }) };
    },
  };

  const first = await sweep(options);
  await sweep(options);

  assert.equal(first.sent, 1);
  assert.equal(first.failed, 1);
  // Both recorded, so the second pass sends nothing at all.
  assert.equal(attempts.length, 2);
  assert.ok(Object.keys(readSeen(home)).length === 2);
});

test("uploadTranscript posts to the route the capture router actually serves", async () => {
  // The capture router is mounted at /api/sources, not /api. Getting this
  // wrong is a 404 that only shows up against a running server, which is
  // exactly how it was found.
  let seen = null;

  await uploadTranscript({
    baseUrl: "https://v.example",
    key: "amk_1",
    file: "session.jsonl",
    text: "{}",
    fetchImpl: async (url) => {
      seen = url;
      return { ok: true, json: async () => ({ interface: "x", results: [] }) };
    },
  });

  assert.equal(seen, "https://v.example/api/sources/capture/upload");
});

test("uploadTranscript surfaces the server's reason", async () => {
  await assert.rejects(
    uploadTranscript({
      baseUrl: "https://v",
      key: "amk_1",
      file: "session.jsonl",
      text: "{}",
      fetchImpl: async () => ({
        ok: false,
        status: 400,
        json: async () => ({ detail: { detail: "no importer for .jsonl" } }),
      }),
    }),
    /no importer/,
  );
});

test("watch refuses to run on a machine that is not linked", async () => {
  await assert.rejects(watchCommand(["--once"], { home: tempHome() }), /not linked/);
});

test("watch says what to do when no transcript directories are known", async () => {
  const home = linkedHome({ transcriptDirs: [] });

  await assert.rejects(watchCommand(["--once"], { home }), /connect --auto/);
});

test("watch --once makes a single pass and returns", async () => {
  const home = linkedHome();
  writeTranscript(home, "a/session.jsonl", "{}\n");
  const logs = [];
  let uploads = 0;

  await watchCommand(["--once"], {
    home,
    log: (line) => logs.push(line),
    fetchImpl: async () => {
      uploads += 1;
      return { ok: true, json: async () => ({ interface: "x", results: [] }) };
    },
  });

  assert.equal(uploads, 1);
  assert.match(logs.join("\n"), /1 of 1 transcripts captured/);
});
