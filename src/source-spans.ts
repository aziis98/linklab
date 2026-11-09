import { StateField, StateEffect, RangeSetBuilder } from "@codemirror/state";
import { EditorView, Decoration, type DecorationSet } from "@codemirror/view";

export interface SourceSpan {
  id: string;
  from: number;
  to: number;
}

/** Convert (1-based line, 1-based endLine, 0-based col, 0-based endCol) to char offsets */
export function spanToOffsets(
  doc: { line: (n: number) => { from: number; length: number }; length: number; lines: number },
  span: [number, number, number, number],
): { from: number; to: number } | null {
  const [startLine, endLine, startCol, endCol] = span;
  if (startLine < 1 || startLine > doc.lines || endLine < 1 || endLine > doc.lines) {
    return null;
  }
  const l1 = doc.line(startLine);
  const l2 = doc.line(endLine);
  const from = Math.min(l1.from + Math.max(0, startCol), doc.length);
  const to = Math.min(l2.from + Math.max(0, endCol), doc.length);
  return from <= to ? { from, to } : null;
}

export const setSpansEffect = StateEffect.define<SourceSpan[]>();
export const setActiveHighlightEffect = StateEffect.define<string | null>();

const spanMark = Decoration.mark({ class: "cm-source-span" });
const activeSpanMark = Decoration.mark({ class: "cm-source-span-active" });

export interface SpanState {
  spans: SourceSpan[];
  activeId: string | null;
  isStale: boolean;
  decorations: DecorationSet;
}

export const sourceSpanField = StateField.define<SpanState>({
  create() {
    return {
      spans: [],
      activeId: null,
      isStale: false,
      decorations: Decoration.none,
    };
  },
  update(value, tr) {
    let { spans, activeId, isStale } = value;

    if (tr.docChanged) {
      isStale = true;
      spans = [];
    }

    for (const e of tr.effects) {
      if (e.is(setSpansEffect)) {
        spans = e.value;
        isStale = false;
      } else if (e.is(setActiveHighlightEffect)) {
        activeId = e.value;
      }
    }

    const builder = new RangeSetBuilder<Decoration>();
    if (!isStale && spans.length > 0) {
      const sorted = [...spans].sort((a, b) => a.from - b.from || a.to - b.to);
      for (const span of sorted) {
        if (span.from < span.to && span.to <= tr.newDoc.length) {
          builder.add(
            span.from,
            span.to,
            span.id === activeId ? activeSpanMark : spanMark,
          );
        }
      }
    }

    return { spans, activeId, isStale, decorations: builder.finish() };
  },
  provide: (f) => EditorView.decorations.from(f, (v) => v.decorations),
});

export interface SourceSpanExtensionOptions {
  onHoverElement?: (id: string | null) => void;
  onCaretElement?: (id: string | null) => void;
}

export function sourceSpanExtension(options: SourceSpanExtensionOptions = {}) {
  return [
    sourceSpanField,
    EditorView.updateListener.of((update) => {
      if (update.selectionSet || update.docChanged) {
        const state = update.state.field(sourceSpanField);
        if (state.isStale || state.spans.length === 0) {
          options.onCaretElement?.(null);
          return;
        }
        const pos = update.state.selection.main.head;
        const matched = state.spans.find((s) => pos >= s.from && pos <= s.to);
        options.onCaretElement?.(matched ? matched.id : null);
      }
    }),
    EditorView.domEventHandlers({
      mousemove(event, view) {
        if (!options.onHoverElement) return false;
        const state = view.state.field(sourceSpanField);
        if (state.isStale || state.spans.length === 0) {
          options.onHoverElement(null);
          return false;
        }
        const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
        if (pos === null) {
          options.onHoverElement(null);
          return false;
        }
        const matched = state.spans.find((s) => pos >= s.from && pos <= s.to);
        options.onHoverElement(matched ? matched.id : null);
        return false;
      },
      mouseleave(_event, _view) {
        options.onHoverElement?.(null);
        return false;
      },
    }),
  ];
}
