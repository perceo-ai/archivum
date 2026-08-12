import { useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react';
import { useNavigate } from 'react-router-dom';
import { autocompletion } from '@codemirror/autocomplete';
import { EditorView, keymap } from '@codemirror/view';
import { EditorState } from '@codemirror/state';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { languages } from '@codemirror/language-data';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { useAppState } from '../../store';
import { updatePage, type MemorySuggestion } from '../../api';
import { Button } from '../ui/Button';
import { makeWikilinkCompletion, wikilinkExtension } from './wikilinkExtension';
import { markdownBlockExtension, slashCommandCompletion } from './markdownBlockExtension';

export interface EditorProps {
  slug: string;
  initialContent: string;
  onSave?: (status: 'saving' | 'saved' | 'error') => void;
  onChange?: (content: string) => void;
  pendingSuggestions?: MemorySuggestion[];
  onAcceptSuggestion?: (suggestion: MemorySuggestion) => void | Promise<void>;
  onRejectSuggestion?: (suggestion: MemorySuggestion) => void | Promise<void>;
}

export type EditorHandle = {
  getContent: () => string;
  focus: () => void;
};

const Editor = forwardRef<EditorHandle, EditorProps>(function Editor(
  { slug, initialContent, onSave, onChange, pendingSuggestions = [], onAcceptSuggestion, onRejectSuggestion },
  ref,
) {
  const { pages } = useAppState();
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout>>();
  const slugRef = useRef(slug);
  slugRef.current = slug;

  useImperativeHandle(
    ref,
    () => ({
      getContent: () => viewRef.current?.state.doc.toString() ?? initialContent,
      focus: () => viewRef.current?.focus(),
    }),
    [initialContent],
  );

  const save = useCallback(
    async (content: string) => {
      onSave?.('saving');
      try {
        await updatePage(slugRef.current, { content });
        onSave?.('saved');
      } catch {
        onSave?.('error');
      }
    },
    [onSave],
  );

  const scheduleSave = useCallback(
    (content: string) => {
      clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => save(content), 1000);
    },
    [save],
  );

  useEffect(() => {
    if (!containerRef.current) return;

    const wikilinks = wikilinkExtension(pages, (targetSlug) => {
      navigate(`/wiki/${targetSlug}`);
    });

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        const content = update.state.doc.toString();
        onChange?.(content);
        scheduleSave(content);
      }
    });

    const baseTheme = EditorView.theme({
      '&': {
        height: '100%',
        backgroundColor: 'transparent',
        color: 'hsl(var(--foreground))',
        fontSize: '16px',
      },
      '.cm-scroller': {
        fontFamily: "'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        backgroundColor: 'transparent',
      },
      '.cm-content': {
        padding: '18px 32px 72px',
        width: '100%',
        caretColor: '#ffffff',
      },
      '.cm-focused': {
        outline: 'none',
      },
      '.cm-line': {
        lineHeight: '1.7',
      },
      '.cm-activeLine': {
        backgroundColor: 'transparent',
      },
      '.cm-cursor': {
        borderLeftColor: 'hsl(var(--foreground))',
      },
      '.cm-selectionBackground': {
        backgroundColor: 'hsl(var(--primary) / 0.22) !important',
      },
      '&.cm-focused .cm-selectionBackground': {
        backgroundColor: 'hsl(var(--primary) / 0.28) !important',
      },
      '.cm-matchingBracket, .cm-nonmatchingBracket': {
        backgroundColor: 'transparent',
        outline: 'none',
      },
      '.cm-gutters': {
        display: 'none',
        backgroundColor: 'transparent',
        border: 'none',
        color: '#3a3a4a',
      },
    });

    const state = EditorState.create({
      doc: initialContent,
      extensions: [
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        markdown({
          base: markdownLanguage,
          codeLanguages: languages,
        }),
        baseTheme,
        autocompletion({
          override: [slashCommandCompletion, makeWikilinkCompletion(pages)],
          activateOnTyping: true,
        }),
        markdownBlockExtension(),
        updateListener,
        ...wikilinks,
        EditorView.lineWrapping,
      ],
    });

    const view = new EditorView({
      state,
      parent: containerRef.current,
    });

    viewRef.current = view;

    return () => {
      clearTimeout(saveTimer.current);
      view.destroy();
      viewRef.current = null;
    };
    // Only re-initialize when slug changes (initialContent is the starting value)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  // When pages list changes (new pages added), update wikilink decorations
  // by updating the extension — simplest approach: destroy+recreate is costly,
  // so we rely on the plugin re-running on each viewport change which picks up
  // the latest slugSet via closure. For a full refresh, a compartment could be
  // used, but for typical usage this is fine.

  const suggestions = pendingSuggestions.filter((suggestion) => suggestion.status === 'pending');

  return (
    <div className="flex h-full w-full flex-col">
      {suggestions.length > 0 && (
        <div className="border-b border-white/[0.06] px-4 py-3">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Suggestions</div>
          <div className="space-y-2">
            {suggestions.map((suggestion) => (
              <div key={suggestion.id} className="flex flex-wrap items-center gap-2 text-sm">
                <code className="min-w-0 flex-1 truncate text-zinc-300">{suggestion.proposed_markdown}</code>
                <Button type="button" variant="secondary" size="sm" onClick={() => void onAcceptSuggestion?.(suggestion)}>
                  Accept
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => void onRejectSuggestion?.(suggestion)}>
                  Reject
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
      <div ref={containerRef} className="min-h-0 flex-1 overflow-auto" style={{ backgroundColor: 'transparent' }} />
    </div>
  );
});

export default Editor;
