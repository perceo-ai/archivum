import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

import { parseOptions } from "./util.js";

// Indexing resolves paths on the server, which cannot see this machine's disk.
// So the client decides what to send and the server does the rest: same
// pipeline, same embeddings, no second code path.

const MAX_FILE_BYTES = 2 * 1024 * 1024;

// Extensions that are certainly not source. Everything else is offered, and
// anything that turns out to be binary is dropped by the content check below —
// an allow-list would silently skip whatever language it had not heard of.
const SKIP_EXTENSIONS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff", ".avif",
  ".pdf", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war",
  ".mp3", ".mp4", ".mov", ".avi", ".mkv", ".wav", ".flac", ".ogg", ".webm",
  ".woff", ".woff2", ".ttf", ".otf", ".eot",
  ".so", ".dylib", ".dll", ".exe", ".bin", ".o", ".a", ".class", ".pyc",
  ".db", ".sqlite", ".sqlite3", ".parquet", ".wasm",
]);

const SKIP_DIRECTORIES = new Set([
  "node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build",
  "target", ".next", ".nuxt", ".cache", "vendor", ".terraform", ".mypy_cache",
  ".pytest_cache", ".ruff_cache", "coverage", ".gradle", ".idea",
]);

/** Files git would track, which is `.gitignore` honoured exactly.
 *
 * Reimplementing `.gitignore` matching would be a second, worse implementation
 * of a spec with real corner cases. `-c` is tracked, `-o --exclude-standard`
 * is untracked-but-not-ignored: together, everything a developer would call
 * part of the repository.
 */
