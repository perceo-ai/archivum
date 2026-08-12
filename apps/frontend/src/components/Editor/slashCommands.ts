export type SlashCommandId =
  | 'paragraph'
  | 'heading-1'
  | 'heading-2'
  | 'heading-3'
  | 'bullet'
  | 'numbered'
  | 'todo'
  | 'quote'
  | 'code'
  | 'divider';

export type SlashCommand = {
  id: SlashCommandId;
  label: string;
  detail: string;
  aliases: string[];
};

export const SLASH_COMMANDS: SlashCommand[] = [
  { id: 'paragraph', label: 'Text', detail: 'Plain paragraph', aliases: ['text', 'p'] },
  { id: 'heading-1', label: 'Heading 1', detail: 'Large section heading', aliases: ['h1', 'heading', 'title'] },
  { id: 'heading-2', label: 'Heading 2', detail: 'Medium section heading', aliases: ['h2', 'subheading'] },
  { id: 'heading-3', label: 'Heading 3', detail: 'Small section heading', aliases: ['h3'] },
  { id: 'bullet', label: 'Bulleted list', detail: 'Simple list item', aliases: ['bullet', 'ul', 'list'] },
  { id: 'numbered', label: 'Numbered list', detail: 'Ordered list item', aliases: ['number', 'ol', 'ordered'] },
  { id: 'todo', label: 'To-do', detail: 'Checkbox task', aliases: ['todo', 'task', 'check'] },
  { id: 'quote', label: 'Quote', detail: 'Call out a quote', aliases: ['quote', 'blockquote'] },
  { id: 'code', label: 'Code block', detail: 'Fenced code block', aliases: ['code', 'pre'] },
  { id: 'divider', label: 'Divider', detail: 'Horizontal rule', aliases: ['divider', 'hr', 'rule'] },
];

function slashBody(lineText: string) {
  return lineText.replace(/^\s*\/[^\s]*\s?/, '');
}

export function applySlashCommandToLine(lineText: string, command: SlashCommandId) {
  const body = slashBody(lineText);

  switch (command) {
    case 'paragraph':
      return body;
    case 'heading-1':
      return `# ${body}`.trimEnd();
    case 'heading-2':
      return `## ${body}`.trimEnd();
    case 'heading-3':
      return `### ${body}`.trimEnd();
    case 'bullet':
      return `- ${body}`.trimEnd();
    case 'numbered':
      return `1. ${body}`.trimEnd();
    case 'todo':
      return `- [ ] ${body}`.trimEnd();
    case 'quote':
      return `> ${body}`.trimEnd();
    case 'code':
      return body ? `\`\`\`\n${body}\n\`\`\`` : '```';
    case 'divider':
      return '---';
  }
}

export function matchSlashCommand(command: SlashCommand, rawQuery: string) {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return 1;
  const values = [command.label, command.detail, ...command.aliases].map((value) => value.toLowerCase());

  for (const value of values) {
    if (value === query) return 1000;
    if (value.startsWith(query)) return 800 - value.length;
    if (value.includes(query)) return 500 - value.indexOf(query);
  }

  return 0;
}

type MarkdownBlockRange = {
  start: number;
  end: number;
};

function isIndentedContinuation(line: string) {
  return /^\s{2,}\S/.test(line);
}

function isListLine(line: string) {
  return /^\s*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)/.test(line);
}

function isQuoteLine(line: string) {
  return /^\s*>/.test(line);
}

