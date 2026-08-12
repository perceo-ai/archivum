import fs from "node:fs";
import path from "node:path";
import { composeCommand, ensureDockerReady, run } from "./docker.js";
import { ensureRoot, parseOptions } from "./util.js";

export const PRECIOUS_VOLUME_MOUNTS = [
  { volume: "wiki_data", path: "/data/wiki" },
  { volume: "raw_data", path: "/data/raw" },
  { volume: "db_data", path: "/data" },
];

const RECOVERABLE_FILES = [".env", "docker-compose.yml", "docker-compose.images.yml", "caddy/Caddyfile"];

function backupName(prefix = "backup", now = new Date()) {
  return `${prefix}-${now.toISOString().replace(/[:.]/g, "").replace("T", "-").replace("Z", "Z")}`;
}

export function dockerVolumeName(root, volume, projectName = "") {
  return `${projectName || path.basename(root)}_${volume}`;
}

export function discoverComposeProjectName(compose, root) {
  const base = composeCommand(compose, { useImages: true });
  const [command, ...args] = base;
  const result = run(command, [...args, "config", "--format", "json"], { cwd: root });
  if (result.status !== 0 || !result.stdout) return path.basename(root);
  try {
    return JSON.parse(result.stdout).name || path.basename(root);
  } catch {
    return path.basename(root);
  }
}

function tarCommand(root, backupDir, mount, projectName) {
  return [
    "docker",
    "run",
    "--rm",
    "-v",
    `${dockerVolumeName(root, mount.volume, projectName)}:/volume:ro`,
    "-v",
    `${backupDir}:/backup`,
    "alpine:3.20",
    "tar",
    "-czf",
    `/backup/${mount.volume}.tar.gz`,
    "-C",
    "/volume",
    ".",
  ];
}

function untarCommand(root, backupDir, mount, projectName) {
  return [
    "docker",
    "run",
    "--rm",
    "-v",
    `${dockerVolumeName(root, mount.volume, projectName)}:/volume`,
    "-v",
    `${backupDir}:/backup:ro`,
    "alpine:3.20",
    "sh",
    "-c",
    `rm -rf /volume/* /volume/.[!.]* /volume/..?* 2>/dev/null || true; tar -xzf /backup/${mount.volume}.tar.gz -C /volume`,
  ];
}

export function buildBackupPlan({ root, backupDir, compose, prefix = "pre-update", projectName = "" }) {
  const name = path.basename(backupDir) || backupName(prefix);
  const base = composeCommand(compose, { useImages: true });
  return {
    files: RECOVERABLE_FILES,
    volumes: PRECIOUS_VOLUME_MOUNTS,
    manifest: {
      name,
      created_at: new Date().toISOString(),
      files: RECOVERABLE_FILES,
      volumes: PRECIOUS_VOLUME_MOUNTS.map((mount) => mount.volume),
      compose_project: projectName || path.basename(root),
    },
    commands: [
      [...base, "stop", "backend", "mcp"],
      ...PRECIOUS_VOLUME_MOUNTS.map((mount) => tarCommand(root, backupDir, mount, projectName)),
      [...base, "start", "backend", "mcp"],
    ],
  };
}

export function buildRestorePlan({ root, backupDir, compose, projectName = "" }) {
  const base = composeCommand(compose, { useImages: true });
  return {
    files: RECOVERABLE_FILES,
    volumes: PRECIOUS_VOLUME_MOUNTS,
    commands: [
      [...base, "down"],
      ...PRECIOUS_VOLUME_MOUNTS.map((mount) => untarCommand(root, backupDir, mount, projectName)),
      [...base, "up", "-d"],
    ],
  };
}

