import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";

import {
  gitTrackedFiles,
  indexCommand,
  discardArchive,
  packFiles,
  selectFiles,
  uploadRepo,
  walkFiles,
} from "../src/index-repo.js";
// Through the namespace too, so a helper that does not exist yet fails its own
// tests rather than the whole file at import.
import * as indexRepo from "../src/index-repo.js";

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

test("a filename that tar would read as an option is refused, not packed", () => {
  // git permits these names. GNU tar reads `-T` lines as arguments, so
  // `--checkpoint-action=exec=...` in a repository would run a command on the
  // machine doing the indexing.
  const root = tempRepo({ "app.ts": "x\n" });

  assert.throws(
    () => packFiles(root, ["--checkpoint=1", "--checkpoint-action=exec=sh evil.sh"]),
    /begin with "-"/,
  );
});

test("packed paths are written so tar cannot mistake one for a flag", () => {
  const root = tempRepo({ "app.ts": "x\n" });
  const archive = packFiles(root, ["app.ts"]);

  try {
    const listing = execFileSync("tar", ["-tzf", archive], { encoding: "utf8" });
    // `./app.ts` rather than `app.ts`: a leading ./ can never be read as an option.
    assert.match(listing, /\.\/app\.ts/);
  } finally {
    discardArchive(archive);
  }
});

test("the archive lives in a private directory, not a predictable temp path", () => {
  const root = tempRepo({ "app.ts": "x\n" });

  const archive = packFiles(root, ["app.ts"]);

  try {
    // A PID-derived name under the shared temp dir is readable by other local
    // users and pre-creatable as a symlink.
    assert.ok(!archive.includes(String(process.pid)));
    assert.match(path.dirname(archive), /archivum-pack-/);
    assert.equal(fs.statSync(path.dirname(archive)).mode & 0o077, 0);
  } finally {
    discardArchive(archive);
  }
});

test("discardArchive removes the whole private directory", () => {
  const root = tempRepo({ "app.ts": "x\n" });
  const archive = packFiles(root, ["app.ts"]);
  const dir = path.dirname(archive);

  discardArchive(archive);

  assert.equal(fs.existsSync(dir), false);
});

// ── Naming an upload ──────────────────────────────────────────────────────────
//
// The archive leaves `.git` behind, so the server cannot read an uploaded
// repo's remote: the name the CLI sends is the namespace. It must follow the
// same rule as the server's register_repo — explicit --name, else owner-repo
// from the origin remote, else the directory — and slug the remote exactly as
// apps/backend/archivum/code_repos.py `_identity_from_remote_url` does, so a
// repo uploaded from a laptop and the same repo registered by path on the
// server land in one namespace.

function linkedHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-home-"));
  fs.mkdirSync(path.join(home, ".archivum"), { recursive: true });
  fs.writeFileSync(
    path.join(home, ".archivum", "connection.json"),
    JSON.stringify({ base_url: "https://v.example", key: "amk_1" }),
  );
  return home;
}

/** A checkout at `<parent>/<dir>` that git (stubbed) says has `remote` as origin. */
function checkoutIn(parent, dir) {
  const root = path.join(fs.mkdtempSync(path.join(os.tmpdir(), `archivum-${parent}-`)), dir);
  fs.mkdirSync(root);
  fs.writeFileSync(path.join(root, "app.ts"), "export const a = 1\n");
  return root;
}

/** git answering for checkouts whose origin is given per root; tar runs for real. */
function gitWithRemotes(remotes) {
  return (bin, args, opts) => {
    if (bin !== "git") return spawnSync(bin, args, opts);
    const root = args[1];
    const command = args.slice(2).join(" ");
    if (command === "rev-parse --show-toplevel" && root in remotes) {
      return { status: 0, stdout: `${root}\n` };
    }
    if (command === "remote get-url origin" && remotes[root]) {
      return { status: 0, stdout: `${remotes[root]}\n` };
    }
    // Not a checkout git can list (ls-files), or no origin: fail like git does.
    return { status: 128, stdout: "", stderr: "fatal" };
  };
}

async function uploadedName(args, { cwd, spawnImpl, t }) {
  t.mock.method(console, "log", () => {});
  let sentName = null;
  await indexCommand(args, {
    home: linkedHome(),
    cwd,
    spawnImpl,
    fetchImpl: async (_url, init) => {
      sentName = init.body.get("name");
      return { ok: true, json: async () => ({ name: sentName, files: 1, nodes: 1, edges: 0, pages: 1 }) };
    },
  });
  return sentName;
}

