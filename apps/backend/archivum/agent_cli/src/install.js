import { ensureDockerReady, composeCommand, runCompose } from "./docker.js";
import { askBool, askText, parseOptions, ensureRoot } from "./util.js";
import { DEFAULTS, envNeedsConfiguration, generateSecret, loadEnv, saveEnv, secretDefault } from "./env.js";

export async function installCommand(args) {
  const { flags, values } = parseOptions(args);
  const root = ensureRoot();
  const useImages = !flags.has("build");
  const assumeYes = flags.has("yes") || flags.has("y");
  const compose = ensureDockerReady();
  const env = loadEnv(root);
  const next = { ...DEFAULTS, ...env.values };

  const setValues = values.get("set");
  for (const assignment of Array.isArray(setValues) ? setValues : setValues ? [setValues] : []) {
    const [key, ...rest] = assignment.split("=");
    if (!key || rest.length === 0) throw new Error(`Invalid --set value '${assignment}'. Expected KEY=VALUE.`);
    next[key] = rest.join("=");
  }

  if (envNeedsConfiguration(next) && !assumeYes) {
    next.OWNER_USERNAME = await askText("Owner username", next.OWNER_USERNAME || "admin", { required: true });
    next.OWNER_PASSWORD = await askText("Owner password", secretDefault(next.OWNER_PASSWORD), { required: true, secret: true });
    if (!secretDefault(next.JWT_SECRET)) next.JWT_SECRET = generateSecret(48);
    if (!secretDefault(next.MCP_API_KEY)) next.MCP_API_KEY = generateSecret(32);
    next.PUBLIC_WIKI_ENABLED = (await askBool("Expose the entire wiki publicly as read-only at /public?", next.PUBLIC_WIKI_ENABLED === "true")) ? "true" : "false";
    next.ANTHROPIC_API_KEY = await askText("Anthropic API key", secretDefault(next.ANTHROPIC_API_KEY), { required: next.LLM_EXTRACTION_PROVIDER === "anthropic" || next.LLM_SYNTHESIS_PROVIDER === "anthropic", secret: true });
  } else {
    if (!secretDefault(next.JWT_SECRET)) next.JWT_SECRET = generateSecret(48);
    if (!secretDefault(next.MCP_API_KEY)) next.MCP_API_KEY = generateSecret(32);
  }

  saveEnv(env.envPath, next);
  const base = composeCommand(compose, { useImages });
  const upArgs = useImages ? ["up", "-d", "--no-build"] : ["up", "-d", "--build"];
  runCompose(base, upArgs);
  console.log("Archivum install completed.");
}