export function gitTrackedFiles(root, { spawnImpl = spawnSync } = {}) {
  const result = spawnImpl(
    "git",
    ["-C", root, "ls-files", "-co", "--exclude-standard"],
    { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
  );
  if (result?.error || result?.status !== 0) return null;
  return result.stdout.split("\n").filter(Boolean);
}

/** A directory walk for repositories that are not git checkouts. */
export function walkFiles(root, relative = "") {
  const found = [];
  for (const entry of fs.readdirSync(path.join(root, relative), { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue;
    const next = relative ? path.join(relative, entry.name) : entry.name;
    if (entry.isDirectory()) {
      if (SKIP_DIRECTORIES.has(entry.name) || entry.name.startsWith(".")) continue;
      found.push(...walkFiles(root, next));
    } else if (entry.isFile()) {
      found.push(next);
    }
  }
  return found;
}

// A NUL byte in the first few KB is what `git diff` uses to call a file
// binary, and it is right often enough to be the rule here too.
function looksBinary(file) {
  let handle;
  try {
    handle = fs.openSync(file, "r");
    const buffer = Buffer.alloc(8192);
    const read = fs.readSync(handle, buffer, 0, 8192, 0);
    return buffer.subarray(0, read).includes(0);
  } catch {
    return true;
  } finally {
    if (handle !== undefined) fs.closeSync(handle);
  }
}

export function selectFiles(root, { spawnImpl = spawnSync } = {}) {
  const candidates = gitTrackedFiles(root, { spawnImpl }) ?? walkFiles(root);
  const selected = [];
  // Counted apart rather than together: 'skipped 400 non-source' reads as a
  // problem when it is really node_modules, and as noise when it is not.
  const skipped = { binary: 0, large: 0, extension: 0, directory: 0 };

  for (const relative of candidates) {
    if (SKIP_EXTENSIONS.has(path.extname(relative).toLowerCase())) {
      skipped.extension += 1;
      continue;
    }
    if (relative.split(path.sep).some((part) => SKIP_DIRECTORIES.has(part))) {
      skipped.directory += 1;
      continue;
    }
    const absolute = path.join(root, relative);
    let stats;
    try {
      stats = fs.lstatSync(absolute);
    } catch {
      continue;
    }
    // Not followed: a symlink is a path into somewhere this machine did not
    // agree to upload.
    if (!stats.isFile() || stats.isSymbolicLink()) continue;
    if (stats.size > MAX_FILE_BYTES) {
      skipped.large += 1;
      continue;
    }
    if (looksBinary(absolute)) {
      skipped.binary += 1;
      continue;
    }
    selected.push(relative);
  }
  return { selected, skipped };
}

/** Pack the chosen files. Shells out to `tar`, which every target platform has.
 *
 * Two things here are security, not style.
 *
 * Every path is written as `./name`. GNU tar reads `-T` lines as arguments, so
 * a tracked file called `--checkpoint-action=exec=sh x` — a name git permits —
 * would otherwise be read as an option and run a command from the repository
 * on the machine doing the indexing. A leading `./` makes every line a path
 * and nothing else. Names that still begin with `-` after that are refused
 * rather than escaped, because a name needing an escape is not a name we
 * expected.
 *
 * The archive is built inside a private directory created with mkdtemp, not at
 * a predictable path in the shared temp directory. It holds the packed source
 * tree for the length of the upload; on a shared host a predictable path is
 * readable by other users and pre-creatable as a symlink.
 */
export function packFiles(root, files, { spawnImpl = spawnSync } = {}) {
  const unsafe = files.filter((file) => file.startsWith("-"));
  if (unsafe.length > 0) {
    throw new Error(
      `Refusing to pack ${unsafe.length} file(s) whose names begin with "-": ` +
        `${unsafe.slice(0, 3).join(", ")}. Such names are read as options by tar.`,
    );
  }

  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-pack-"));
  const listFile = path.join(workDir, "files.txt");
  const archive = path.join(workDir, "repo.tar.gz");
  fs.writeFileSync(listFile, `${files.map((file) => `./${file}`).join("\n")}\n`, { mode: 0o600 });
  try {
    const result = spawnImpl(
      "tar",
      ["-czf", archive, "-C", root, "-T", listFile],
      { encoding: "utf8" },
    );
    if (result?.error || result?.status !== 0) {
      throw new Error(`Could not pack the repository: ${result?.stderr ?? result?.error?.message}`);
    }
    return archive;
  } finally {
    fs.rmSync(listFile, { force: true });
  }
}

/** Remove the private directory an archive was packed into. */
export function discardArchive(archive) {
  try {
    fs.rmSync(path.dirname(archive), { recursive: true, force: true });
  } catch {
    // Cleanup failing must not fail an upload that already succeeded.
  }
}

export async function uploadRepo({ baseUrl, key, name, archive, fetchImpl = fetch }) {
  const form = new FormData();
  form.append("name", name);
  form.append(
    "archive",
    new Blob([fs.readFileSync(archive)], { type: "application/gzip" }),
    "repo.tar.gz",
  );
  const response = await fetchImpl(`${baseUrl}/api/repos/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}` },
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new Error(detail ?? `Indexing failed (HTTP ${response.status}).`);
  }
  return response.json();
}

export async function indexCommand(
  args,
  { home = os.homedir(), cwd = process.cwd(), fetchImpl = fetch, spawnImpl = spawnSync } = {},
) {
  const { values, positionals } = parseOptions(args);

  const statePath = path.join(home, ".archivum", "connection.json");
  if (!fs.existsSync(statePath)) {
    throw new Error("This machine is not linked. Run: archivum connect --auto");
  }
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));

  const root = path.resolve(cwd, positionals[0] ?? ".");
  if (!fs.existsSync(root)) throw new Error(`No such directory: ${root}`);
  const name = values.get("name") ?? path.basename(root);

  const { selected, skipped } = selectFiles(root, { spawnImpl });
  if (selected.length === 0) {
    throw new Error(`Nothing to index in ${root}: no text files were found.`);
  }

  console.log(`archivum: sending ${selected.length} files from ${root}`);
  const noise = [
    skipped.extension ? `${skipped.extension} non-source` : null,
    skipped.directory ? `${skipped.directory} in build or vendor dirs` : null,
    skipped.binary ? `${skipped.binary} binary` : null,
    skipped.large ? `${skipped.large} over 2MB` : null,
  ].filter(Boolean);
  if (noise.length) console.log(`  skipped ${noise.join(", ")}`);

  const archive = packFiles(root, selected, { spawnImpl });
  try {
    const repo = await uploadRepo({
      baseUrl: state.base_url,
      key: state.key,
      name,
      archive,
      fetchImpl,
    });
    console.log(
      `archivum: indexed "${repo.name}" — ${repo.files} files, ${repo.nodes} symbols, ${repo.edges} edges, ${repo.pages} pages.`,
    );
    console.log("  Your agents can now use retrieve_code_context and recall_fix for this repo.");
  } finally {
    discardArchive(archive);
  }
}
