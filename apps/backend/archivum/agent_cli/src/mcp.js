import { loadEnv } from "./env.js";
import { ensureRoot, parseOptions } from "./util.js";

export async function mcpCommand(args) {
  const [action, ...rest] = args;
  if (action !== "config") throw new Error("Usage: archivum mcp config [--client claude|cursor|sse]");
  const { values } = parseOptions(rest);
  const client = values.get("client") ?? "claude";
  const { values: env } = loadEnv(ensureRoot());
  const key = env.MCP_API_KEY ?? "";

  if (client === "claude") {
    console.log(JSON.stringify({
      archivum: {
        command: "docker",
        args: ["exec", "-i", "archivum-mcp", "python", "-m", "archivum.mcp.server", "--stdio"],
        env: { MCP_API_KEY: key },
      },
    }, null, 2));
    return;
  }

  console.log(JSON.stringify({
    mcpServers: {
      archivum: {
        url: "http://localhost:8001/sse",
        headers: { Authorization: `Bearer ${key}` },
      },
    },
  }, null, 2));
}
