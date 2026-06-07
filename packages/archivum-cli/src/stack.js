import { composeCommand, ensureDockerReady, runCompose } from "./docker.js";
import { ensureRoot, parseOptions } from "./util.js";

export async function stackCommand(args) {
  ensureRoot();
  const [action, target] = args;
  const { values } = parseOptions(args.slice(1));
  const service = values.get("service") ?? target;
  const compose = composeCommand(ensureDockerReady(), { useImages: false });

  if (action === "up") return runCompose(compose, ["up", "-d"]);
  if (action === "down") return runCompose(compose, ["down"]);
  if (action === "restart") return runCompose(compose, ["restart"]);
  if (action === "ps") return runCompose(compose, ["ps"]);
  if (action === "build") return runCompose(compose, ["build"]);
  if (action === "logs") return runCompose(compose, ["logs", "-f", ...(service ? [service] : [])]);
  if (action === "shell") {
    if (target === "backend") return runCompose(compose, ["exec", "backend", "bash"]);
    if (target === "frontend") return runCompose(compose, ["exec", "frontend", "sh"]);
  }
  throw new Error("Usage: archivum stack <up|down|restart|logs|ps|build|shell>");
}
