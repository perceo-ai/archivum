import {
  autocompletion,
  type CompletionContext,
  type CompletionResult,
} from '@codemirror/autocomplete';
import {
  Decoration,
  type DecorationSet,
  EditorView,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from '@codemirror/view';
import { RangeSetBuilder, type Extension } from '@codemirror/state';
import type { Page } from '../../types';

// ─── Autocomplete ─────────────────────────────────────────────────────────────

function makeWikilinkCompletion(pages: Page[]) {
  return function wikilinkComplete(context: CompletionContext): CompletionResult | null {
    // Match [[ followed by any text up to the cursor
    const before = context.matchBefore(/\[\[[^\]]*$/);
    if (!before) return null;

    // Text the user typed after [[
    const typed = before.text.slice(2);

    const options = pages
      .filter(
        (p) =>
          p.title.toLowerCase().includes(typed.toLowerCase()) ||
          p.slug.toLowerCase().includes(typed.toLowerCase()),
      )
      .slice(0, 20)
      .map((p) => ({
        label: p.title,
        apply: `[[${p.slug}|${p.title}]]`,
        detail: p.slug,
        type: 'text',
      }));

    return {
      from: before.from,
      options,
      validFor: /^\[\[[^\]]*$/,
    };
  };
}

// ─── Decorations ──────────────────────────────────────────────────────────────

// Matches [[slug]] or [[slug|Title]]
const WIKILINK_RE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;

class WikilinkWidget extends WidgetType {
  constructor(
    readonly slug: string,
    readonly title: string,
    readonly exists: boolean,
    readonly onNavigate: (slug: string) => void,
  ) {
    super();
  }

  eq(other: WikilinkWidget) {
    return (
      this.slug === other.slug &&
      this.title === other.title &&
      this.exists === other.exists
    );
  }

  toDOM() {
    const span = document.createElement('span');
    span.className = this.exists ? 'cm-wikilink-existing' : 'cm-wikilink-missing';
    span.textContent = `[[${this.title}]]`;
    span.title = this.exists ? this.slug : `Create "${this.title}"`;
    span.addEventListener('click', (e) => {
      e.preventDefault();
      this.onNavigate(this.slug);
    });
    return span;
  }

  ignoreEvent() {
    return false;
  }
}

function buildDecorations(
  view: EditorView,
  slugSet: Set<string>,
  onNavigate: (slug: string) => void,
): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();

  for (const { from, to } of view.visibleRanges) {
    const text = view.state.doc.sliceString(from, to);
    let match: RegExpExecArray | null;
    WIKILINK_RE.lastIndex = 0;

    while ((match = WIKILINK_RE.exec(text)) !== null) {
      const start = from + match.index;
      const end = start + match[0].length;
      const slug = match[1].trim();
      const title = match[2]?.trim() ?? slug;
      const exists = slugSet.has(slug);

      const deco = Decoration.replace({
        widget: new WikilinkWidget(slug, title, exists, onNavigate),
        inclusive: false,
      });
      builder.add(start, end, deco);
    }
  }

  return builder.finish();
}

function makeWikilinkPlugin(pages: Page[], onNavigate: (slug: string) => void) {
  const slugSet = new Set(pages.map((p) => p.slug));

  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;

      constructor(view: EditorView) {
        this.decorations = buildDecorations(view, slugSet, onNavigate);
      }

      update(update: ViewUpdate) {
        if (update.docChanged || update.viewportChanged || update.selectionSet) {
          this.decorations = buildDecorations(update.view, slugSet, onNavigate);
        }
      }
    },
    {
      decorations: (v) => v.decorations,
      eventHandlers: {
        mousedown: (_e, _view) => {
          // Clicks handled in widget toDOM
          return false;
        },
      },
    },
  );
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function wikilinkExtension(
  pages: Page[],
  onNavigate: (slug: string) => void,
): Extension[] {
  return [
    autocompletion({
      override: [makeWikilinkCompletion(pages)],
      activateOnTyping: true,
    }),
    makeWikilinkPlugin(pages, onNavigate),
    EditorView.theme({
      '.cm-wikilink-existing': {
        color: '#4B91F1',
        textDecoration: 'underline',
        cursor: 'pointer',
      },
      '.cm-wikilink-existing:hover': {
        color: '#74b0ff',
      },
      '.cm-wikilink-missing': {
        color: '#6c7086',
        textDecoration: 'underline dotted',
        cursor: 'pointer',
      },
      '.cm-wikilink-missing:hover': {
        color: '#a6adc8',
      },
    }),
  ];
}
