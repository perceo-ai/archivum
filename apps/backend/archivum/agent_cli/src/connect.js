import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";

import { parseOptions, writeFileAtomic } from "./util.js";
import { pullSkills } from "./skills.js";
import {
  BUILTIN_CLIENTS,
  CLIENT_WRITERS,
  detectClients,
  detectFromManifest,
  streamableHttpUrl,
  writeClientConfig,
} from "./clients.js";

const STATE_DIR = ".archivum";
const STATE_FILE = "connection.json";

export function decodePairingToken(token) {
  if (typeof token !== "string" || !token.startsWith("arch1_")) {
    throw new Error("That is not an Archivum pairing token. Issue one from Settings.");
  }
  let payload;
  try {
    payload = JSON.parse(Buffer.from(token.slice("arch1_".length), "base64url").toString());
  } catch {
    throw new Error("Malformed pairing token.");
  }
  if (!payload.u || !payload.s) throw new Error("Malformed pairing token.");
  return { baseUrl: payload.u, secret: payload.s };
}

export const PROVISION_PREFIX = "arch1p_";
export const PROVISION_ENV_VAR = "ARCHIVUM_PROVISION_TOKEN";

export function decodeProvisioningToken(token) {
  if (typeof token !== "string" || !token.startsWith(PROVISION_PREFIX)) {
    throw new Error("That is not an Archivum provisioning token. Issue one from Settings.");
  }
  let payload;
  try {
    payload = JSON.parse(Buffer.from(token.slice(PROVISION_PREFIX.length), "base64url").toString());
  } catch {
    throw new Error("Malformed provisioning token.");
  }
  if (!payload.u || !payload.s) throw new Error("Malformed provisioning token.");
  return { baseUrl: payload.u, secret: payload.s };
}

/** A stable id for this machine, so re-running setup replaces its key.
 *
 * Persisted rather than derived from hostname alone: hostnames change, and two
 * machines behind the same DHCP name would otherwise take turns revoking each
 * other. The value is meaningless to the server, which only matches it.
 */
export function machineFingerprint(home) {
  const file = path.join(home, STATE_DIR, "machine-id");
  if (fs.existsSync(file)) return fs.readFileSync(file, "utf8").trim();
  const id = randomUUID();
  writeFileAtomic(file, `${id}\n`);
  return id;
}

