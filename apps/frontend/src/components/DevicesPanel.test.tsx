import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { DevicesPanel } from './DevicesPanel';

const device = {
  id: 'dev_abc',
  name: 'work laptop / claude',
  created_at: '2026-08-26T10:00:00Z',
  last_seen_at: '2026-08-26T11:00:00Z',
  revoked_at: null,
};

describe('DevicesPanel', () => {
  it('lists linked devices with when they were last seen', () => {
    const html = renderToString(
      <DevicesPanel devices={[device]} pairing={null} legacyKeyConfigured={false} onLink={() => {}} onRevoke={() => {}} />,
    );

    expect(html).toContain('work laptop / claude');
    expect(html).toContain('dev_abc');
  });

  it('shows a revoked device as revoked rather than hiding it', () => {
    const html = renderToString(
      <DevicesPanel
        devices={[{ ...device, revoked_at: '2026-08-26T12:00:00Z' }]}
        pairing={null}
        legacyKeyConfigured={false}
        onLink={() => {}}
        onRevoke={() => {}}
      />,
    );

    expect(html).toContain('Revoked');
    expect(html).toContain('work laptop / claude');
  });

  it('tells the new machine to install from this vault, not to clone a repo', () => {
    const html = renderToString(
      <DevicesPanel
        devices={[]}
        pairing={{ token: 'arch1_xyz', expires_at: '2026-08-26T10:15:00Z' }}
        legacyKeyConfigured={false}
        onLink={() => {}}
        onRevoke={() => {}}
      />,
    );

    // The vault serves its own installer, so linking is one line and the CLI
    // version can never drift from the server it talks to.
    expect(html).toContain('/install | sh');
    expect(html).toContain('archivum connect arch1_xyz');
    // A clone was the old instruction and is the thing this replaced.
    expect(html).not.toContain('git clone');
    // npx must never be the line run against a live token: the package is not
    // on public npm, so that name resolves to somebody else's package.
    expect(html).not.toContain('npx archivum@latest connect arch1_xyz');
    expect(html).toContain('15 minutes');
  });

  it('offers a copy button for the pairing token', () => {
    const html = renderToString(
      <DevicesPanel
        devices={[]}
        pairing={{ token: 'arch1_xyz', expires_at: '2026-08-26T10:15:00Z' }}
        legacyKeyConfigured={false}
        onLink={() => {}}
        onRevoke={() => {}}
        onCopyToken={() => {}}
      />,
    );

    expect(html).toContain('Copy token');
  });

  it('reports a copied token back to the user', () => {
    const html = renderToString(
      <DevicesPanel
        devices={[]}
        pairing={{ token: 'arch1_xyz', expires_at: '2026-08-26T10:15:00Z' }}
        legacyKeyConfigured={false}
        tokenCopied
        onLink={() => {}}
        onRevoke={() => {}}
        onCopyToken={() => {}}
      />,
    );

    expect(html).toContain('Copied token');
  });

  it('offers a way to dismiss a spent pairing token', () => {
    const html = renderToString(
      <DevicesPanel
        devices={[]}
        pairing={{ token: 'arch1_xyz', expires_at: '2026-08-26T10:15:00Z' }}
        legacyKeyConfigured={false}
        onLink={() => {}}
        onRevoke={() => {}}
        onDismissPairing={() => {}}
      />,
    );

    expect(html).toContain('refresh devices');
  });

  it('names the legacy shared key and states how it is actually retired', () => {
    const html = renderToString(
      <DevicesPanel devices={[]} pairing={null} legacyKeyConfigured onLink={() => {}} onRevoke={() => {}} />,
    );

    expect(html).toContain('legacy shared key');
    expect(html).toContain('every client');
    // The shared key lives in .env, not in the device table, so the row must
    // say what retiring it takes rather than implying a revoke button exists.
    expect(html).toContain('MCP_API_KEY');
    expect(html).toContain('restarting');
  });

  it('says nothing about a legacy key when none is configured', () => {
    const html = renderToString(
      <DevicesPanel devices={[]} pairing={null} legacyKeyConfigured={false} onLink={() => {}} onRevoke={() => {}} />,
    );

    expect(html).not.toContain('legacy shared key');
  });
});
