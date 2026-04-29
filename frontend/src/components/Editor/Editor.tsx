import { useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react';
import { useNavigate } from 'react-router-dom';
import { EditorView, keymap } from '@codemirror/view';
import { EditorState } from '@codemirror/state';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { languages } from '@codemirror/language-data';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { oneDark } from '@codemirror/theme-one-dark';
import { useAppState } from '../../store';
import { updatePage } from '../../api';
import { wikilinkExtension } from './wikilinkExtension';

export interface EditorProps {
  slug: string;
  initialContent: string;
  onSave?: (status: 'saving' | 'saved' | 'error') => void;
  onChange?: (content: string) => void;
}

export type EditorHandle = {
  getContent: () => string;
  focus: () => void;
};

const Editor = forwardRef<EditorHandle, EditorProps>(function Editor(
  { slug, initialContent, onSave, onChange },
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
        backgroundColor: '#1e1e2e',
        fontSize: '14px',
      },
      '.cm-content': {
        padding: '16px 24px',
        maxWidth: '800px',
        margin: '0 auto',
      },
      '.cm-focused': {
        outline: 'none',
      },
      '.cm-line': {
        lineHeight: '1.7',
      },
      '.cm-cursor': {
        borderLeftColor: '#4B91F1',
      },
      '.cm-selectionBackground': {
        backgroundColor: '#4B91F130 !important',
      },
      '&.cm-focused .cm-selectionBackground': {
        backgroundColor: '#4B91F140 !important',
      },
      '.cm-gutters': {
        backgroundColor: '#1e1e2e',
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
        oneDark,
        baseTheme,
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

  return (
    <div
      ref={containerRef}
      className="h-full w-full overflow-auto"
      style={{ backgroundColor: '#1e1e2e' }}
    />
  );
});

export default Editor;
