import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { SelfNodeHeader } from './SelfNodeHeader';

describe('SelfNodeHeader', () => {
  it('shows the owner as the current graph center', () => {
    const html = renderToString(<SelfNodeHeader label="Me" activeScope="wiki:default" />);

    expect(html).toContain('Me');
    expect(html).toContain('Center');
  });
});
