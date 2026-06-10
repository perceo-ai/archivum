import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { composeCommand, ensureDockerReady, runCompose } from "./docker.js";
import { ensureRoot, parseOptions } from "./util.js";

function runChecked(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit", encoding: "utf8" });
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed.`);
}

export async function updateCommand(args) {
  const { flags } = parseOptions(args);
  const root = ensureRoot();
  const useImages = !flags.has("build");
  const compose = ensureDockerReady();

  if (fs.existsSync(".git")) {
    runChecked("git", ["fetch", "--all", "--prune"]);
    runChecked("git", ["pull", "--ff-only"]);
  } else {
    console.log("Minimal install update through the packaged CLI is not yet destructive; keeping local runtime files in place.");
  }

  if (!fs.existsSync(`${root}/.env`) && fs.existsSync(`${root}/.env.example`)) {
    fs.copyFileSync(`${root}/.env.example`, `${root}/.env`);
  }

  const base = composeCommand(compose, { useImages });
  if (useImages) {
    runCompose(base, ["pull"]);
    runCompose(base, ["up", "-d", "--no-build", "--remove-orphans"]);
  } else {
    runCompose(base, ["build", "--pull"]);
    runCompose(base, ["up", "-d", "--build", "--remove-orphans"]);
  }
  console.log("Archivum update completed.");
}
