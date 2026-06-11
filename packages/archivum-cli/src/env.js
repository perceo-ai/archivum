import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

export const PROVIDER_OPTIONS = ["anthropic", "openrouter", "openai_compat", "ollama"];
export const OPENAI_COMPAT_OPTIONS = ["openai", "together", "fireworks", "groq", "deepinfra", "azure", "custom"];
export const EMBED_OPTIONS = ["local", "openai_compat", "openrouter", "ollama"];

export const DEFAULTS = {
  ANTHROPIC_API_KEY: "",
  OPENROUTER_API_KEY: "",
  OPENROUTER_BASE_URL: "https://openrouter.ai/api/v1",
  JWT_SECRET: "",
  OWNER_PASSWORD: "",
  OWNER_USERNAME: "admin",
  MCP_API_KEY: "",
  ARCHIVUM_HOST: "",
  ARCHIVUM_FRONTEND_PORT: "8473",
  PUBLIC_WIKI_ENABLED: "false",
  EMBED_PROVIDER: "local",
  EMBED_MODEL: "BAAI/bge-small-en-v1.5",
  EMBED_DIM: "0",
  EMBED_OPENAI_COMPAT_PROVIDER: "openai",
  EMBED_BASE_URL: "",
  EMBED_API_KEY: "",
  EMBED_AZURE_API_VERSION: "2024-02-15-preview",
  OLLAMA_BASE_URL: "http://host.docker.internal:11434",
  LLM_EXTRACTION_PROVIDER: "anthropic",
  LLM_SYNTHESIS_PROVIDER: "anthropic",
  LLM_MODEL: "claude-haiku-4-5-20251001",
  LLM_SYNTHESIS_MODEL: "claude-sonnet-4-6",
  OPENAI_COMPAT_PROVIDER: "openai",
  OPENAI_COMPAT_BASE_URL: "",
  OPENAI_COMPAT_API_KEY: "",
  OPENAI_COMPAT_AZURE_API_VERSION: "2024-02-15-preview",
};

export function parseEnv(text) {
  const out = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (match) out[match[1]] = match[2];
  }
  return out;
}

export function isPlaceholderSecret(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return (
    !normalized ||
    normalized.includes("change-me") ||
    normalized === "changeme" ||
    normalized.includes("replace-in-production") ||
    normalized.includes("openssl rand") ||
    normalized.endsWith("...")
  );
}

export function secretDefault(value) {
  return isPlaceholderSecret(value) ? "" : value;
}

export function hasValue(values, key) {
  return Boolean(String(values[key] ?? "").trim());
}

export function hasSecret(values, key) {
  return !isPlaceholderSecret(values[key]);
}

export function envNeedsConfiguration(values) {
  for (const key of ["OWNER_PASSWORD", "JWT_SECRET", "MCP_API_KEY"]) {
    if (!hasSecret(values, key)) return true;
  }

  const selectedLlms = new Set([values.LLM_EXTRACTION_PROVIDER ?? "", values.LLM_SYNTHESIS_PROVIDER ?? ""]);
  if (selectedLlms.has("") || [...selectedLlms].some((provider) => !PROVIDER_OPTIONS.includes(provider))) return true;
  if (!hasValue(values, "LLM_MODEL") || !hasValue(values, "LLM_SYNTHESIS_MODEL")) return true;
  if (selectedLlms.has("anthropic") && !hasSecret(values, "ANTHROPIC_API_KEY")) return true;
  if (selectedLlms.has("openrouter") && (!hasValue(values, "OPENROUTER_BASE_URL") || !hasSecret(values, "OPENROUTER_API_KEY"))) return true;
  if (selectedLlms.has("openai_compat")) {
    if (!OPENAI_COMPAT_OPTIONS.includes(values.OPENAI_COMPAT_PROVIDER)) return true;
    if (["azure", "custom"].includes(values.OPENAI_COMPAT_PROVIDER) && !hasValue(values, "OPENAI_COMPAT_BASE_URL")) return true;
    if (!hasSecret(values, "OPENAI_COMPAT_API_KEY")) return true;
  }
  if (selectedLlms.has("ollama") && !hasValue(values, "OLLAMA_BASE_URL")) return true;

  const embedProvider = values.EMBED_PROVIDER ?? "";
  if (!EMBED_OPTIONS.includes(embedProvider)) return true;
  if (!hasValue(values, "EMBED_MODEL") || !hasValue(values, "EMBED_DIM")) return true;
  if (embedProvider === "openai_compat") {
    if (!OPENAI_COMPAT_OPTIONS.includes(values.EMBED_OPENAI_COMPAT_PROVIDER)) return true;
    if (["azure", "custom"].includes(values.EMBED_OPENAI_COMPAT_PROVIDER) && !hasValue(values, "EMBED_BASE_URL")) return true;
    if (!hasSecret(values, "EMBED_API_KEY")) return true;
  }
  if (embedProvider === "openrouter" && (!hasValue(values, "OPENROUTER_BASE_URL") || !hasSecret(values, "OPENROUTER_API_KEY"))) return true;
  if (embedProvider === "ollama" && !hasValue(values, "OLLAMA_BASE_URL")) return true;

  return false;
}

export function writeEnvText(existingText, values) {
  const lines = existingText ? existingText.split(/(?<=\n)/) : [];
  const seen = new Set();
  const output = [];
  const pattern = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=.*$/;

  for (const line of lines) {
    const match = line.trim().match(pattern);
    if (!match) {
      output.push(line);
      continue;
    }
    const key = match[1];
    if (Object.hasOwn(values, key)) {
      const existingValue = parseEnv(line)[key] ?? "";
      if (key.endsWith("_API_KEY") && hasSecret({ existing: existingValue }, "existing") && !hasSecret(values, key)) {
        output.push(line);
        seen.add(key);
        continue;
      }
      output.push(`${key}=${values[key]}\n`);
      seen.add(key);
    } else {
      output.push(line);
    }
  }

  const missingKeys = Object.keys(DEFAULTS).filter((key) => !seen.has(key) && Object.hasOwn(values, key));
  if (missingKeys.length > 0) {
    if (output.length > 0 && !output[output.length - 1].endsWith("\n")) output[output.length - 1] += "\n";
    output.push("\n# Installer-managed values\n");
    for (const key of missingKeys) output.push(`${key}=${values[key]}\n`);
  }

  return output.join("");
}

export function loadEnv(root = process.cwd()) {
  const envPath = path.join(root, ".env");
  const examplePath = path.join(root, ".env.example");
  if (!fs.existsSync(envPath)) {
    if (!fs.existsSync(examplePath)) throw new Error("Missing .env and .env.example; cannot create configuration.");
    fs.copyFileSync(examplePath, envPath);
  }
  return { envPath, values: { ...DEFAULTS, ...parseEnv(fs.readFileSync(envPath, "utf8")) } };
}

export function saveEnv(envPath, values) {
  const existing = fs.existsSync(envPath) ? fs.readFileSync(envPath, "utf8") : "";
  fs.writeFileSync(envPath, writeEnvText(existing, values), "utf8");
}

export function generateSecret(bytes = 32) {
  return crypto.randomBytes(bytes).toString("base64url");
}

export function mask(value) {
  if (!value) return "<empty>";
  if (value.length <= 10) return `${value.slice(0, 2)}...${value.slice(-2)}`;
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}
