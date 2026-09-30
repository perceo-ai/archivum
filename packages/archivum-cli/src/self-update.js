import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { parseOptions } from "./util.js";

// The CLI on a linked machine came from `curl <server>/install | sh`, so the
// way to update it is to run that line again. The installer already does the
// right thing on a re-run: it replaces the CLI wholesale, keeps the device key,
// and refreshes the habits. This command only saves remembering the URL.
export function resolveInstallUrl(args, { home = os.homedir(), env = process.env } = {}) {
  const { values } = parseOptions(args);
  // Overrides first, and only then the saved connection: --base and
  // ARCHIVUM_URL are what someone reaches for when the saved state is the
  // problem, so a corrupt connection.json must not block them.
  let base = values.get("base") ?? env.ARCHIVUM_URL ?? null;
  if (!base) {
    const statePath = path.join(home, ".archivum", "connection.json");
    try {
      base = JSON.parse(fs.readFileSync(statePath, "utf8"))?.base_url ?? null;
    } catch {
      base = null;
    }
  }
  return base ? `${base.replace(/\/+$/, "")}/install` : null;
}

export function selfUpdateCommand(
  args,
  { home = os.homedir(), env = process.env, run = spawnSync, log = console.log } = {},
) {
  const url = resolveInstallUrl(args, { home, env });
  if (!url) {
    throw new Error(
      "Not linked, so there is no server to update from. Pass --base <url> or set ARCHIVUM_URL.",
    );
  }
  if (process.platform === "win32") {
    log(`Run in PowerShell: irm ${url}.ps1 | iex`);
    return;
  }
  log(`archivum: updating from ${url}`);
  // Download, then run: `curl | sh` reports sh's exit status, and sh exits 0
  // on the empty input a failed download leaves, so a dead server looked like
  // a finished update.
  const script =
    't=$(mktemp) && curl -fsSL "$1" -o "$t" && sh "$t"; s=$?; rm -f "$t"; exit $s';
  const result = run("sh", ["-c", script, "sh", url], { stdio: "inherit", env });
  if (result.status !== 0) throw new Error(`Update from ${url} failed.`);
}
