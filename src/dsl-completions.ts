import {
  snippetCompletion,
  type Completion,
  type CompletionContext,
  type CompletionResult,
} from "@codemirror/autocomplete";
import { syntaxTree } from "@codemirror/language";
import { localCompletionSource } from "@codemirror/lang-python";
import type { EditorState } from "@codemirror/state";

interface SnippetDefinition {
  label: string;
  template: string;
  detail: string;
  category: "Objects" | "Constraints" | "Geometry" | "Scenes";
}
const entry = (
  category: SnippetDefinition["category"],
  label: string,
  template: string,
  detail: string,
): SnippetDefinition => ({ category, label, template, detail });

/** Defaults are editable snippet fields; repeated field numbers stay linked. */
export const DSL_SNIPPETS: readonly SnippetDefinition[] = [
  entry(
    "Objects",
    "rod",
    'rod(${1:origin}, ${2:up}, id="${3:r}")${0}',
    "rod(start, end, id=…)",
  ),
  entry(
    "Objects",
    "ring",
    'ring(${1:origin}, ${2:1.5}, id="${3:ring}")${0}',
    "rigid ring(center, radius, id=…)",
  ),
  entry(
    "Objects",
    "body",
    'body({"${1:tip}": ${2:up * 2}}, id="${3:body}")${0}',
    "rigid body with named material points",
  ),
  entry(
    "Objects",
    "new_rod",
    '${1:r} = rod(${2:origin}, ${3:up}, id="${1:r}")${0}',
    "declare a rod",
  ),
  entry(
    "Objects",
    "fixed_rod",
    '${1:ground} = rod(${2:left}, ${3:right}, id="${1:ground}", fixed=True)${0}',
    "declare a grounded rod",
  ),
  entry(
    "Objects",
    "new_ring",
    '${1:wheel} = ring(${2:origin}, ${3:1.5}, id="${1:wheel}")${0}',
    "declare a ring",
  ),
  entry(
    "Objects",
    "fixed_ring",
    '${1:ground} = ring(${2:origin}, ${3:3}, id="${1:ground}", fixed=True)${0}',
    "declare a grounded ring",
  ),
  entry(
    "Objects",
    "new_body",
    '${1:rotor} = body({}, id="${1:rotor}")${0}',
    "declare a rigid material frame",
  ),
  entry(
    "Constraints",
    "pin",
    "pin(${1:a.start})${0}",
    "pin a point at its initial position",
  ),
  entry(
    "Constraints",
    "pin_at",
    "pin(${1:a.start}, ${2:origin})${0}",
    "pin a point at a specified position",
  ),
  entry(
    "Constraints",
    "coincident",
    "coincident(${1:a.end}, ${2:b.start})${0}",
    "join two material points",
  ),
  entry(
    "Constraints",
    "constraint_point_point",
    "constraint_point_point(${1:a.end}, ${2:b.start})${0}",
    "compatibility alias for coincident",
  ),
  entry(
    "Constraints",
    "distance",
    "distance(${1:a.end}, ${2:b.end}, ${3:2})${0}",
    "fixed distance between two points",
  ),
  entry(
    "Constraints",
    "fixed",
    "fixed(${1:a})${0}",
    "ground an entire rigid object",
  ),
  entry(
    "Constraints",
    "plane",
    "plane(${1:a}, ${2:origin}, ${3:forward})${0}",
    "constrain an object or point to a plane",
  ),
  entry(
    "Constraints",
    "point_on_plane",
    "point_on_plane(${1:a.end}, ${2:origin}, ${3:forward})${0}",
    "point, plane origin, plane normal",
  ),
  entry(
    "Constraints",
    "parallel",
    "parallel(${1:a}.axis(), ${2:b}.axis())${0}",
    "parallel object axes",
  ),
  entry(
    "Constraints",
    "pin_endpoints",
    "pin(${1:a}.start)\npin(${1:a}.end)${0}",
    "pin both ends of a rod",
  ),
  entry(
    "Geometry",
    "Vec",
    "Vec(${1:0}, ${2:0}, ${3:0})${0}",
    "3D vector (x, y, z)",
  ),
  entry("Geometry", "Vec2", "Vec(${1:0}, ${2:0})${0}", "2D vector (x, y)"),
  entry("Geometry", "sqrt", "sqrt(${1:2})${0}", "exact algebraic square root"),
  entry(
    "Geometry",
    "Line",
    "Line(${1:origin}, ${2:right})${0}",
    "intersection primitive: origin, direction",
  ),
  entry(
    "Geometry",
    "Segment",
    "Segment(${1:left}, ${2:right})${0}",
    "intersection primitive: start, end",
  ),
  entry(
    "Geometry",
    "Circle",
    "Circle(${1:origin}, ${2:1})${0}",
    "intersection primitive: center, radius",
  ),
  entry(
    "Geometry",
    "Plane",
    "Plane(${1:origin}, ${2:forward})${0}",
    "intersection primitive: origin, normal",
  ),
  entry(
    "Geometry",
    "Sphere",
    "Sphere(${1:origin}, ${2:1})${0}",
    "intersection primitive: center, radius",
  ),
  entry(
    "Geometry",
    "intersect",
    "intersect(${1:Circle(origin, 2)}, ${2:Circle(right, 2)})${0}",
    "intersect geometric primitives",
  ),
  entry(
    "Scenes",
    "scene_dimension",
    "scene_dimension(${1:3})${0}",
    "set the scene dimension explicitly",
  ),
  entry(
    "Scenes",
    "scene_2d",
    "scene_dimension(2)\n${0}",
    "start a planar scene",
  ),
  entry(
    "Scenes",
    "scene_3d",
    "scene_dimension(3)\n${0}",
    "start a spatial scene",
  ),
  entry(
    "Scenes",
    "pendulum_2d",
    `scene_dimension(2)
\${1:arm} = rod(origin, up * \${2:2}, id="\${1:arm}")
pin(\${1:arm}.start)
\${0}`,
    "complete 1-DOF planar pendulum",
  ),
  entry(
    "Scenes",
    "spherical_pendulum",
    `scene_dimension(3)
\${1:arm} = rod(origin, up * \${2:2}, id="\${1:arm}")
pin(\${1:arm}.start)
\${0}`,
    "complete 2-DOF spatial pendulum",
  ),
  entry(
    "Scenes",
    "hinged_pair",
    `scene_dimension(2)
\${1:a} = rod(origin, up, id="\${1:a}")
\${2:b} = rod(\${1:a}.end, \${1:a}.end + right, id="\${2:b}")
pin(\${1:a}.start)
coincident(\${1:a}.end, \${2:b}.start)
\${0}`,
    "complete two-link planar arm",
  ),
  entry(
    "Scenes",
    "four_bar",
    `scene_dimension(2)
\${1:ground} = rod(origin, right * 3, id="\${1:ground}", fixed=True)
\${2:a} = rod(origin, up * 2, id="\${2:a}")
\${3:b} = rod(\${1:ground}.end, \${1:ground}.end + up * 3, id="\${3:b}")
\${4:c} = rod(\${2:a}.end, \${3:b}.end, id="\${4:c}")
coincident(\${1:ground}.start, \${2:a}.start)
coincident(\${1:ground}.end, \${3:b}.start)
coincident(\${2:a}.end, \${4:c}.start)
coincident(\${3:b}.end, \${4:c}.end)
\${0}`,
    "complete planar four-bar linkage",
  ),
  entry(
    "Scenes",
    "concentric_rings",
    `scene_dimension(2)
\${1:outer} = ring(origin, 3, id="\${1:outer}", fixed=True)
\${2:inner} = ring(origin, 1.5, id="\${2:inner}")
\${3:bar} = rod(\${1:outer}.top, \${2:inner}.top, id="\${3:bar}")
coincident(\${1:outer}.top, \${3:bar}.start)
coincident(\${3:bar}.end, \${2:inner}.top)
\${0}`,
    "complete 2-DOF rings and hinged bar",
  ),
  entry(
    "Scenes",
    "spatial_rotor",
    `scene_dimension(3)
\${1:stand} = rod(down * 0.6, origin, id="\${1:stand}", fixed=True)
\${2:rotor} = body({}, id="\${2:rotor}")
pin(\${2:rotor}.point("origin"))
\${0}`,
    "complete 3-DOF rigid rotor for Wander",
  ),
  entry(
    "Scenes",
    "linked_pendulum_3d",
    `scene_dimension(3)
\${1:a} = rod(left, up, id="\${1:a}")
\${2:b} = rod(right, up, id="\${2:b}")
\${3:c} = rod(up, up * 2, id="\${3:c}")
pin(\${1:a}.start)
pin(\${2:b}.start)
coincident(\${1:a}.end, \${2:b}.end)
coincident(\${1:a}.end, \${3:c}.start)
\${0}`,
    "complete 3-DOF linked spatial pendulum",
  ),
];

