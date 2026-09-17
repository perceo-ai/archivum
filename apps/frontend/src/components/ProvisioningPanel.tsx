import { useState } from 'react';

import type { IssuedProvisioningToken, ProvisioningToken } from '../api';
import { installOrigin } from './DevicesPanel';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';

type ProvisioningPanelProps = {
  tokens: ProvisioningToken[];
  issued: IssuedProvisioningToken | null;
  onIssue: () => void;
  onRevoke: (tokenId: string, revokeDevices: boolean) => void;
  onDismiss: () => void;
};

/** The line an agent runs on a machine nobody is watching.
 *
 * One command, and the token travels in the environment rather than as an
 * argument so it does not land in shell history.
 */
export function autoSetupCommand(token: string, origin = installOrigin()) {
  return [
    `export ARCHIVUM_PROVISION_TOKEN=${token}`,
    `curl -fsSL ${origin}/install | sh`,
  ].join('\n');
}

function formatDate(iso: string | null) {
  if (!iso) return 'Never';
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function ProvisioningPanel({
  tokens,
  issued,
  onIssue,
  onRevoke,
  onDismiss,
}: ProvisioningPanelProps) {
  const [copied, setCopied] = useState(false);
  const live = tokens.filter((token) => !token.revoked_at);

  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">Let agents link themselves</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          A reusable token any machine can redeem for its own device key, with no
          copy-paste. It mints keys and reads nothing, so it is safe to keep in a
          shell profile or secret manager — but anything that can read it can add
          devices, up to its limit.
        </p>
      </div>

      <Button type="button" variant="outline" size="sm" onClick={onIssue}>
        Create a provisioning token
      </Button>

      {issued && (
        <div className="soft-border rounded-[8px] border bg-white/[0.03] p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                Shown once
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Run this on any machine you want linked. It installs the CLI from
                this vault and links in one step.
              </p>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
              Done
            </Button>
          </div>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all rounded-[5px] bg-black/30 p-2 font-mono text-[11px] leading-5 text-muted-foreground">
            {autoSetupCommand(issued.token)}
          </pre>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => copy(autoSetupCommand(issued.token))}
          >
            {copied ? 'Copied' : 'Copy setup command'}
          </Button>
        </div>
      )}

      {live.length > 0 && (
        <ul className="space-y-2">
          {live.map((token) => (
            <li
              key={token.id}
              className="soft-border flex items-center justify-between gap-3 rounded-[8px] border bg-white/[0.02] px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-xs font-medium">{token.name || 'Unnamed token'}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  Up to {token.device_cap} devices · last used {formatDate(token.last_used_at)}
                  {token.expires_at ? ` · expires ${formatDate(token.expires_at)}` : ''}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {!token.last_used_at && <Badge>Unused</Badge>}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onRevoke(token.id, false)}
                >
                  Revoke
                </Button>
                {/* Separate action because the answer to a leak is different
                    from the answer to routine rotation, and a single button
                    would have to guess which one this is. */}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onRevoke(token.id, true)}
                >
                  Revoke + devices
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type WebConnectorPanelProps = {
  mcpUrl: string;
  deviceKey: string | null;
  onMintKey: () => void;
  onDismiss: () => void;
};

/** claude.ai and ChatGPT cannot run an installer, so they get values to paste. */
export function WebConnectorPanel({
  mcpUrl,
  deviceKey,
  onMintKey,
  onDismiss,
}: WebConnectorPanelProps) {
  const [copied, setCopied] = useState<string | null>(null);

  const copy = (label: string, text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(label);
    window.setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">claude.ai and ChatGPT</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Browser assistants are configured by pasting a URL and a header. This
          needs the vault reachable over public HTTPS — a connector cannot reach
          an address on your own network.
        </p>
      </div>

      <div className="soft-border rounded-[8px] border bg-white/[0.03] p-3">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">URL</p>
        <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{mcpUrl}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-2"
          onClick={() => copy('url', mcpUrl)}
        >
          {copied === 'url' ? 'Copied' : 'Copy URL'}
        </Button>
      </div>

      {deviceKey ? (
        <div className="soft-border rounded-[8px] border bg-white/[0.03] p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Authorization header · shown once
            </p>
            <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
              Done
            </Button>
          </div>
          <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
            Bearer {deviceKey}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => copy('key', `Bearer ${deviceKey}`)}
          >
            {copied === 'key' ? 'Copied' : 'Copy header'}
          </Button>
        </div>
      ) : (
        <Button type="button" variant="outline" size="sm" onClick={onMintKey}>
          Mint a key for a web client
        </Button>
      )}
    </div>
  );
}
