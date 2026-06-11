import { loadEnv } from "./env.js";
import { ensureRoot, parseOptions, readStdinIfAvailable } from "./util.js";

async function request(path, { method = "GET", body } = {}) {
  const { values } = loadEnv(ensureRoot());
  const response = await fetch(`http://localhost:8000${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${values.MCP_API_KEY ?? ""}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`);
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function print(value) {
  if (typeof value === "string") console.log(value);
  else console.log(JSON.stringify(value, null, 2));
}

export async function wikiCommand(args) {
  const [action, ...rest] = args;
  const { values, positionals } = parseOptions(rest);
  if (action === "ingest") return print(await request("/api/ingest", { method: "POST", body: { source: positionals.join(" ") } }));
  if (action === "search") return print(await request(`/api/search?q=${encodeURIComponent(positionals.join(" "))}`));
  if (action === "query") return print(await request("/api/query", { method: "POST", body: { question: positionals.join(" ") } }));
  if (action === "pages") return print(await request("/api/pages"));
  if (action === "open") return print(await request(`/api/pages/${encodeURIComponent(positionals[0] ?? "")}`));
  if (action === "lint") return print(await request("/api/lint"));
  if (action === "graph") return print(await request(`/api/graph/neighbors/${encodeURIComponent(positionals[0] ?? "")}`));
  if (action === "rebuild-indexes") return print(await request("/api/rebuild-indexes", { method: "POST" }));
  if (action === "write") {
    const stdin = await readStdinIfAvailable();
    const tags = values.get("tag");
    return print(await request("/api/pages", {
      method: "POST",
      body: {
        title: values.get("title") ?? positionals[0],
        slug: values.get("slug"),
        content: values.get("content") ?? stdin,
        tags: Array.isArray(tags) ? tags : tags ? [tags] : [],
      },
    }));
  }
  throw new Error("Usage: archivum wiki <ingest|search|query|pages|open|write|lint|graph|rebuild-indexes>");
}