function isFenceLine(line: string) {
  return /^\s*(`{3,}|~{3,})/.test(line);
}

export function getMarkdownBlockRange(text: string, lineNumber: number): MarkdownBlockRange {
  const lines = text.split('\n');
  const index = lineNumber - 1;
  if (index < 0 || index >= lines.length) return { start: index, end: index };

  const line = lines[index] ?? '';
  if (isFenceLine(line)) {
    for (let cursor = index + 1; cursor < lines.length; cursor += 1) {
      if (isFenceLine(lines[cursor] ?? '')) return { start: index, end: cursor };
    }
    return { start: index, end: lines.length - 1 };
  }

  if (isListLine(line)) {
    let end = index;
    for (let cursor = index + 1; cursor < lines.length; cursor += 1) {
      const next = lines[cursor] ?? '';
      if (!next.trim() || isIndentedContinuation(next)) {
        end = cursor;
        continue;
      }
      break;
    }
    return { start: index, end };
  }

  if (isQuoteLine(line)) {
    let end = index;
    for (let cursor = index + 1; cursor < lines.length; cursor += 1) {
      if (isQuoteLine(lines[cursor] ?? '')) {
        end = cursor;
        continue;
      }
      break;
    }
    return { start: index, end };
  }

  return { start: index, end: index };
}

export function moveMarkdownBlockInText(text: string, fromLine: number, toLine: number) {
  const lines = text.split('\n');
  const fromRange = getMarkdownBlockRange(text, fromLine);
  const toRange = getMarkdownBlockRange(text, toLine);
  const fromIndex = fromRange.start;
  const toIndex = toRange.start;
  if (fromIndex < 0 || fromIndex >= lines.length || toIndex < 0 || toIndex >= lines.length) return text;
  if (toIndex >= fromRange.start && toIndex <= fromRange.end) return text;

  const movedLines = lines.splice(fromRange.start, fromRange.end - fromRange.start + 1);
  const insertIndex = fromRange.start < toIndex ? toIndex - movedLines.length : toIndex;
  lines.splice(insertIndex, 0, ...movedLines);
  return lines.join('\n');
}

export function moveMarkdownBlockByOffset(text: string, lineNumber: number, offset: -1 | 1) {
  const lines = text.split('\n');
  const range = getMarkdownBlockRange(text, lineNumber);
  if (range.start < 0 || range.end >= lines.length) return { text, lineNumber };

  if (offset < 0) {
    if (range.start === 0) return { text, lineNumber };
    const previousRange = getMarkdownBlockRange(text, range.start);
    const nextText = moveMarkdownBlockInText(text, lineNumber, previousRange.start + 1);
    return { text: nextText, lineNumber: previousRange.start + 1 };
  }

  if (range.end >= lines.length - 1) return { text, lineNumber };
  const nextRange = getMarkdownBlockRange(text, range.end + 2);
  const movedLines = lines.splice(range.start, range.end - range.start + 1);
  const insertIndex = nextRange.end + 1 - movedLines.length;
  lines.splice(insertIndex, 0, ...movedLines);
  return { text: lines.join('\n'), lineNumber: insertIndex + 1 };
}

export function moveLineInText(text: string, fromLine: number, toLine: number) {
  return moveMarkdownBlockInText(text, fromLine, toLine);
}

export function getEnterInsertionForLine(lineText: string): { replaceLine: string | null; insertion: string } | null {
  const task = /^(\s*[-*+]\s+\[[ xX]\]\s*)(.*)$/.exec(lineText);
  if (task) {
    return task[2].trim() ? { replaceLine: null, insertion: `\n${task[1].replace(/\[[ xX]\]/, '[ ]')}` } : { replaceLine: '', insertion: '\n' };
  }

  const unordered = /^(\s*[-*+]\s+)(.*)$/.exec(lineText);
  if (unordered) {
    return unordered[2].trim() ? { replaceLine: null, insertion: `\n${unordered[1]}` } : { replaceLine: '', insertion: '\n' };
  }

  const ordered = /^(\s*)(\d+)([.)]\s+)(.*)$/.exec(lineText);
  if (ordered) {
    return ordered[4].trim()
      ? { replaceLine: null, insertion: `\n${ordered[1]}${Number(ordered[2]) + 1}${ordered[3]}` }
      : { replaceLine: '', insertion: '\n' };
  }

  const quote = /^(\s*>\s?)(.*)$/.exec(lineText);
  if (quote) {
    return quote[2].trim() ? { replaceLine: null, insertion: `\n${quote[1]}` } : { replaceLine: '', insertion: '\n' };
  }

  return null;
}

export function toggleTaskLine(lineText: string) {
  return lineText.replace(/^(\s*[-*+]\s+\[)([ xX])(\]\s*)/, (_match, start: string, checked: string, end: string) => {
    return `${start}${checked.toLowerCase() === 'x' ? ' ' : 'x'}${end}`;
  });
}