export async function provision({
  baseUrl,
  secret,
  deviceName,
  fingerprint,
  fetchImpl = fetch,
}) {
  const response = await fetchImpl(`${baseUrl}/api/mcp/pairing/provision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret, device_name: deviceName, fingerprint }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.detail?.detail ?? `Provisioning failed (HTTP ${response.status}).`);
  }
  return response.json();
}

/** What the server knows about MCP clients, or null when it cannot say.
 *
 * Null rather than throwing: an older server has no such route, and a machine
 * that can mint a key but not fetch a manifest should still link the clients
 * this CLI has always known about.
 */
export async function fetchClientRegistry({ baseUrl, key, fetchImpl = fetch }) {
  const response = await fetchImpl(`${baseUrl}/api/mcp/clients`, {
    headers: { Authorization: `Bearer ${key}` },
  }).catch(() => null);
  if (!response?.ok) return null;
  const body = await response.json().catch(() => null);
  return Array.isArray(body?.clients) ? body : null;
}

export async function redeem({ baseUrl, secret, deviceName, fetchImpl = fetch }) {
  const response = await fetchImpl(`${baseUrl}/api/mcp/pairing/redeem`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret, device_name: deviceName }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.detail?.detail ?? `Pairing failed (HTTP ${response.status}).`);
  }
  return response.json();
}

// A 200 with a body missing what we're about to persist and hand to every
// client config is worse than a rejected request: the pairing token is
// already spent, and nothing downstream would notice until the agent tried
// to use a `Bearer undefined` header. Fail loudly before writing anything.
function assertRedeemResult(details) {
  const missing = ["device_id", "key", "sse_url"].filter((field) => !details?.[field]);
  if (missing.length > 0) {
    throw new Error(
      `Server response to pairing redeem was missing ${missing.join(", ")}. ` +
        "The pairing token has been spent; check the server before issuing another.",
    );
  }
}

// Checked before redeem spends the one-time token: an unsupported --client
// must not cost the user their only shot at that token.
function assertKnownClients(clients) {
  const unknown = clients.filter((client) => !CLIENT_WRITERS[client]);
  if (unknown.length > 0) {
    throw new Error(
      `Unknown client: ${unknown.join(", ")}. Supported: ${Object.keys(CLIENT_WRITERS).join(", ")}.`,
    );
  }
}

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "0.0.0.0"]);

function isLoopback(url) {
  try {
    return (
      LOOPBACK_HOSTS.has(new URL(url).hostname.toLowerCase().replace(/^\[|\]$/g, "")) ||
      new URL(url).hostname.toLowerCase().endsWith(".localhost")
    );
  } catch {
    return false;
  }
}

// `MCP_PUBLIC_URL` is optional on the server, and its fallback is
// `http://localhost:8001/sse` — which, written into this machine's client
// configs, names *this* machine's port 8001 rather than the vault. The server
// refuses to issue such a URL, but an older server, or one behind a proxy that
// rewrites it, still can; the failure otherwise surfaces days later as an
// unexplained MCP connection error with no thread back to pairing.
export function assertReachableSseUrl(baseUrl, sseUrl) {
  if (!isLoopback(sseUrl) || isLoopback(baseUrl)) return;
  throw new Error(
    `The server handed back an MCP endpoint of ${sseUrl}, but this vault is at ${baseUrl}. ` +
      "A loopback endpoint points at this machine, not at the vault, so no client config was written. " +
      "Set MCP_PUBLIC_URL on the server to the URL its MCP port is reachable at, restart the stack, and link again.",
  );
}

// The spec's step 4: do not report success for an endpoint nobody has spoken
// to. Every misconfiguration of the MCP URL — a proxy that fronts the API but
// not the MCP port, a wrong MCP_PUBLIC_URL path, a key the server does not
// know — otherwise produces a confident "Linked to ..." and a broken agent.
// A GET on the SSE endpoint with the device key is answered by the same
// bearer middleware every tool call goes through, so a 200 means this exact
// URL and this exact key work together.
export async function verifyConnection({ sseUrl, key, fetchImpl = fetch }) {
  let response;
  try {
    response = await fetchImpl(sseUrl, {
      headers: { Authorization: `Bearer ${key}`, Accept: "text/event-stream" },
      signal: AbortSignal.timeout(10_000),
    });
  } catch (error) {
    return {
      ok: false,
      reason: `could not reach ${sseUrl} (${error.message})`,
      hint: "Check that the MCP port is exposed through the same proxy as the API, and that MCP_PUBLIC_URL matches it.",
    };
  }
  // Headers are all we need; an SSE stream left open would hold the process.
  await Promise.resolve(response.body?.cancel?.()).catch(() => {});
  if (response.ok) return { ok: true };
  if (response.status === 401 || response.status === 403) {
    return {
      ok: false,
      reason: `${sseUrl} refused this device key (HTTP ${response.status})`,
      hint: "The key was minted seconds ago, so this usually means the URL belongs to a different server.",
    };
  }
  return {
    ok: false,
    reason: `${sseUrl} answered HTTP ${response.status}`,
    hint: "Check MCP_PUBLIC_URL on the server — it must include the /sse path and point at the MCP port.",
  };
}

// Codex-style clients POST `initialize` at the URL they are given, so the SSE
// endpoint answers them with 405 and the client never starts. A server that
// predates the streamable HTTP endpoint answers 404. Either way the config we
// just wrote for Codex is dead, and saying so now beats an unexplained
// "MCP client failed to start" later.
export async function verifyStreamableEndpoint({ streamableUrl, key, fetchImpl = fetch }) {
  const body = JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "archivum-connect", version: "1" },
    },
  });
  let response;
  try {
    response = await fetchImpl(streamableUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
      },
      body,
      signal: AbortSignal.timeout(10_000),
    });
  } catch (error) {
    return { ok: false, reason: `could not reach ${streamableUrl} (${error.message})` };
  }
  await Promise.resolve(response.body?.cancel?.()).catch(() => {});
  if (response.ok) return { ok: true };
  return { ok: false, reason: `${streamableUrl} answered HTTP ${response.status}` };
}

