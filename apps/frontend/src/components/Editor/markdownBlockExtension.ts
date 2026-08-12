import { RangeSetBuilder, type Extension } from '@codemirror/state';
import {
  Decoration,
  type DecorationSet,
  EditorView,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from '@codemirror/view';

type MarkdownBlockKind =
  | 'blank'
  | 'paragraph'
  | 'heading-1'
  | 'heading-2'
  | 'heading-3'
  | 'heading-4'
  | 'heading-5'
  | 'heading-6'
  | 'unordered-list'
  | 'ordered-list'
  | 'task-open'
  | 'task-done'
  | 'quote'
  | 'code-fence'
  | 'thematic-break';

type MarkdownMarker = {
  from: number;
  to: number;
  label: string;
};

export type MarkdownLineBlock = {
  kind: MarkdownBlockKind;
  marker?: MarkdownMarker;
};

const HEADING_RE = /^(#{1,6})\s+/;
const TASK_RE = /^(\s*)([-*+]\s+\[([ xX])\]\s+)/;
const UNORDERED_RE = /^(\s*)([-*+]\s+)/;
const ORDERED_RE = /^(\s*)(\d+[.)]\s+)/;
const QUOTE_RE = /^(\s*>+\s?)/;
const CODE_FENCE_RE = /^(\s*`{3,}|~{3,})/;
const THEMATIC_BREAK_RE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;

export function classifyMarkdownLine(text: string): MarkdownLineBlock {
  if (text.trim().length === 0) return { kind: 'blank' };

  const heading = HEADING_RE.exec(text);
  if (heading) {
    const level = Math.min(heading[1].length, 6);
    return {
      kind: `heading-${level}` as MarkdownBlockKind,
      marker: { from: 0, to: heading[0].length, label: '' },
    };
  }

  const task = TASK_RE.exec(text);
  if (task) {
    return {
      kind: task[3].toLowerCase() === 'x' ? 'task-done' : 'task-open',
      marker: {
        from: task[1].length,
        to: task[1].length + task[2].length,
        label: task[3].toLowerCase() === 'x' ? '☑' : '☐',
      },
    };
  }

  const unordered = UNORDERED_RE.exec(text);
  if (unordered) {
    return {
      kind: 'unordered-list',
      marker: {
        from: unordered[1].length,
        to: unordered[1].length + unordered[2].length,
        label: '•',
      },
    };
  }

  const ordered = ORDERED_RE.exec(text);
  if (ordered) {
    return {
      kind: 'ordered-list',
      marker: {
        from: ordered[1].length,
        to: ordered[1].length + ordered[2].length,
        label: ordered[2].trim(),
      },
    };
  }

  const quote = QUOTE_RE.exec(text);
  if (quote) {
    return {
      kind: 'quote',
      marker: { from: 0, to: quote[1].length, label: '' },
    };
  }

  const fence = CODE_FENCE_RE.exec(text);
  if (fence) {
    return {
      kind: 'code-fence',
      marker: { from: fence[1].search(/[`~]/), to: fence[1].length, label: 'code' },
    };
  }

  if (THEMATIC_BREAK_RE.test(text)) {
    return {
      kind: 'thematic-break',
      marker: { from: 0, to: text.length, label: '' },
    };
  }

  return { kind: 'paragraph' };
}

class MarkdownMarkerWidget extends WidgetType {
  constructor(
    readonly label: string,
    readonly kind: MarkdownBlockKind,
  ) {
    super();
  }

  eq(other: MarkdownMarkerWidget) {
    return this.label === other.label && this.kind === other.kind;
  }

  toDOM() {
    const span = document.createElement('span');
    span.className = `cm-markdown-marker cm-markdown-marker-${this.kind}`;
    span.textContent = this.label;
    return span;
  }

  ignoreEvent() {
    return true;
  }
}

function selectedLines(view: EditorView) {
  const lines = new Set<number>();
  for (const range of view.state.selection.ranges) {
    lines.add(view.state.doc.lineAt(range.from).number);
    lines.add(view.state.doc.lineAt(range.to).number);
  }
  return lines;
}

