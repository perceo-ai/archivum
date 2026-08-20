/**
 * Minimal markdown for shared documents.
 *
 * Emits semantic class names from `shell.css` rather than the inline colours
 * the old share viewer hard-coded, so a shared page follows the reader's theme
 * instead of pinning itself to one palette. Output is always sanitised by the
 * caller before it reaches the DOM.
 *
 * Structure is detected on the raw source and escaping happens at the leaves.
 * Escaping first would turn every `>` into `&gt;` and quietly break blockquote
 * detection.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function renderSharedMarkdown(source: string): string {
  return source
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map(renderBlock)
    .join('');
}

function renderBlock(block: string): string {
  const heading = block.match(/^(#{1,3})\s+(.*)$/);
  if (heading) {
    const level = heading[1].length + 1; // h1 belongs to the document title
    return `<h${level}>${inline(heading[2])}</h${level}>`;
  }

  if (block.startsWith('```')) {
    const body = block.replace(/^```[\w-]*\n?/, '').replace(/```$/, '');
    return `<pre><code>${escapeHtml(body)}</code></pre>`;
  }

  if (/^>\s?/.test(block)) {
    return `<blockquote class="quote">${inline(block.replace(/^>\s?/gm, ''))}</blockquote>`;
  }

  if (/^[-*]\s/.test(block)) {
    return `<ul>${listItems(block, /^[-*]\s+/)}</ul>`;
  }

  if (/^\d+\.\s/.test(block)) {
    return `<ol>${listItems(block, /^\d+\.\s+/)}</ol>`;
  }

  if (/^---+$/.test(block)) return '<hr class="divider" />';

  return `<p>${inline(block)}</p>`;
}

function listItems(block: string, marker: RegExp): string {
  return block
    .split('\n')
    .map((line) => `<li>${inline(line.replace(marker, ''))}</li>`)
    .join('');
}

function inline(text: string): string {
  return (
    escapeHtml(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Wikilinks point inside a vault the reader cannot open, so they render
      // as plain text rather than dead links.
      .replace(/\[\[([^\]]+)\]\]/g, '<span class="shared-wl">$1</span>')
      .replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
      )
      .replace(/\n/g, '<br />')
  );
}