export async function installSkill({ home, skillUrl, fetchImpl = fetch }) {
  const response = await fetchImpl(skillUrl).catch(() => null);
  // A server without a bundled skill is a working server; linking must not fail
  // over it. The tools are still there, the agent just gets no guidance on
  // which to reach for first.
  if (!response?.ok) return null;
  const target = path.join(home, ".claude", "skills", "archivum-memory", "SKILL.md");
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, await response.text());
  return target;
}

function statePath(home) {
  return path.join(home, STATE_DIR, STATE_FILE);
}

export function saveState(home, state) {
  // Atomic, and 0600 every time: this file holds the raw device key, and a
  // re-link onto a file that already existed must not inherit its prior mode
  // or leave a truncated stub if the write dies halfway.
  return writeFileAtomic(statePath(home), `${JSON.stringify(state, null, 2)}\n`);
}

function readState(home) {
  const file = statePath(home);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : null;
}

export async function status(home, { fetchImpl = fetch } = {}) {
  const state = readState(home);
  if (!state) {
    console.log("Not linked. Run: archivum connect <pairing-token>");
    return;
  }
  console.log(`Linked to ${state.base_url} as ${state.device_id}`);
  console.log(`Clients configured: ${state.clients.join(", ") || "none"}`);
  // /devices/self authenticates with the device's own key (require_device on
  // the server), so a 200 here is a direct answer to "does this key still
  // work" rather than the owner-only /devices list, which 401s no matter
  // what the device key is.
  const response = await fetchImpl(`${state.base_url}/api/mcp/devices/self`, {
    headers: { Authorization: `Bearer ${state.key}` },
  }).catch(() => null);
  console.log(response?.ok ? "Key authenticates." : "Key no longer authenticates.");
}

export async function revoke(home, { fetchImpl = fetch } = {}) {
  const state = readState(home);
  if (!state) throw new Error("Nothing to revoke: this machine is not linked.");
  const response = await fetchImpl(`${state.base_url}/api/mcp/devices/self`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${state.key}` },
  }).catch(() => null);
  if (!response?.ok) {
    // An offline machine, or a key the server has already forgotten, must
    // never print "Revoked." while the local record — the only note of
    // which device_id to revoke from Settings — still exists to delete.
    throw new Error(
      `Could not confirm revocation with the server (device ${state.device_id}). ` +
        "Revoke it from Settings, or retry once the server is reachable. Local state was left in place.",
    );
  }
  fs.rmSync(statePath(home), { force: true });
  console.log("Revoked. Remove the archivum entry from your MCP clients if you want it gone from disk.");
}

// A re-link (a second machine's worth of clients, a fresh token after
// reinstalling an agent) used to overwrite the local record and leave the old
// device key live on the server forever, under a near-identical name, with
// nothing on this machine that remembers it. "Losing a laptop costs you one
// key" only holds if a machine has one key.
async function revokePreviousLink(previous, { fetchImpl }) {
  if (!previous?.key || !previous?.base_url) return null;
  const response = await fetchImpl(`${previous.base_url}/api/mcp/devices/self`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${previous.key}` },
  }).catch(() => null);
  return { deviceId: previous.device_id, revoked: Boolean(response?.ok) };
}