function buildBlockDecorations(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  const activeLines = selectedLines(view);

  for (const { from, to } of view.visibleRanges) {
    let position = from;
    while (position <= to) {
      const line = view.state.doc.lineAt(position);
      const block = classifyMarkdownLine(line.text);

      builder.add(
        line.from,
        line.from,
        Decoration.line({
          class: `cm-markdown-block cm-markdown-${block.kind}`,
        }),
      );

      if (block.marker && !activeLines.has(line.number)) {
        builder.add(
          line.from + block.marker.from,
          line.from + block.marker.to,
          Decoration.replace({
            widget: new MarkdownMarkerWidget(block.marker.label, block.kind),
            inclusive: false,
          }),
        );
      }

      if (line.to >= to) break;
      position = line.to + 1;
    }
  }

  return builder.finish();
}

const markdownBlockPlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = buildBlockDecorations(view);
    }

    update(update: ViewUpdate) {
      if (update.docChanged || update.viewportChanged || update.selectionSet) {
        this.decorations = buildBlockDecorations(update.view);
      }
    }
  },
  {
    decorations: (plugin) => plugin.decorations,
  },
);

export function markdownBlockExtension(): Extension {
  return [
    markdownBlockPlugin,
    EditorView.theme({
      '.cm-content': {
        fontFamily: "'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      },
      '.cm-line.cm-markdown-block': {
        position: 'relative',
        padding: '3px 0 3px 30px',
        borderRadius: '5px',
        color: '#e7e7e7',
      },
      '.cm-line.cm-markdown-block:hover': {
        backgroundColor: 'rgba(255, 255, 255, 0.025)',
      },
      '.cm-line.cm-activeLine': {
        backgroundColor: 'rgba(255, 255, 255, 0.045)',
      },
      '.cm-markdown-heading-1': {
        marginTop: '20px',
        marginBottom: '6px',
        fontSize: '30px',
        lineHeight: '1.18',
        fontWeight: '700',
        color: '#ffffff',
      },
      '.cm-markdown-heading-2': {
        marginTop: '18px',
        marginBottom: '5px',
        fontSize: '24px',
        lineHeight: '1.22',
        fontWeight: '700',
        color: '#ffffff',
      },
      '.cm-markdown-heading-3': {
        marginTop: '14px',
        marginBottom: '4px',
        fontSize: '19px',
        lineHeight: '1.3',
        fontWeight: '650',
        color: '#f4f4f5',
      },
      '.cm-markdown-heading-4, .cm-markdown-heading-5, .cm-markdown-heading-6': {
        marginTop: '10px',
        marginBottom: '3px',
        fontSize: '16px',
        lineHeight: '1.38',
        fontWeight: '650',
        color: '#f4f4f5',
      },
      '.cm-markdown-paragraph': {
        fontSize: '15px',
        lineHeight: '1.72',
      },
      '.cm-markdown-unordered-list, .cm-markdown-ordered-list, .cm-markdown-task-open, .cm-markdown-task-done': {
        fontSize: '15px',
        lineHeight: '1.68',
      },
      '.cm-markdown-task-done': {
        color: '#9ca3af',
        textDecoration: 'line-through',
      },
      '.cm-markdown-quote': {
        marginTop: '4px',
        marginBottom: '4px',
        borderLeft: '3px solid rgba(255, 255, 255, 0.22)',
        color: '#cfcfd6',
        fontStyle: 'italic',
      },
      '.cm-markdown-code-fence': {
        color: '#a6adc8',
        fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
        fontSize: '13px',
      },
      '.cm-markdown-thematic-break': {
        height: '18px',
        margin: '8px 0',
        borderTop: '1px solid rgba(255, 255, 255, 0.14)',
        color: 'transparent',
      },
      '.cm-markdown-marker': {
        display: 'inline-flex',
        minWidth: '24px',
        marginLeft: '-30px',
        marginRight: '6px',
        justifyContent: 'center',
        color: '#8f8f98',
        fontWeight: '600',
        textDecoration: 'none',
        fontStyle: 'normal',
      },
      '.cm-markdown-marker-heading-1, .cm-markdown-marker-heading-2, .cm-markdown-marker-heading-3, .cm-markdown-marker-heading-4, .cm-markdown-marker-heading-5, .cm-markdown-marker-heading-6, .cm-markdown-marker-quote, .cm-markdown-marker-thematic-break': {
        width: '0',
        minWidth: '0',
        margin: '0',
      },
      '.cm-markdown-marker-code-fence': {
        minWidth: '34px',
        marginLeft: '-40px',
        marginRight: '6px',
        borderRadius: '4px',
        backgroundColor: 'rgba(255, 255, 255, 0.08)',
        color: '#cdd6f4',
        fontSize: '10px',
        textTransform: 'uppercase',
      },
    }),
  ];
}
