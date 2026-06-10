import { loadEnv, saveEnv } from "./env.js";
import { ensureRoot } from "./util.js";

export async function configCommand(args) {
  const [action, key, value] = args;
  const env = loadEnv(ensureRoot());
  if (action === "get") {
    if (key) console.log(env.values[key] ?? "");
    else console.log(JSON.stringify(env.values, null, 2));
    return;
  }
  if (action === "set") {
    if (!key || value === undefined) throw new Error("Usage: archivum config set KEY VALUE");
    saveEnv(env.envPath, { ...env.values, [key]: value });
    console.log(`Set ${key}.`);
    return;
  }
  if (action === "doctor") {
    console.log(`Config file: ${env.envPath}`);
    console.log(`MCP API key: ${env.values.MCP_API_KEY ? "set" : "missing"}`);
    return;
  }
  throw new Error("Usage: archivum config <get|set|doctor>");
}