export async function connectCommand(
  args,
  { home = os.homedir(), fetchImpl = fetch, spawnImpl, env = process.env } = {},
) {
  const { flags, values, positionals } = parseOptions(args);

  if (flags.has("status")) return status(home, { fetchImpl });
  if (flags.has("revoke")) return revoke(home, { fetchImpl });

  // An agent setting up a machine has no one to paste a token for it, so the
  // environment is checked whenever an explicit one was not given. `--auto`
  // exists to say "only the environment", so a stale argument cannot silently
  // win over the variable a provisioning script just exported.
  const explicit = flags.has("auto") ? undefined : positionals[0];
  const token = explicit ?? env[PROVISION_ENV_VAR];
  if (!token) {
    throw new Error(
      "Usage: archivum connect <pairing-token> [--name NAME] [--client claude|cursor|codex]\n" +
        `   or: archivum connect --auto   (reads ${PROVISION_ENV_VAR} from the environment)`,
    );
  }

  const provisioning = token.startsWith(PROVISION_PREFIX);
  const { baseUrl, secret } = provisioning
    ? decodeProvisioningToken(token)
    : decodePairingToken(token);

  const requested = values.get("client");
  // Detection against the built-in list only decides the device *name* here;
  // the real client list is resolved from the server's manifest once there is
  // a key to fetch it with.
  const preDetected = requested ? [].concat(requested) : detectClients(home);
  if (!provisioning) {
    if (preDetected.length === 0) {
      throw new Error("No supported MCP client found. Install Claude Code, Cursor, or Codex, or pass --client.");
    }
    assertKnownClients(preDetected);
  }

  const deviceName =
    values.get("name") ?? `${os.hostname()}${preDetected.length ? ` / ${preDetected.join("+")}` : ""}`;

  // Read before minting, revoked after the new key is safely on disk: if the
  // exchange fails, this machine keeps the key it already had.
  const previous = readState(home);
  const details = provisioning
    ? await provision({
        baseUrl,
        secret,
        deviceName,
        fingerprint: machineFingerprint(home),
        fetchImpl,
      })
    : await redeem({ baseUrl, secret, deviceName, fetchImpl });
  assertRedeemResult(details);
  assertReachableSseUrl(baseUrl, details.sse_url);

  // Saved before any writer runs or the skill is fetched: the key is live on
  // the server the instant the exchange returns, so a partial failure from
  // here on must still leave it recoverable rather than orphaned.
  saveState(home, {
    device_id: details.device_id,
    base_url: baseUrl,
    sse_url: details.sse_url,
    key: details.key,
    linked_at: new Date().toISOString(),
    clients: preDetected,
  });

  // The server's fingerprint match already replaced this machine's previous
  // key, so asking it to revoke one again would revoke the key just minted.
  const retired = provisioning ? null : await revokePreviousLink(previous, { fetchImpl });

  const registry = await fetchClientRegistry({ baseUrl, key: details.key, fetchImpl });
  const catalogue = registry?.clients ?? BUILTIN_CLIENTS;
  const urls = registry?.urls ?? {
    sse: details.sse_url,
    "streamable-http": details.mcp_url ?? streamableHttpUrl(details.sse_url),
  };

  const selected = requested
    ? catalogue.filter((client) => [].concat(requested).includes(client.id))
    : detectFromManifest(home, catalogue);

  if (requested) {
    const unknown = [].concat(requested).filter((id) => !catalogue.some((c) => c.id === id));
    if (unknown.length > 0) {
      throw new Error(
        `Unknown client: ${unknown.join(", ")}. This server knows: ${catalogue.map((c) => c.id).join(", ")}.`,
      );
    }
  }

  // Recorded now that the manifest is in hand: `archivum watch` reads these
  // rather than carrying its own idea of where each client writes sessions.
  const transcriptDirs = [
    ...new Set(selected.flatMap((client) => client.transcripts ?? [])),
  ];
  saveState(home, {
    device_id: details.device_id,
    base_url: baseUrl,
    sse_url: details.sse_url,
    key: details.key,
    linked_at: new Date().toISOString(),
    clients: selected.map((client) => client.id),
    transcript_dirs: transcriptDirs,
  });

  const written = [];
  const skipped = [];
  for (const client of selected) {
    // One client whose config file is unreadable must not cost the others
    // theirs: the key is already live, and a half-linked machine that says
    // which half failed is recoverable by hand.
    try {
      const target = writeClientConfig(client, { home, urls, key: details.key, spawnImpl });
      if (target) written.push(target);
      else skipped.push(`${client.label ?? client.id}: no writer for method "${client.method}"`);
    } catch (error) {
      skipped.push(`${client.label ?? client.id}: ${error.message}`);
    }
  }

  const skillPath = details.skill_url
    ? await installSkill({ home, skillUrl: details.skill_url, fetchImpl })
    : null;

  // The point of storing skills in the vault is that linking a machine is the
  // only step. A server that has none, or is too old to serve them, must not
  // turn a working link into a failure.
  let pulledSkills = 0;
  try {
    const { pulled } = await pullSkills({
      home,
      fetchImpl,
      log: () => {},
    });
    pulledSkills = pulled;
  } catch {
    pulledSkills = 0;
  }

  const verification = await verifyConnection({
    sseUrl: details.sse_url,
    key: details.key,
    fetchImpl,
  });

  console.log(`Linked to ${details.vault_name ?? baseUrl} as "${deviceName}".`);
  for (const file of written) console.log(`  configured ${file}`);
  for (const problem of skipped) console.log(`  skipped ${problem}`);
  if (selected.length === 0) {
    console.log("  no MCP client detected on this machine — configure one by hand with the values below");
  }
  if (skillPath) console.log(`  installed ${skillPath}`);
  if (pulledSkills > 0) {
    console.log(`  installed ${pulledSkills} skill${pulledSkills === 1 ? "" : "s"} from the vault`);
  }
  if (retired) {
    console.log(
      retired.revoked
        ? `  revoked the previous device key for this machine (${retired.deviceId})`
        : `  could not revoke the previous device key for this machine (${retired.deviceId}) — revoke it from Settings`,
    );
  }

  const streamableUrl = urls["streamable-http"] ?? streamableHttpUrl(details.sse_url);
  // Named rather than counted: several clients speak only streamable HTTP, and
  // "a client is broken" sends someone hunting through five configs.
  const streamableClients = selected
    .filter((client) => client.transport === "streamable-http")
    .map((client) => client.label ?? client.id);
  const streamableCheck = streamableClients.length
    ? await verifyStreamableEndpoint({ streamableUrl, key: details.key, fetchImpl })
    : null;

  if (verification.ok) {
    console.log(`  verified ${details.sse_url} answers this device key`);
  } else {
    // Loud, and not fatal: the key is real and on disk, so telling the user to
    // start over would cost them a token for a problem re-linking cannot fix.
    console.log(`\nCould not verify the MCP endpoint: ${verification.reason}.`);
    console.log(`  ${verification.hint}`);
    console.log("  The configs above were written and the device key is valid;");
    console.log("  re-check with: archivum connect --status");
  }
  if (streamableCheck && !streamableCheck.ok) {
    console.log(
      `\n${streamableClients.join(", ")} was configured for ${streamableUrl}, ` +
        `which did not answer: ${streamableCheck.reason}.`,
    );
    console.log("  Clients that speak only streamable HTTP cannot use the /sse endpoint.");
    console.log("  Update the server to a version that serves /mcp, then re-run this command.");
  }

  const web = registry?.web_clients ?? [];
  console.log(
    web.length
      ? `\nFor ${web.map((c) => c.label).join(" or ")}, add a custom connector:`
      : "\nFor claude.ai or ChatGPT, add a custom connector:",
  );
  console.log(`  URL:    ${streamableUrl}`);
  console.log(`  SSE:    ${details.sse_url} (clients that only speak the SSE transport)`);
  console.log(`  Header: Authorization: Bearer ${details.key}`);
  console.log("\nRestart your agent for the new server to appear.");
}
