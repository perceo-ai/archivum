import {
  type CompletionContext,
  type Completion,
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

export function matchPageForLinkQuery(page: Page, rawQuery: string) {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return 1;

  const haystacks = [page.title, page.slug].map((value) => value.toLowerCase());
  let best = 0;

  for (const value of haystacks) {
    if (value === query) best = Math.max(best, 1000);
    if (value.startsWith(query)) best = Math.max(best, 800 - value.length);
    const containsAt = value.indexOf(query);
    if (containsAt >= 0) best = Math.max(best, 600 - containsAt - value.length / 100);

    let lastIndex = -1;
    let score = 0;
    for (const char of query) {
      const index = value.indexOf(char, lastIndex + 1);
      if (index === -1) {
        score = 0;
        break;
      }
      score += index === lastIndex + 1 ? 12 : 5;
      lastIndex = index;
    }
    best = Math.max(best, score);
  }

  return best;
}

function pageLinkCompletions(pages: Page[], query: string, boost = 0): Completion[] {
  return pages
    .map((page) => ({ page, score: matchPageForLinkQuery(page, query) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score || a.page.title.localeCompare(b.page.title))
    .slice(0, 12)
    .map(({ page, score }) => ({
      label: page.title,
      apply: `[[${page.slug}|${page.title}]]`,
      detail: page.slug,
      boost: score + boost,
      type: 'text',
    }));
}

export function makeWikilinkCompletion(pages: Page[]) {
  return function wikilinkComplete(context: CompletionContext): CompletionResult | null {
    const wikilink = context.matchBefore(/\[\[[^\]\n]*$/);
    if (wikilink) {
      const typed = wikilink.text.slice(2);
      return {
        from: wikilink.from,
        options: pageLinkCompletions(pages, typed),
        validFor: /^\[\[[^\]\n]*$/,
      };
    }

    const mention = context.matchBefore(/(?:^|\s)@[\w/-]*$/);
    if (!mention) return null;

    const prefix = mention.text.startsWith('@') ? '' : mention.text[0];
    const typed = mention.text.trimStart().slice(1);
    const options = pageLinkCompletions(pages, typed, 100);

    return {
      from: mention.from + prefix.length,
      options,
      validFor: /^@[\w/-]*$/,
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
    span.textContent = this.title;
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
    makeWikilinkPlugin(pages, onNavigate),
    EditorView.theme({
      '.cm-wikilink-existing': {
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: '4px',
        backgroundColor: 'rgba(75, 145, 241, 0.13)',
        color: '#8fbcff',
        padding: '0 4px',
        textDecoration: 'none',
        cursor: 'pointer',
      },
      '.cm-wikilink-existing:hover': {
        backgroundColor: 'rgba(75, 145, 241, 0.2)',
        color: '#c8ddff',
      },
      '.cm-wikilink-missing': {
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: '4px',
        padding: '0 4px',
        color: '#6c7086',
        backgroundColor: 'rgba(255, 255, 255, 0.05)',
        textDecoration: 'none',
        cursor: 'pointer',
      },
      '.cm-wikilink-missing:hover': {
        color: '#a6adc8',
      },
      '.cm-tooltip-autocomplete': {
        overflow: 'hidden',
        border: '1px solid rgba(255, 255, 255, 0.09)',
        borderRadius: '7px',
        backgroundColor: '#202020',
        boxShadow: '0 18px 40px rgba(0, 0, 0, 0.32)',
        fontFamily: "'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      },
      '.cm-tooltip-autocomplete > ul': {
        maxHeight: '280px',
        padding: '5px',
      },
      '.cm-tooltip-autocomplete ul li': {
        display: 'flex',
        alignItems: 'center',
        minHeight: '32px',
        borderRadius: '5px',
        padding: '5px 8px',
        color: '#d4d4d8',
      },
      '.cm-tooltip-autocomplete ul li[aria-selected]': {
        backgroundColor: 'rgba(255, 255, 255, 0.08)',
        color: '#ffffff',
      },
      '.cm-tooltip-autocomplete .cm-completionIcon': {
        display: 'none',
      },
      '.cm-tooltip-autocomplete .cm-completionLabel': {
        fontWeight: '500',
      },
      '.cm-tooltip-autocomplete .cm-completionDetail': {
        marginLeft: '12px',
        color: '#71717a',
        fontSize: '11px',
      },
    }),
  ];
}
