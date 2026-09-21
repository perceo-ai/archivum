import type { McpDevice, PairingToken } from '../api';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';

type DevicesPanelProps = {
  devices: McpDevice[];
  pairing: PairingToken | null;
  legacyKeyConfigured: boolean;
  tokenCopied?: boolean;
  onLink: () => void;
  onRevoke: (deviceId: string) => void;
  onCopyToken?: () => void;
  onDismissPairing?: () => void;
};

// This vault serves its own installer, which is why the command is one line
// and names no package registry. `npx archivum@latest` is still not an option:
// the CLI is published to GitHub Packages as @pranavkannepalli/archivum rather
// than public npm, so it would either fail after a registry round trip — inside
// a fifteen-minute window — or resolve to somebody else's `archivum` package,
// which the user would then hand a token that redeems to full vault access.
export function installOrigin() {
  // Same origin as the API the page is already talking to: the frontend
  // container proxies /api to the backend, and /install sits beside it.
  return typeof window === 'undefined' ? '' : window.location.origin;
}

// A pairing token is single-use and belongs on the `connect` line, not in the
// environment variable named for the reusable kind. Two lines, no clone.
function connectCommand(token: string, origin = installOrigin()) {
  return [`curl -fsSL ${origin}/install | sh`, `archivum connect ${token}`].join('\n');
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

export function DevicesPanel({
  devices,
  pairing,
  legacyKeyConfigured,
  tokenCopied = false,
  onLink,
  onRevoke,
  onCopyToken,
  onDismissPairing,
}: DevicesPanelProps) {
  return (
    <div className="space-y-3">
      <Button type="button" variant="outline" size="sm" onClick={onLink}>
        Link a device
      </Button>

      {pairing && (
        <div className="soft-border rounded-[8px] border bg-white/[0.03] p-3">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Run this on the new machine
          </p>
          <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground">
            {connectCommand(pairing.token)}
          </pre>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Needs Node 20+ and nothing else — no checkout and no package
            registry. The installer is served by this vault, so it always
            matches the server it links to.
          </p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            This token works once and expires in 15 minutes.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {onCopyToken && (
              <Button type="button" variant="outline" size="sm" onClick={onCopyToken}>
                {tokenCopied ? 'Copied token' : 'Copy token'}
              </Button>
            )}
            {onDismissPairing && (
              <Button type="button" variant="ghost" size="sm" onClick={onDismissPairing}>
                Done — refresh devices
              </Button>
            )}
          </div>
        </div>
      )}

      {legacyKeyConfigured && (
        <div className="subtle-divider flex items-center justify-between gap-3 border-b py-2">
          <div className="min-w-0">
            <p className="text-sm text-foreground">legacy shared key</p>
            <p className="text-xs leading-5 text-muted-foreground">
              Authenticates every client that holds it, so it cannot be revoked from here. Once every
              machine is linked individually, retire it by unsetting MCP_API_KEY in .env and restarting
              the stack.
            </p>
          </div>
          <Badge variant="secondary" className="shrink-0 text-xs">
            Shared
          </Badge>
        </div>
      )}

      {devices.length === 0 ? (
        <p className="text-sm text-muted-foreground">No devices linked yet.</p>
      ) : (
        <div className="space-y-2">
          {devices.map((device) => (
            <div
              key={device.id}
              className="subtle-divider flex items-center justify-between gap-3 border-b py-2 last:border-0"
            >
              <div className="min-w-0">
                <p className="truncate text-sm text-foreground">{device.name}</p>
                <p className="truncate font-mono text-xs text-muted-foreground">{device.id}</p>
                <p className="text-xs text-muted-foreground">
                  Linked {formatDate(device.created_at)} · Last seen {formatDate(device.last_seen_at)}
                </p>
              </div>
              {device.revoked_at ? (
                <Badge variant="destructive" className="shrink-0 text-xs">
                  Revoked
                </Badge>
              ) : (
                <Button type="button" variant="outline" size="sm" onClick={() => onRevoke(device.id)}>
                  Revoke
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
