import { useLayoutEffect, useRef } from "preact/hooks";
import { Annotation, EditorState, Transaction } from "@codemirror/state";
import {
  EditorView,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
} from "@codemirror/view";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentLess,
  indentMore,
} from "@codemirror/commands";
import {
  bracketMatching,
  indentUnit,
  syntaxHighlighting,
} from "@codemirror/language";
import { python } from "@codemirror/lang-python";
import {
  acceptCompletion,
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionStatus,
  nextSnippetField,
  prevSnippetField,
  startCompletion,
} from "@codemirror/autocomplete";
import { dslCompletionSource } from "../dsl-completions";
import { editorHighlighting, editorTheme } from "../editor-theme";
import {
  setActiveHighlightEffect,
  setSpansEffect,
  sourceSpanExtension,
  type SourceSpan,
} from "../source-spans";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onRun?: () => void;
  spans?: SourceSpan[];
  activeElementId?: string | string[] | null;
  onHoverElement?: (id: string | string[] | null) => void;
  onCaretElement?: (id: string | string[] | null) => void;
}
const externalUpdate = Annotation.define<boolean>();

/** Minimal Python editor; DSL completions inspect syntax without executing code. */
export function Editor(props: Props) {
  const host = useRef<HTMLDivElement>(null),
    editor = useRef<EditorView | null>(null);
  const latest = useRef(props);
  latest.current = props;
  useLayoutEffect(() => {
    const view = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: latest.current.value,
        extensions: [
          python(),
          history(),
          lineNumbers(),
          highlightActiveLine(),
          highlightActiveLineGutter(),
          drawSelection(),
          bracketMatching(),
          closeBrackets(),
          EditorView.lineWrapping,
          indentUnit.of("    "),
          EditorState.tabSize.of(4),
          EditorState.allowMultipleSelections.of(true),
          editorTheme,
          syntaxHighlighting(editorHighlighting),
          autocompletion({
            override: [dslCompletionSource],
            maxRenderedOptions: 60,
          }),
          keymap.of([
            {
              key: "Mod-Enter",
              run: () => {
                latest.current.onRun?.();
                return true;
              },
            },
            {
              key: "Tab",
              run: (v) =>
                nextSnippetField(v) ||
                (completionStatus(v.state) === "active" &&
                  acceptCompletion(v)) ||
                indentMore(v),
            },
            {
              key: "Shift-Tab",
              run: (v) => prevSnippetField(v) || indentLess(v),
            },
            ...closeBracketsKeymap,
            ...defaultKeymap,
            ...historyKeymap,
          ]),
          EditorView.contentAttributes.of({
            "aria-label": "Scene DSL editor",
            "aria-description":
              "Python scene DSL. Ctrl or Command Enter runs. Ctrl Space or right-click opens snippets. Tab moves between snippet fields.",
            spellcheck: "false",
            autocapitalize: "off",
            autocorrect: "off",
          }),
          sourceSpanExtension({
            onHoverElement: (id) => latest.current.onHoverElement?.(id),
            onCaretElement: (id) => latest.current.onCaretElement?.(id),
          }),
          EditorView.updateListener.of((update) => {
            if (
              update.docChanged &&
              !update.transactions.some((t) => t.annotation(externalUpdate))
            )
              latest.current.onChange(update.state.doc.toString());
          }),
          EditorView.domEventHandlers({
            contextmenu(event, view) {
              event.preventDefault();
              const pos = view.posAtCoords({
                x: event.clientX,
                y: event.clientY,
              });
              if (pos !== null) view.dispatch({ selection: { anchor: pos } });
              view.focus();
              startCompletion(view);
              return true;
            },
          }),
        ],
      }),
    });
    editor.current = view;
    return () => {
      view.destroy();
      editor.current = null;
    };
  }, []);
  useLayoutEffect(() => {
    const view = editor.current;
    if (view && view.state.doc.toString() !== props.value)
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: props.value },
        annotations: [
          externalUpdate.of(true),
          Transaction.addToHistory.of(false),
        ],
      });
  }, [props.value]);

  useLayoutEffect(() => {
    const view = editor.current;
    if (!view) return;
    view.dispatch({
      effects: setSpansEffect.of(props.spans ?? []),
    });
  }, [props.spans]);

  useLayoutEffect(() => {
    const view = editor.current;
    if (!view) return;
    view.dispatch({
      effects: setActiveHighlightEffect.of(props.activeElementId ?? null),
    });
  }, [props.activeElementId]);

  return <div class="editor" ref={host} />;
}
