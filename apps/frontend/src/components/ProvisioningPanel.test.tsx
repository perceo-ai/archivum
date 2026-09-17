import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import {
  ProvisioningPanel,
  WebConnectorPanel,
  autoSetupCommand,
} from './ProvisioningPanel';

// renderToString inserts <!-- --> between adjacent text nodes, which splits
// any interpolated string. Strip them so assertions read as what a person sees.
const text = (html: string) => html.replace(/<!-- -->/g, '');

const token = {
  id: 'prov_1',
  name: 'dotfiles',
  created_at: '2026-09-17T10:00:00Z',
  expires_at: null,
  device_cap: 25,
  last_used_at: null,
  revoked_at: null,
};

describe('autoSetupCommand', () => {
  it('passes the token through the environment, not as an argument', () => {
    const command = autoSetupCommand('arch1p_abc', 'https://vault.example.com');

    // An argument lands in shell history; an exported variable does not.
    expect(command).toContain('export ARCHIVUM_PROVISION_TOKEN=arch1p_abc');
    expect(command).toContain('curl -fsSL https://vault.example.com/install | sh');
    expect(command).not.toContain('connect arch1p_abc');
  });
});

describe('ProvisioningPanel', () => {
  it('says plainly what a provisioning token can and cannot do', () => {
    const html = renderToString(
      <ProvisioningPanel
        tokens={[]}
        issued={null}
        onIssue={() => {}}
        onRevoke={() => {}}
        onDismiss={() => {}}
      />,
    );

    // It lives in a shell profile, so the tradeoff belongs on screen rather
    // than in documentation nobody opens.
    expect(html).toContain('mints keys and reads nothing');
    expect(html).toContain('add devices');
  });

  it('shows the setup command once, when the token is issued', () => {
    const html = renderToString(
      <ProvisioningPanel
        tokens={[token]}
        issued={{ ...token, token: 'arch1p_xyz', env_var: 'ARCHIVUM_PROVISION_TOKEN' }}
        onIssue={() => {}}
        onRevoke={() => {}}
        onDismiss={() => {}}
      />,
    );

    expect(html).toContain('Shown once');
    expect(html).toContain('ARCHIVUM_PROVISION_TOKEN=arch1p_xyz');
  });

  it('lists a live token with its cap and whether it has ever been used', () => {
    const html = renderToString(
      <ProvisioningPanel
        tokens={[token]}
        issued={null}
        onIssue={() => {}}
        onRevoke={() => {}}
        onDismiss={() => {}}
      />,
    );

    expect(html).toContain('dotfiles');
    expect(text(html)).toContain('Up to 25 devices');
    // An unused token is the one that is safe to revoke without thinking.
    expect(html).toContain('Unused');
  });

  it('separates routine revocation from the answer to a leak', () => {
    const html = renderToString(
      <ProvisioningPanel
        tokens={[token]}
        issued={null}
        onIssue={() => {}}
        onRevoke={() => {}}
        onDismiss={() => {}}
      />,
    );

    // Rotating a secret should not log out every machine; a leak should.
    expect(html).toContain('Revoke</button>');
    expect(html).toContain('Revoke + devices');
  });

  it('hides tokens that are already revoked', () => {
    const html = renderToString(
      <ProvisioningPanel
        tokens={[{ ...token, revoked_at: '2026-09-17T11:00:00Z' }]}
        issued={null}
        onIssue={() => {}}
        onRevoke={() => {}}
        onDismiss={() => {}}
      />,
    );

    expect(html).not.toContain('dotfiles');
  });
});

describe('WebConnectorPanel', () => {
  it('offers the streamable URL browser connectors need', () => {
    const html = renderToString(
      <WebConnectorPanel
        mcpUrl="https://vault.example.com/mcp"
        deviceKey={null}
        onMintKey={() => {}}
        onDismiss={() => {}}
      />,
    );

    expect(html).toContain('https://vault.example.com/mcp');
    expect(html).toContain('claude.ai and ChatGPT');
  });

  it('warns that a browser connector cannot reach a private address', () => {
    const html = renderToString(
      <WebConnectorPanel
        mcpUrl="https://vault.example.com/mcp"
        deviceKey={null}
        onMintKey={() => {}}
        onDismiss={() => {}}
      />,
    );

    // Otherwise this is discovered as a connector that silently never works.
    expect(html).toContain('public HTTPS');
  });

  it('shows the header only after a key is minted, and says it is shown once', () => {
    const before = renderToString(
      <WebConnectorPanel
        mcpUrl="https://v/mcp"
        deviceKey={null}
        onMintKey={() => {}}
        onDismiss={() => {}}
      />,
    );
    const after = renderToString(
      <WebConnectorPanel
        mcpUrl="https://v/mcp"
        deviceKey="amk_secret"
        onMintKey={() => {}}
        onDismiss={() => {}}
      />,
    );

    expect(before).not.toContain('amk_secret');
    expect(text(after)).toContain('Bearer amk_secret');
    expect(after).toContain('shown once');
  });
});