test("two repos in same-named directories upload under two different names", async (t) => {
  const widgets = checkoutIn("a", "work");
  const sprockets = checkoutIn("b", "work");
  const spawnImpl = gitWithRemotes({
    [widgets]: "https://github.com/acme/widgets.git",
    [sprockets]: "git@github.com:acme/sprockets.git",
  });

  const first = await uploadedName([], { cwd: widgets, spawnImpl, t });
  const second = await uploadedName([], { cwd: sprockets, spawnImpl, t });

  assert.notEqual(first, second);
  assert.ok(![first, second].includes("work"), `neither may be the directory name: ${first}, ${second}`);
  assert.equal(first, "acme-widgets");
  assert.equal(second, "acme-sprockets");
});

test("a misleading checkout directory does not name the upload", async (t) => {
  const root = checkoutIn("m", "nixos");
  const spawnImpl = gitWithRemotes({ [root]: "https://github.com/perceo-ai/conductor-arch.git" });

  assert.equal(await uploadedName([], { cwd: root, spawnImpl, t }), "perceo-ai-conductor-arch");
});

test("an explicit --name still wins over the remote", async (t) => {
  const root = checkoutIn("n", "nixos");
  const spawnImpl = gitWithRemotes({ [root]: "https://github.com/perceo-ai/conductor-arch.git" });

  assert.equal(await uploadedName(["--name", "chosen"], { cwd: root, spawnImpl, t }), "chosen");
  assert.equal(await uploadedName(["--name=also-chosen"], { cwd: root, spawnImpl, t }), "also-chosen");
});

test("with no git remote the upload falls back to the directory name", async (t) => {
  const root = checkoutIn("r", "atlas");
  // A git checkout with no origin, and then not a git checkout at all.
  assert.equal(await uploadedName([], { cwd: root, spawnImpl: gitWithRemotes({ [root]: null }), t }), "atlas");
  assert.equal(await uploadedName([], { cwd: root, spawnImpl: noGit, t }), "atlas");
});

test("a subdirectory of a checkout does not borrow the whole repo's name", async (t) => {
  // git answers from inside a subdirectory too; two subdirectories of one
  // monorepo uploaded on their own must not collide on the monorepo's name.
  const mono = checkoutIn("s", "mono");
  const backend = path.join(mono, "backend");
  fs.mkdirSync(backend);
  fs.writeFileSync(path.join(backend, "app.py"), "x = 1\n");
  const spawnImpl = (bin, args, opts) => {
    if (bin === "git" && args.slice(2).join(" ") === "rev-parse --show-toplevel") {
      return { status: 0, stdout: `${mono}\n` };
    }
    if (bin === "git" && args.slice(2).join(" ") === "remote get-url origin") {
      return { status: 0, stdout: "https://github.com/acme/mono.git\n" };
    }
    return gitWithRemotes({})(bin, args, opts);
  };

  assert.equal(await uploadedName([], { cwd: backend, spawnImpl, t }), "backend");
});

// The same vectors as tests/test_code_repo_identity.py, so the two sides are
// held to one answer.
for (const url of [
  "https://github.com/perceo-ai/conductor-arch.git",
  "https://github.com/perceo-ai/conductor-arch",
  "git@github.com:perceo-ai/conductor-arch.git",
  "ssh://git@gitlab.example.com:2222/perceo-ai/conductor-arch.git",
  "https://github.com/Perceo-AI/Conductor-Arch.git/",
]) {
  test(`remote ${url} names the repo as the server does`, () => {
    assert.equal(indexRepo.identityFromRemoteUrl(url), "perceo-ai-conductor-arch");
  });
}

test("characters a path segment cannot hold are slugged as the server slugs them", () => {
  assert.equal(indexRepo.identityFromRemoteUrl("https://host/team space/my repo!.git"), "team-space-my-repo");
  assert.equal(indexRepo.identityFromRemoteUrl("https://host/a%20b/c.d_e.git?x=1#frag"), "a-20b-c.d_e");
  assert.equal(indexRepo.identityFromRemoteUrl("file:///srv/git/Foo.git"), "git-foo");
});

for (const url of ["", "   ", "https://github.com/", "git@github.com:solo.git"]) {
  test(`remote ${JSON.stringify(url)} gives no name`, () => {
    assert.equal(indexRepo.identityFromRemoteUrl(url), null);
  });
}

test("a real checkout with an origin names its upload after the remote", async (t) => {
  const root = checkoutIn("g", "nixos");
  try {
    execFileSync("git", ["-C", root, "init", "-q"], { stdio: "pipe" });
    execFileSync("git", ["-C", root, "remote", "add", "origin", "https://github.com/perceo-ai/conductor-arch.git"], {
      stdio: "pipe",
    });
  } catch {
    t.skip("git is not available");
    return;
  }

  assert.equal(await uploadedName([], { cwd: root, spawnImpl: spawnSync, t }), "perceo-ai-conductor-arch");
});
