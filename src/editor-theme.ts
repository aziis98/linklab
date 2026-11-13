import { EditorView } from "@codemirror/view";
import { HighlightStyle } from "@codemirror/language";
import { tags } from "@lezer/highlight";

export const editorTheme = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "var(--text-sm)",
    color: "var(--fg)",
    backgroundColor: "var(--bg)",
  },
  "&.cm-focused": { outline: "1px solid var(--accent)", outlineOffset: "-1px" },
  ".cm-scroller": {
    fontFamily: "var(--font-mono)",
    lineHeight: "1.6",
    overflow: "auto",
  },
  ".cm-content": { padding: "var(--sp-2) 0", caretColor: "var(--fg)" },
  ".cm-line": { padding: "0 var(--sp-3)" },
  ".cm-gutters": {
    backgroundColor: "var(--bg-sunken)",
    color: "var(--fg-muted)",
    borderRight: "1px solid var(--line-color)",
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 var(--sp-2)" },
  ".cm-activeLine, .cm-activeLineGutter": {
    backgroundColor: "var(--bg-hover)",
  },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--fg)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "var(--focus)",
  },
  ".cm-selectionMatch": {
    backgroundColor: "color-mix(in srgb, var(--accent) 12%, transparent)",
    borderRadius: "2px",
  },
  ".cm-matchingBracket": {
    backgroundColor: "var(--bg-active)",
    outline: "1px solid var(--line-strong)",
  },
  ".cm-tooltip": {
    border: "1px solid var(--line-strong)",
    backgroundColor: "var(--bg-raised)",
    color: "var(--fg)",
    borderRadius: "var(--radius)",
    boxShadow: "var(--shadow-pop)",
    fontFamily: "var(--font-ui)",
  },
  ".cm-tooltip-autocomplete": { maxWidth: "min(460px, calc(100vw - 16px))" },
  ".cm-tooltip-autocomplete > ul": {
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-sm)",
    maxHeight: "min(300px, 50vh)",
  },
  ".cm-tooltip-autocomplete > ul > li": { padding: "4px 8px" },
  ".cm-tooltip-autocomplete > ul > li[aria-selected=true]": {
    backgroundColor: "var(--bg-active)",
    color: "var(--fg)",
  },
  ".cm-completionDetail": {
    color: "var(--fg-muted)",
    fontStyle: "normal",
    marginLeft: "var(--sp-3)",
  },
  ".cm-completionMatchedText": {
    textDecoration: "none",
    fontWeight: "600",
    color: "var(--accent)",
  },
  ".cm-completionSection": {
    color: "var(--fg-muted)",
    fontFamily: "var(--font-ui)",
    borderBottom: "1px solid var(--line-color)",
  },
  ".cm-completionInfo": { padding: "var(--sp-2)", maxWidth: "260px" },
  ".cm-snippetField": {
    backgroundColor: "var(--bg-active)",
    outline: "1px solid var(--line-strong)",
  },
  ".cm-snippetFieldPosition": { borderLeftColor: "var(--accent)" },
});

export const editorHighlighting = HighlightStyle.define([
  { tag: tags.comment, color: "var(--fg-muted)" },
  { tag: [tags.keyword, tags.bool, tags.null], color: "var(--accent)" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--ok)" },
  {
    tag: [tags.number, tags.typeName, tags.className],
    color: "var(--cad-badge-fg)",
  },
  {
    tag: [tags.function(tags.variableName), tags.definition(tags.variableName)],
    color: "var(--cad-badge-fg)",
  },
]);
