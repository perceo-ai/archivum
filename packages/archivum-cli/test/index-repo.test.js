import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";

import {
  gitTrackedFiles,
  indexCommand,
  packFiles,
  selectFiles,
  uploadRepo,
  walkFiles,
} from "../src/index-repo.js";

function tempRepo(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-repo-"));
  for (const [name, content] of Object.entries(files)) {
    const target = path.join(root, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content);
  }
  return root;
}

// "This is not a git checkout", which is the directory-walk path. Only `git`
// is stubbed: `tar` must still really run, or packing is never exercised.
const noGit = (bin, args, opts) =>
  bin === "git"
    ? { error: Object.assign(new Error("ENOENT"), { code: "ENOENT" }) }
    : spawnSync(bin, args, opts);

test("the walk skips directories nobody wants indexed", () => {
  const root = tempRepo({
    "src/main.py": "print(1)\n",
    "node_modules/left-pad/index.js": "module.exports = 1\n",
    "__pycache__/main.pyc": "x",
    ".git/config": "[core]\n",
  });

  const found = walkFiles(root);

  assert.deepEqual(found.sort(), [path.join("src", "main.py")]);
});

test("binary files are dropped even when git tracks them", () => {
  const root = tempRepo({ "src/main.py": "print(1)\n" });
  // A NUL byte is what makes this binary, not the extension.
  fs.writeFileSync(path.join(root, "data.txt"), Buffer.from([0x41, 0x00, 0x42]));

  const { selected, skipped } = selectFiles(root, { spawnImpl: noGit });

  assert.ok(selected.includes(path.join("src", "main.py")));
  assert.ok(!selected.includes("data.txt"));
  assert.equal(skipped.binary, 1);
});

test("files with obviously non-source extensions are skipped without being read", () => {
  const root = tempRepo({ "logo.png": "not really a png", "app.ts": "export const a = 1\n" });

  const { selected, skipped } = selectFiles(root, { spawnImpl: noGit });

  assert.deepEqual(selected, ["app.ts"]);
  assert.equal(skipped.extension, 1);
});

test("very large files are skipped rather than uploaded", () => {
  const root = tempRepo({ "app.ts": "export const a = 1\n" });
  fs.writeFileSync(path.join(root, "huge.sql"), "x".repeat(3 * 1024 * 1024));

  const { selected, skipped } = selectFiles(root, { spawnImpl: noGit });

  assert.deepEqual(selected, ["app.ts"]);
  assert.equal(skipped.large, 1);
});

test("symlinks are never followed out of the repository", () => {
  const root = tempRepo({ "app.ts": "export const a = 1\n" });
  const secret = path.join(os.tmpdir(), `archivum-secret-${process.pid}`);
  fs.writeFileSync(secret, "PRIVATE\n");
  fs.symlinkSync(secret, path.join(root, "link.ts"));

  const { selected } = selectFiles(root, { spawnImpl: noGit });

  // Following it would upload a file outside the directory the user named.
  assert.deepEqual(selected, ["app.ts"]);
});

test("gitignored files are excluded, because git decides what is in the repo", (t) => {
  const root = tempRepo({
    "app.ts": "export const a = 1\n",
    ".gitignore": "secrets.env\n",
    "secrets.env": "TOKEN=hunter2\n",
  });
  try {
    execFileSync("git", ["-C", root, "init", "-q"], { stdio: "pipe" });
  } catch {
    t.skip("git is not available");
    return;
  }

  const tracked = gitTrackedFiles(root);

  assert.ok(tracked.includes("app.ts"));
  // Reimplementing .gitignore would be a second, worse implementation; this
  // asserts we delegate rather than guess.
  assert.ok(!tracked.includes("secrets.env"));
});

test("packFiles produces an archive containing exactly the chosen files", () => {
  const root = tempRepo({ "src/app.ts": "export const a = 1\n", "README.md": "# hi\n" });

  const archive = packFiles(root, ["src/app.ts", "README.md"]);

  try {
    const listing = execFileSync("tar", ["-tzf", archive], { encoding: "utf8" });
    assert.match(listing, /src\/app\.ts/);
    assert.match(listing, /README\.md/);
  } finally {
    fs.rmSync(archive, { force: true });
  }
});

test("uploadRepo sends the device key and surfaces the server's refusal", async () => {
  const calls = [];
  const root = tempRepo({ "app.ts": "x\n" });
  const archive = packFiles(root, ["app.ts"]);

  const ok = await uploadRepo({
    baseUrl: "https://v.example",
    key: "amk_1",
    name: "demo",
    archive,
    fetchImpl: async (url, init) => {
      calls.push({ url, auth: init.headers.Authorization });
      return { ok: true, json: async () => ({ name: "demo", files: 1, nodes: 2, edges: 3, pages: 1 }) };
    },
  });

  assert.equal(calls[0].url, "https://v.example/api/repos/upload");
  assert.equal(calls[0].auth, "Bearer amk_1");
  assert.equal(ok.files, 1);

  await assert.rejects(
    uploadRepo({
      baseUrl: "https://v.example", key: "amk_1", name: "demo", archive,
      fetchImpl: async () => ({ ok: false, status: 400, json: async () => ({ detail: "Refused 'x': links are not allowed" }) }),
    }),
    /links are not allowed/,
  );
  fs.rmSync(archive, { force: true });
});

test("index refuses to run on a machine that is not linked", async () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));

  await assert.rejects(
    indexCommand([], { home, cwd: tempRepo({ "a.ts": "x\n" }) }),
    /not linked/,
  );
});

test("index uploads the current directory under its own name", async (t) => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));
  fs.mkdirSync(path.join(home, ".archivum"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".archivum", "connection.json"),
    JSON.stringify({ base_url: "https://v.example", key: "amk_1" }),
  );
  const root = tempRepo({ "src/app.ts": "export const a = 1\n" });
  t.mock.method(console, "log", () => {});
  let sentName = null;

  await indexCommand([], {
    home,
    cwd: root,
    spawnImpl: noGit,
    fetchImpl: async (_url, init) => {
      sentName = init.body.get("name");
      return { ok: true, json: async () => ({ name: sentName, files: 1, nodes: 1, edges: 0, pages: 1 }) };
    },
  });

  assert.equal(sentName, path.basename(root));
});

test("index refuses a directory with nothing indexable rather than uploading nothing", async () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));
  fs.mkdirSync(path.join(home, ".archivum"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".archivum", "connection.json"),
    JSON.stringify({ base_url: "https://v.example", key: "amk_1" }),
  );
  const root = tempRepo({ "logo.png": "binary-ish" });

  await assert.rejects(
    indexCommand([], { home, cwd: root, spawnImpl: noGit, fetchImpl: async () => ({ ok: true }) }),
    /no text files/,
  );
});