function copyRecoverableFiles(root, backupDir, files = RECOVERABLE_FILES) {
  for (const relative of files) {
    const source = path.join(root, relative);
    if (!fs.existsSync(source)) continue;
    const target = path.join(backupDir, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(source, target);
  }
}

function restoreRecoverableFiles(root, backupDir, files = RECOVERABLE_FILES) {
  for (const relative of files) {
    const source = path.join(backupDir, relative);
    if (!fs.existsSync(source)) continue;
    const target = path.join(root, relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(source, target);
  }
}

function runCommand(command) {
  const [bin, ...args] = command;
  const result = run(bin, args, { capture: false });
  if (result.status !== 0) throw new Error(`${command.join(" ")} failed.`);
}

function runPlanCommands(commands) {
  for (const command of commands) runCommand(command);
}

function shellQuote(value) {
  if (/^[A-Za-z0-9_./:=@+-]+$/.test(value)) return value;
  return `'${value.replace(/'/g, "'\\''")}'`;
}

export function formatPlanCommands(commands) {
  return commands.map((command) => command.map((part) => shellQuote(String(part))).join(" ")).join("\n");
}

export function runBackupPlan(plan, runner = runCommand) {
  const [stopCommand, ...rest] = plan.commands;
  const startCommand = rest.at(-1);
  const archiveCommands = rest.slice(0, -1);

  runner(stopCommand);
  try {
    for (const command of archiveCommands) runner(command);
  } finally {
    runner(startCommand);
  }
}

export function validateBackupDir(backupDir) {
  const required = [
    "manifest.json",
    ...PRECIOUS_VOLUME_MOUNTS.map((mount) => `${mount.volume}.tar.gz`),
  ];
  const missing = required.filter((relative) => !fs.existsSync(path.join(backupDir, relative)));
  const invalid = [];
  for (const mount of PRECIOUS_VOLUME_MOUNTS) {
    const relative = `${mount.volume}.tar.gz`;
    const archive = path.join(backupDir, relative);
    if (!fs.existsSync(archive)) continue;
    const result = run("tar", ["-tzf", archive]);
    if (result.status !== 0) invalid.push(relative);
  }
  return { ok: missing.length === 0 && invalid.length === 0, missing, invalid };
}

export function createBackup({ root, compose, backupDir, prefix = "backup" }) {
  const resolvedBackupDir = backupDir ?? path.join(root, "backups", backupName(prefix));
  fs.mkdirSync(resolvedBackupDir, { recursive: true });
  const projectName = discoverComposeProjectName(compose, root);
  const plan = buildBackupPlan({ root, backupDir: resolvedBackupDir, compose, prefix, projectName });
  copyRecoverableFiles(root, resolvedBackupDir, plan.files);
  fs.writeFileSync(path.join(resolvedBackupDir, "manifest.json"), JSON.stringify(plan.manifest, null, 2) + "\n", "utf8");
  runBackupPlan(plan);
  return resolvedBackupDir;
}

export function restoreBackup({ root, compose, backupDir }) {
  if (!backupDir) throw new Error("Usage: archivum recovery restore <backup-dir>");
  const resolvedBackupDir = path.resolve(root, backupDir);
  if (!fs.existsSync(resolvedBackupDir)) throw new Error(`Backup directory not found: ${resolvedBackupDir}`);
  const validation = validateBackupDir(resolvedBackupDir);
  if (validation.invalid.length > 0) throw new Error(`Backup has invalid archives: ${validation.invalid.join(", ")}`);
  if (validation.missing.length > 0) throw new Error(`Backup is incomplete; missing: ${validation.missing.join(", ")}`);
  const projectName = discoverComposeProjectName(compose, root);
  const plan = buildRestorePlan({ root, backupDir: resolvedBackupDir, compose, projectName });
  runPlanCommands(plan.commands.slice(0, -1));
  restoreRecoverableFiles(root, resolvedBackupDir, plan.files);
  runPlanCommands(plan.commands.slice(-1));
  return resolvedBackupDir;
}

export async function recoveryCommand(args) {
  const { flags, values, positionals } = parseOptions(args);
  const [action, backupDirArg] = positionals;
  const root = ensureRoot();
  const compose = ensureDockerReady();
  const backupDir = values.get("dir") ?? backupDirArg;

  if (action === "backup") {
    if (flags.has("dry-run")) {
      const resolvedBackupDir = path.resolve(root, backupDir || path.join("backups", backupName("backup")));
      const projectName = discoverComposeProjectName(compose, root);
      const plan = buildBackupPlan({ root, backupDir: resolvedBackupDir, compose, projectName });
      console.log(formatPlanCommands(plan.commands));
      return;
    }
    const created = createBackup({
      root,
      compose,
      backupDir: backupDir ? path.resolve(root, backupDir) : undefined,
      prefix: flags.has("pre-update") ? "pre-update" : "backup",
    });
    console.log(`Archivum backup created: ${created}`);
    return;
  }

  if (action === "restore") {
    if (flags.has("dry-run")) {
      if (!backupDir) throw new Error("Usage: archivum recovery restore <backup-dir> --dry-run");
      const resolvedBackupDir = path.resolve(root, backupDir);
      const projectName = discoverComposeProjectName(compose, root);
      const plan = buildRestorePlan({ root, backupDir: resolvedBackupDir, compose, projectName });
      console.log(formatPlanCommands(plan.commands));
      return;
    }
    if (!flags.has("yes") && !flags.has("y")) {
      throw new Error("Restore is destructive. Re-run with --yes after verifying the backup path.");
    }
    const restored = restoreBackup({ root, compose, backupDir });
    console.log(`Archivum backup restored: ${restored}`);
    return;
  }

  if (action === "validate") {
    if (!backupDir) throw new Error("Usage: archivum recovery validate <backup-dir>");
    const resolvedBackupDir = path.resolve(root, backupDir);
    const validation = validateBackupDir(resolvedBackupDir);
    if (validation.invalid.length > 0) throw new Error(`Backup has invalid archives: ${validation.invalid.join(", ")}`);
    if (validation.missing.length > 0) throw new Error(`Backup is incomplete; missing: ${validation.missing.join(", ")}`);
    console.log(`Archivum backup is valid: ${resolvedBackupDir}`);
    return;
  }

  throw new Error("Usage: archivum recovery <backup|validate|restore> [backup-dir] [--yes]");
}
