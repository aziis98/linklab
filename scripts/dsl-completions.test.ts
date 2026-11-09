import { describe, expect, test } from "bun:test";
import { CompletionContext, snippet } from "@codemirror/autocomplete";
import { EditorState } from "@codemirror/state";
import { python } from "@codemirror/lang-python";
import { syntaxTree } from "@codemirror/language";
import {
  DSL_SNIPPETS,
  dslCompletionSource,
  sceneObjects,
} from "../src/dsl-completions";

function complete(doc: string) {
  const state = EditorState.create({ doc, extensions: [python()] });
  return dslCompletionSource(new CompletionContext(state, doc.length, true));
}

describe("Scene DSL completion", () => {
  test("rod and ring members differ, and names come from declarations", () => {
    const rod = complete("beam = rod(left, up)\nbeam.")!;
    expect(rod.options.map((o) => o.label)).toContain("start");
    expect(rod.options.map((o) => o.label)).not.toContain("top");
    expect(rod.from).toBe("beam = rod(left, up)\nbeam.".length);
    const ring = complete("wheel = ring(origin, 2)\nwheel.")!;
    expect(ring.options.map((o) => o.label)).toContain("top");
    expect(ring.options.map((o) => o.label)).toContain("bottom");
    expect(ring.options.map((o) => o.label)).not.toContain("start");
    expect(complete('fake = "rod(left, up)"\nfake.')).toBeNull();
    expect(complete("a = rod(left, up)\na = 1\na.")).toBeNull();
  });
  test("body point-name completion includes custom points and the correct frame", () => {
    const result = complete(
      'scene_dimension(3)\nrotor = body({"tip": up*2})\nrotor.point("ti',
    )!;
    expect(result.options.map((o) => o.label)).toEqual([
      "origin",
      "x",
      "y",
      "z",
      "tip",
    ]);
    const planar = EditorState.create({
      doc: "# scene_dimension(3)\nb=body({})",
      extensions: [python()],
    });
    expect(sceneObjects(planar)[0].points).not.toContain("z");
  });
  test("constraint arguments prefer material points, objects or axes appropriately", () => {
    const prefix = "a=rod(left,up)\nb=ring(origin,2)\n";
    expect(complete(prefix + "pin(")!.options.map((o) => o.label)).toContain(
      "a.start",
    );
    expect(complete(prefix + "fixed(")!.options.map((o) => o.label)).toEqual([
      "a",
      "b",
    ]);
    expect(
      complete(prefix + "parallel(")!.options.map((o) => o.label),
    ).toContain("b.axis()");
  });
  test("ordinary comments and strings do not open DSL completion", () => {
    expect(complete("# ro")).toBeNull();
    expect(complete('text="ro')).toBeNull();
    expect(complete("a=rod(left,up)\ntext='a.point(\"")).toBeNull();
  });
  test("constructor keyword arguments and scene dimensions have contextual choices", () => {
    expect(
      complete("r=rod(origin,up, fi")!.options.map((o) => o.label),
    ).toContain("fixed");
    expect(complete("scene_dimension(")!.options.map((o) => o.label)).toEqual([
      "2",
      "3",
    ]);
  });
  test("all snippet defaults expand to Python syntax, without leftover placeholders", () => {
    expect(DSL_SNIPPETS.length).toBeGreaterThanOrEqual(35);
    for (const definition of DSL_SNIPPETS) {
      let state = EditorState.create({ extensions: [python()] });
      snippet(definition.template)(
        {
          get state() {
            return state;
          },
          dispatch(tr) {
            state = tr.state;
          },
        },
        null,
        0,
        0,
      );
      const errors: string[] = [];
      syntaxTree(state).iterate({
        enter(node) {
          if (node.type.isError)
            errors.push(state.sliceDoc(node.from, node.to));
        },
      });
      expect(errors, definition.label).toEqual([]);
      expect(state.doc.toString(), definition.label).not.toContain("${");
    }
  });
  test("declaration snippet links the variable name and object id", () => {
    const definition = DSL_SNIPPETS.find((s) => s.label === "new_rod")!;
    let state = EditorState.create({
      extensions: [EditorState.allowMultipleSelections.of(true)],
    });
    snippet(definition.template)(
      {
        get state() {
          return state;
        },
        dispatch(tr) {
          state = tr.state;
        },
      },
      null,
      0,
      0,
    );
    expect(state.selection.ranges).toHaveLength(2);
    for (const range of state.selection.ranges)
      expect(state.sliceDoc(range.from, range.to)).toBe("r");
  });
});
