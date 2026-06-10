import { spawnSync } from "node:child_process";

export function composeCommand(compose, { useImages = true } = {}) {
  if (!useImages) return [...compose];
  return [...compose, "-f", "docker-compose.yml", "-f", "docker-compose.images.yml"];
}

export function commandExists(command) {
  return spawnSync(command, ["--version"], { stdio: "ignore" }).status === 0;
}

export function run(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: options.cwd ?? process.cwd(),
    env: options.env ?? process.env,
    encoding: "utf8",
    stdio: options.capture === false ? "inherit" : "pipe",
  });
}

export function findComposeCommand() {
  if (commandExists("docker")) {
    const result = run("docker", ["compose", "version"]);
    if (result.status === 0) return ["docker", "compose"];
  }
  if (commandExists("docker-compose")) {
    const result = run("docker-compose", ["version"]);
    if (result.status === 0) return ["docker-compose"];
  }
  return null;
}

export function ensureDockerReady() {
  const compose = findComposeCommand();
  if (!compose) throw new Error("Docker Compose was not found. Install Docker, then re-run the command.");
  const result = run("docker", ["info"]);
  if (result.status !== 0) throw new Error("Docker is not running or this user cannot access it.");
  return compose;
}

export function runCompose(compose, args, options = {}) {
  const [command, ...baseArgs] = compose;
  return run(command, [...baseArgs, ...args], { ...options, capture: options.capture ?? false });
}
