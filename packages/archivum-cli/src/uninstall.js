import fs from "node:fs";
import path from "node:path";
import { composeCommand, ensureDockerReady, runCompose } from "./docker.js";
import { askBool, ensureRoot, parseOptions } from "./util.js";

export function safeToRemoveInstallDir(root) {
  const resolved = path.resolve(root);
  if (resolved === path.parse(resolved).root || resolved === path.resolve(process.env.HOME ?? "")) {
    return { ok: false, reason: `refusing to remove unsafe install directory: ${resolved}` };
  }
  if (resolved.split(path.sep).filter(Boolean).length < 2) {
    return { ok: false, reason: `refusing to remove shallow install directory: ${resolved}` };
  }
  for (const required of ["docker-compose.yml", ".env.example"]) {
    if (!fs.existsSync(path.join(resolved, required))) {
      return { ok: false, reason: `refusing to remove ${resolved}; missing expected Archivum file: ${required}` };
    }
  }
  return { ok: true, reason: "" };
}

export async function uninstallCommand(args) {
  const { flags } = parseOptions(args);
  const root = ensureRoot();
  const compose = ensureDockerReady();
  const downArgs = ["down", "--remove-orphans"];
  if (flags.has("volumes")) downArgs.push("--volumes");
  if (flags.has("images")) downArgs.push("--rmi", "local");

  if (!flags.has("yes") && !flags.has("y")) {
    const ok = await askBool("Continue?", !(flags.has("volumes") || flags.has("files")));
    if (!ok) {
      console.log("Cancelled.");
      return;
    }
  }

  const base = composeCommand(compose, { useImages: true });
  if (flags.has("dry-run")) {
    console.log([base.join(" "), ...downArgs].join(" "));
  } else {
    runCompose(base, downArgs);
  }

  if (flags.has("files")) {
    const check = safeToRemoveInstallDir(root);
    if (!check.ok) throw new Error(check.reason);
    if (flags.has("dry-run")) console.log(`rm -rf ${root}`);
    else fs.rmSync(root, { recursive: true, force: true });
  }
  console.log("Archivum uninstall step completed.");
}
