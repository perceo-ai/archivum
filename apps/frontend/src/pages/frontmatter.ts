export type ParsedFrontmatter = {
  hasFrontmatter: boolean;
  body: string;
  lines: string[];
};

const FRONTMATTER_BOUNDARY_RE = /^---\s*$/;

export function parseFrontmatter(markdown: string): ParsedFrontmatter {
  const normalized = markdown.replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');
  if (!FRONTMATTER_BOUNDARY_RE.test(lines[0] ?? '')) {
    return { hasFrontmatter: false, body: markdown, lines: [] };
  }

  const endIndex = lines.findIndex((line, index) => index > 0 && FRONTMATTER_BOUNDARY_RE.test(line));
  if (endIndex < 0) {
    return { hasFrontmatter: false, body: markdown, lines: [] };
  }

  const body = lines.slice(endIndex + 1).join('\n').replace(/^\n/, '');
  return {
    hasFrontmatter: true,
    body,
    lines: lines.slice(1, endIndex),
  };
}

export function mergeFrontmatterProperties(
  originalMarkdown: string,
  body: string,
  title: string,
  tags: string[],
) {
  const parsed = parseFrontmatter(originalMarkdown);
  if (!parsed.hasFrontmatter) return body;

  const preserved = parsed.lines.filter((line) => !/^\s*(title|tags)\s*:/.test(line));
  const nextLines = [
    `title: ${formatYamlValue(title.trim() || 'Untitled')}`,
    `tags: [${tags.map(formatYamlValue).join(', ')}]`,
    ...preserved,
  ];

  return `---\n${nextLines.join('\n')}\n---\n\n${body.replace(/^\n+/, '')}`;
}

function formatYamlValue(value: string) {
  if (/^[a-zA-Z0-9_./ -]+$/.test(value) && value.trim() === value) return value;
  return JSON.stringify(value);
}