const sections = Object.fromEntries(
  ["Objects", "Constraints", "Geometry", "Scenes"].map((name, rank) => [
    name,
    { name, rank },
  ]),
);
const snippets = DSL_SNIPPETS.map((s) =>
  snippetCompletion(s.template, {
    label: s.label,
    type: "function",
    detail: s.detail,
    info: s.detail,
    section: sections[s.category],
    boost: 5,
  }),
);
const vectors: Completion[] = [
  "origin",
  "left",
  "right",
  "up",
  "down",
  "forward",
  "backward",
].map((label) => ({
  label,
  type: "constant",
  detail: "scene vector",
  section: sections.Geometry,
}));
interface SceneObject {
  name: string;
  kind: "rod" | "ring" | "body";
  points: string[];
}

/** Read declarations from Python syntax, so comments and strings cannot invent objects. */
export function sceneObjects(
  state: EditorState,
  before = state.doc.length,
): SceneObject[] {
  const objects = new Map<string, SceneObject>();
  let spatial = false;
  syntaxTree(state).iterate({
    enter(ref) {
      if (ref.name !== "CallExpression") return;
      const name = ref.node.getChild("VariableName"),
        value = ref.node.getChild("ArgList")?.getChild("Number");
      if (
        name &&
        value &&
        state.sliceDoc(name.from, name.to) === "scene_dimension"
      )
        spatial = state.sliceDoc(value.from, value.to) === "3";
    },
  });
  syntaxTree(state).iterate({
    enter(ref) {
      if (ref.name !== "AssignStatement" || ref.from >= before) return;
      const node = ref.node,
        variable = node.getChild("VariableName");
      if (!variable) return;
      const name = state.sliceDoc(variable.from, variable.to);
      const call = node.getChild("CallExpression");
      const callee = call?.getChild("VariableName");
      const kind = callee ? state.sliceDoc(callee.from, callee.to) : "";
      if (kind !== "rod" && kind !== "ring" && kind !== "body") {
        objects.delete(name);
        return;
      }
      const points =
        kind === "rod"
          ? ["a", "b"]
          : [
              "origin",
              "x",
              "y",
              ...(kind === "ring" ? ["bottom"] : spatial ? ["z"] : []),
            ];
      const dict = call?.getChild("ArgList")?.getChild("DictionaryExpression");
      for (const key of dict?.getChildren("String") ?? []) {
        const match = /^(['"])([A-Za-z_]\w*)\1$/.exec(
          state.sliceDoc(key.from, key.to),
        );
        if (key.nextSibling?.name === ":" && match) points.push(match[2]);
      }
      objects.set(name, { name, kind, points });
    },
  });
  return [...objects.values()];
}

function members(object: SceneObject): Completion[] {
  const property = (label: string, detail: string): Completion => ({
    label,
    type: "property",
    detail,
  });
  const list =
    object.kind === "rod"
      ? [property("start", "rod start point"), property("end", "rod end point")]
      : [
          ...(object.kind === "ring"
            ? [
                property("top", "ring top point"),
                property("bottom", "opposite rim point"),
              ]
            : []),
        ];
  list.push(
    property("origin", "body frame center"),
    property("center", "body frame center"),
    ...["relative", "rel"].map((name) => snippetCompletion(`${name}(Vec(\${1:0}, \${2:0}, \${3:0}))\${0}`, {
      label: name, type: "method", detail: "point in body-local coordinates",
    })),
    snippetCompletion('axis("${1:x}")${0}', {
      label: "axis",
      type: "method",
      detail: "material axis for parallel()",
    }),
  );
  for (const name of object.points)
    list.push({
      label: `point("${name}")`,
      apply: `point("${name}")`,
      type: "method",
      detail: "named material point",
    });
  return list;
}

export function dslCompletionSource(
  context: CompletionContext,
): CompletionResult | null {
  const { state, pos } = context;
  const node = syntaxTree(state).resolveInner(pos, -1);
  if (node.name === "Comment") return null;
  const objects = sceneObjects(state, pos);
  const pointName = context.matchBefore(/\b\w+\.(?:point|axis)\(\s*["']\w*/);
  if (pointName) {
    const match = /^(\w+)\.(point|axis)\(\s*["'](\w*)$/.exec(pointName.text)!;
    const object = objects.find((o) => o.name === match[1]);
    const actualCall =
      node.parent?.name === "ArgList" ? node.parent.parent : null;
    const actualMember = actualCall?.getChild("MemberExpression");
    if (
      object &&
      actualMember &&
      state.sliceDoc(actualMember.from, actualMember.to) ===
        `${match[1]}.${match[2]}`
    )
      return {
        from: pos - match[3].length,
        options: object.points
          .filter((p) => match[2] !== "axis" || p !== "origin")
          .map((label) => ({
            label,
            type: "property",
            detail: "material point name",
          })),
        validFor: /^\w*$/,
      };
  }
  if (node.name.includes("String")) return null;
  const member = context.matchBefore(/\b\w+\.\w*/);
  if (member) {
    const [name, prefix] = member.text.split(".");
    const object = objects.find((o) => o.name === name);
    return object
      ? {
          from: pos - prefix.length,
          options: members(object),
          validFor: /^\w*$/,
        }
      : null;
  }
  const word = context.matchBefore(/\w*/);
  if (!word || (!word.text && !context.explicit)) return null;
  let enclosing = node.parent;
  while (enclosing && enclosing.name !== "CallExpression")
    enclosing = enclosing.parent;
  const callee = enclosing?.getChild("VariableName");
  const constructor = callee ? state.sliceDoc(callee.from, callee.to) : "";
  if (constructor === "scene_dimension")
    return {
      from: word.from,
      options: ["2", "3"].map((label) => ({
        label,
        type: "constant",
        detail: label === "2" ? "planar scene" : "spatial scene",
      })),
      validFor: /^\d*$/,
    };
  const arity = { rod: 2, ring: 2, body: 1 }[constructor];
  if (arity !== undefined) {
    let index = 0;
    for (
      let item = enclosing!.getChild("ArgList")?.firstChild;
      item;
      item = item.nextSibling
    )
      if (item.name === "," && item.from < word.from) index++;
    if (index >= arity)
      return {
        from: word.from,
        validFor: /^\w*$/,
        options: [
          snippetCompletion('id="${1:object}"${0}', {
            label: "id",
            type: "property",
            detail: "object identifier",
          }),
          snippetCompletion("fixed=${1:True}${0}", {
            label: "fixed",
            type: "property",
            detail: "ground this object",
          }),
          ...(constructor === "rod" ? [
            snippetCompletion('frame="${1:full}"${0}', { label: "frame", type: "property", detail: "axial (default) or full material frame" }),
            snippetCompletion('normal=${1:forward}${0}', { label: "normal", type: "property", detail: "initial local XY plane normal" }),
          ] : constructor === "ring" ? [
            snippetCompletion('normal=${1:forward}${0}', { label: "normal", type: "property", detail: "initial ring plane normal" }),
          ] : constructor === "body" ? [
            snippetCompletion('center=${1:origin}${0}', { label: "center", type: "property", detail: "declared body frame center" }),
          ] : []),
          { label: "True", type: "constant" },
          { label: "False", type: "constant" },
        ],
      };
  }
  const before = state.sliceDoc(state.doc.lineAt(pos).from, pos);
  const call =
    /\b(pin|coincident|constraint_point_point|distance|point_on_plane|plane|parallel|fixed)\(\s*[\w.]*$/.exec(
      before,
    )?.[1];
  const objectNames: Completion[] = objects.map((o) => ({
    label: o.name,
    type: "variable",
    detail: o.kind,
    boost: 15,
  }));
  if (call === "fixed")
    return { from: word.from, options: objectNames, validFor: /^\w*$/ };
  const references: Completion[] = objects.flatMap((o) =>
    call === "parallel"
      ? [
          {
            label: `${o.name}.axis()`,
            type: "method",
            detail: "object axis",
            boost: 15,
          },
        ]
      : o.kind === "rod"
        ? ["start", "end"].map((p) => ({
            label: `${o.name}.${p}`,
            type: "property",
            detail: "rod point",
            boost: 15,
          }))
        : o.points.map((p) => ({
            label: `${o.name}.point("${p}")`,
            type: "property",
            detail: "material point",
            boost: 15,
          })),
  );
  const locals = localCompletionSource(context)?.options ?? [];
  const known = new Set(objectNames.map((o) => o.label));
  return {
    from: word.from,
    validFor: /^\w*$/,
    options: call
      ? [...references, ...(call === "plane" ? objectNames : []), ...vectors]
      : [
          ...snippets,
          ...vectors,
          ...objectNames,
          ...locals.filter((c) => !known.has(c.label)),
        ],
  };
}
