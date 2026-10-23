import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  DEFAULTS,
  ensureInternalGraphToken,
  envNeedsConfiguration,
  parseEnv,
  secretDefault,
  writeEnvText,
} from "../src/env.js";

function completeEnvValues() {
  return {
    ...DEFAULTS,
    ANTHROPIC_API_KEY: "sk-ant-existing",
    JWT_SECRET: "jwt-secret-existing",
    OWNER_PASSWORD: "owner-password-existing",
    MCP_API_KEY: "mcp-key-existing",
    INTERNAL_GRAPH_TOKEN: "internal-graph-token-existing",
    LLM_EXTRACTION_PROVIDER: "anthropic",
    LLM_SYNTHESIS_PROVIDER: "anthropic",
    LLM_MODEL: "claude-haiku-4-5-20251001",
    LLM_SYNTHESIS_MODEL: "claude-sonnet-4-6",
    EMBED_PROVIDER: "local",
    EMBED_MODEL: "BAAI/bge-small-en-v1.5",
    EMBED_DIM: "0",
  };
}

test("complete env does not need configuration", () => {
  assert.equal(envNeedsConfiguration(completeEnvValues()), false);
});

test("missing internal graph token needs configuration", () => {
  // compose refuses to start without it, so an env lacking it is not complete.
  const values = completeEnvValues();
  values.INTERNAL_GRAPH_TOKEN = "";

  assert.equal(envNeedsConfiguration(values), true);
});

test("missing selected provider api key needs configuration", () => {
  const values = completeEnvValues();
  values.ANTHROPIC_API_KEY = "";

  assert.equal(envNeedsConfiguration(values), true);
});

test("openrouter env with shell spacing does not need configuration", () => {
  const parsed = parseEnv(`
    export OPENROUTER_API_KEY = sk-or-existing
    OPENROUTER_BASE_URL = https://openrouter.ai/api/v1
    JWT_SECRET = jwt-secret-existing
    OWNER_PASSWORD = owner-password-existing
    MCP_API_KEY = mcp-key-existing
    INTERNAL_GRAPH_TOKEN = internal-graph-token-existing
    LLM_EXTRACTION_PROVIDER = openrouter
    LLM_SYNTHESIS_PROVIDER = openrouter
    LLM_MODEL = openrouter/auto
    LLM_SYNTHESIS_MODEL = openrouter/auto
    EMBED_PROVIDER = local
    EMBED_MODEL = BAAI/bge-small-en-v1.5
    EMBED_DIM = 0
  `);

  assert.equal(envNeedsConfiguration({ ...DEFAULTS, ...parsed }), false);
});

test("writeEnvText preserves an existing api key when incoming value is blank", () => {
  const text = writeEnvText("OPENROUTER_API_KEY=sk-or-existing\n", {
    OPENROUTER_API_KEY: "",
  });

  assert.match(text, /OPENROUTER_API_KEY=sk-or-existing\n/);
  assert.doesNotMatch(text, /OPENROUTER_API_KEY=\n/);
});

test("writeEnvText preserves exported api key without appending a blank duplicate", () => {
  const text = writeEnvText("export OPENROUTER_API_KEY=sk-or-existing\n", {
    OPENROUTER_API_KEY: "",
  });

  assert.match(text, /export OPENROUTER_API_KEY=sk-or-existing\n/);
  assert.doesNotMatch(text, /OPENROUTER_API_KEY=\n/);
});

test("secretDefault rejects placeholder secrets", () => {
  assert.equal(secretDefault("sk-ant-..."), "");
  assert.equal(secretDefault("sk-ant-existing"), "sk-ant-existing");
});

function installWithEnv(text) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "archivum-env-"));
  fs.writeFileSync(path.join(root, ".env"), text, "utf8");
  return root;
}

function tokenIn(root) {
  return parseEnv(fs.readFileSync(path.join(root, ".env"), "utf8")).INTERNAL_GRAPH_TOKEN;
}

test("update gives an install that predates the token one, once, and touches nothing else", () => {
  const before = "# mine\nJWT_SECRET=jwt-existing\nMCP_API_KEY=mcp-existing";
  const root = installWithEnv(before);

  assert.equal(ensureInternalGraphToken(root), true);
  const token = tokenIn(root);
  assert.equal(secretDefault(token), token);
  assert.ok(token.length >= 40);
  assert.equal(fs.readFileSync(path.join(root, ".env"), "utf8"), `${before}\n\n# Installer-managed values\nINTERNAL_GRAPH_TOKEN=${token}\n`);

  assert.equal(ensureInternalGraphToken(root), false);
  assert.equal(tokenIn(root), token);
});

test("update replaces the .env.example placeholder token in place", () => {
  const root = installWithEnv("INTERNAL_GRAPH_TOKEN=change-me-generate-with-openssl-rand-hex-32\nJWT_SECRET=jwt-existing\n");

  assert.equal(ensureInternalGraphToken(root), true);
  const text = fs.readFileSync(path.join(root, ".env"), "utf8");
  assert.doesNotMatch(text, /change-me/);
  assert.equal(text.match(/INTERNAL_GRAPH_TOKEN=/g).length, 1);
  assert.match(text, /JWT_SECRET=jwt-existing\n/);
});

test("update keeps a token that is already set", () => {
  const root = installWithEnv("INTERNAL_GRAPH_TOKEN=already-set-token\n");

  assert.equal(ensureInternalGraphToken(root), false);
  assert.equal(tokenIn(root), "already-set-token");
});
