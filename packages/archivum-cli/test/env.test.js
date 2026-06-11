import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULTS,
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
