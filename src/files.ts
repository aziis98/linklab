export interface FileEntry {
  /** Stable uuid — the identity of the entry, independent of its (editable) name. */
  id: string;
  name: string;
  body: string;
  editedAt: number;
}

const FILES_KEY = "cad-detect-free-motions.files.v2";
const ACTIVE_KEY = "cad-detect-free-motions.active.v1";

const read = <T>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
};

const write = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode — persistence is best-effort */
  }
};

export const BENCHMARK_EXAMPLES = [
  {
    name: "hopf-link-four-cables-3d.py",
    body: `# Hopf link: A=(cos(theta),sin(theta),0), B=(1+cos(phi),0,sin(phi)).
# The four cables shown here are modeled as fixed-length rods (no slack).
scene_dimension(3)
A = ring(origin, 1, id="A", fixed=True)
B = ring(right, 1, id="B", normal=down)

L = right / 4
H = right * 3 / 4
p = sqrt(15) / 4
q = sqrt(7) / 4

# A's local frame is XY; B's local frame is XZ, centered at (1,0,0).
a1 = A.rel(L + up*p, label="a1")
a2 = A.rel(L - up*p, label="a2")
a3 = A.rel(H + up*q, label="a3")
a4 = A.rel(H - up*q, label="a4")

b1 = B.rel(Vec(-3/4, q), label="b1")
b2 = B.rel(Vec(-3/4, -q), label="b2")
b3 = B.rel(Vec(-1/4, -p), label="b3")
b4 = B.rel(Vec(-1/4, p), label="b4")

cable1 = rod(a1, b1, id="cable1")
coincident(a1, cable1.start, id="joint_a1")
coincident(cable1.end, b1, id="joint_b1")

cable2 = rod(a2, b2, id="cable2")
coincident(a2, cable2.start, id="joint_a2")
coincident(cable2.end, b2, id="joint_b2")

cable3 = rod(a3, b3, id="cable3")
coincident(a3, cable3.start, id="joint_a3")
coincident(cable3.end, b3, id="joint_b3")

cable4 = rod(a4, b4, id="cable4")
coincident(a4, cable4.start, id="joint_a4")
coincident(cable4.end, b4, id="joint_b4")
`,
  },
  {
    name: "concentric-rings-three-braces-3d.py",
    body: `# Three radial braces at 120 degrees between concentric rings in local XY.
scene_dimension(3)
outer = ring(origin, 3, id="outer", fixed=True)
inner = ring(origin, 1.5, id="inner")

directions = range_circle(3, u=right, v=up)
for i, direction in enumerate(directions):
    outer_point = outer.rel(direction * outer.radius)
    inner_point = inner.rel(direction * inner.radius)
    bar = rod(outer_point, inner_point, id=f"brace_{i + 1}")
    coincident(outer_point, bar.start)
    coincident(bar.end, inner_point)

# The radial braces lock this configuration, despite infinitesimal motions.
`,
  },
  {
    name: "concentric-rings-3d.py",
    body: `# Top and bottom braces fix the diameter; the inner ring rotates around it.
scene_dimension(3)
outer = ring(origin, 3, id="outer", fixed=True)
inner = ring(origin, 1.5, id="inner")
bar_top = rod(outer.top, inner.top)
bar_bottom = rod(outer.bottom, inner.bottom)

coincident(outer.top, bar_top.start)
coincident(bar_top.end, inner.top)

coincident(outer.bottom, bar_bottom.start)
coincident(bar_bottom.end, inner.bottom)
`,
  },
  {
    name: "spatial-linked-pendulum.py",
    body: `# Spatial linked pendulum: a circular joint orbit plus a freely swinging rod.
scene_dimension(3)
a = rod(left, up, id="a")
b = rod(right, up, id="b")
c = rod(up, up * 2, id="c")
pin(a.start)
pin(b.start)
coincident(a.end, b.end)
coincident(a.end, c.start)
# Three DOFs: one for the shared joint, two for the direction of c. Try Wander.
`,
  },
  {
    name: "spatial-rotor.py",
    body: `from itertools import cycle, islice

# A triangular pyramid rotor on a spherical joint: three rotational DOFs.
scene_dimension(3)
stand = rod(down * 0.6, origin, id="stand", fixed=True)

pts = range_circle(3, radius=1.0, center=up * 1.4, u=right, v=forward)
edges = [rod(origin, p) for p in pts]
next_edges = list(islice(cycle(edges), 1, 4))
bases = [rod(p, q) for p, q in zip(pts, islice(cycle(pts), 1, 4))]

for e1, e2 in zip(edges, next_edges):
    coincident(e1.start, e2.start)

for e1, b, e2 in zip(edges, bases, next_edges):
    coincident(e1.end, b.start)
    coincident(b.end, e2.end)

pin(edges[0].start, origin, id="spherical_joint")
# Click Wander. The rotor turns freely around its fixed apex in all 3 axes.
`,
  },
  {
    name: "planar-4-bar-v2.py",
    body: `# Planar 4-Bar Linkage
l1 = 2.0
l2 = 3.0
d = 3.0

g1 = rod(origin, origin + right * d, id="g1", fixed=True)
r1 = rod(origin, up * l1, id="r1")
r2 = rod(g1.end, g1.end + up * l2, id="r2")
r3 = rod(r1.end, r2.end, id="r3")

constraint_point_point(g1.start, r1.start, id="j1")
constraint_point_point(r1.end, r3.start, id="j2")
constraint_point_point(r3.end, r2.end, id="j3")
constraint_point_point(r2.start, g1.end, id="j4")
`,
  },
  {
    name: "collinear-2-rod.py",
    body: `# Dead-Center Singularity (Collinear 2-Rod)
l = 2.0
r1 = rod(left * l, origin, id="r1")
r2 = rod(origin, right * l, id="r2")

constraint_point_point(left * l, r1.start, id="j1")
constraint_point_point(r1.end, r2.start, id="j2")
constraint_point_point(r2.end, right * l, id="j3")
`,
  },
  {
    name: "mixed-dimensions-4-rod-v2.py",
    body: `# Mixed Dimensions: a circle and an isolated point
q = origin
p = up
r1 = rod(Vec(1, 1), q, id="r1")
r2 = rod(Vec(1, -1), q, id="r2")
r3 = rod(origin, p, id="r3")
r4 = rod(q, p, id="r4")
pin(r1.start, Vec(1, 1))
pin(r2.start, Vec(1, -1))
pin(r3.start, origin)
coincident(r1.end, r2.end)
coincident(r2.end, r4.start)
coincident(r3.end, r4.end)
`,
  },
  {
    name: "disjoint-modes-triangle.py",
    body: `# Disjoint Modes (Triangle)
y = sqrt(4 - (3/2)**2)
r1 = rod(left * 1.5, up * y, id="r1")
r2 = rod(right * 1.5, up * y, id="r2")

constraint_point_point(left * 1.5, r1.start, id="j1")
constraint_point_point(right * 1.5, r2.start, id="j2")
constraint_point_point(r1.end, r2.end, id="j3")
`,
  },
  {
    name: "spatial-arm.py",
    body: `# Spatial arm moving in the XZ plane
scene_dimension(3)
ground = rod(left, right, id="base", fixed=True)
arm = rod(origin, Vec(1, 0, 1), id="arm")
pin(arm.start, origin)
plane(arm, origin, up)
# Drag the background to orbit; Shift-drag to pan. Object drags use the view plane.
`,
  },
  {
    name: "concentric-rings.py",
    body: `# Two rings joined by a hinged bar: 2 planar DOFs
scene_dimension(2)
outer = ring(origin, 3, id="outer", fixed=True)
inner = ring(origin, 1.5, id="inner")
bar = rod(outer.top, inner.top, id="bar")
coincident(outer.top, bar.start, id="outer_hinge")
coincident(bar.end, inner.top, id="inner_hinge")
`,
  },
];

export const newId = () =>
  crypto.randomUUID?.() ??
  `${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const createFile = (name: string, body = ""): FileEntry => ({
  id: newId(),
  name,
  body,
  editedAt: Date.now(),
});

export const checkReset = () => {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  if (params.has("reset")) {
    try {
      localStorage.removeItem(FILES_KEY);
      localStorage.removeItem(ACTIVE_KEY);
      localStorage.removeItem("cad-detect-free-motions.files.v1");
    } catch {
      /* ignore */
    }
    params.delete("reset");
    const search = params.toString();
    const newUrl =
      window.location.pathname + (search ? `?${search}` : "") + window.location.hash;
    window.history.replaceState(null, "", newUrl);
    return true;
  }
  return false;
};

export const ensureExamples = (files: FileEntry[]): FileEntry[] => {
  const previousRotors = [
    `# A tetrahedral rotor on a spherical joint: three rotational DOFs.
scene_dimension(3)
base = ring(Vec(0, 0, -0.4), 1.1, id="base", fixed=True)
stand = rod(Vec(0, 0, -0.4), origin, id="stand", fixed=True)
rotor = body({}, id="rotor")
pin(rotor.point("origin"), origin, id="spherical_joint")
# Click Wander. The rotor turns freely around its fixed corner in all 3 axes.`,
    `# A tetrahedral rotor on a spherical joint: three rotational DOFs.
scene_dimension(3)
stand = rod(down * 0.6, origin, id="stand", fixed=True)
rotor = body({}, id="rotor")
pin(rotor.point("origin"), origin, id="spherical_joint")
# Click Wander. The rotor turns freely around its fixed corner in all 3 axes.`,
  ];
  const previousHopf = `# Hopf link: A=(cos(theta),sin(theta),0), B=(1+cos(phi),0,sin(phi)).
# The four cables shown here are modeled as fixed-length rods (no slack).
scene_dimension(3)
A = ring(origin, 1, id="A", fixed=True)
B = ring(right, 1, id="B", normal=down)

L = right / 4
H = right * 3 / 4
p = sqrt(15) / 4
q = sqrt(7) / 4

# A's local frame is XY; B's local frame is XZ, centered at (1,0,0).
a_points = [A.rel(L + up*p), A.rel(L - up*p),
            A.rel(H + up*q), A.rel(H - up*q)]
b_points = [B.rel(Vec(-3/4, q)), B.rel(Vec(-3/4, -q)),
            B.rel(Vec(-1/4, -p)), B.rel(Vec(-1/4, p))]

for i, (a, b) in enumerate(zip(a_points, b_points)):
    cable = rod(a, b, id=f"cable_{i + 1}")
    coincident(a, cable.start)
    coincident(cable.end, b)
`;
  const updated = files.map((file) =>
    ((file.name === "spatial-rotor.py" && previousRotors.some((p) => p.trim() === file.body.trim())) ||
     (file.name === "hopf-link-four-cables-3d.py" && file.body.trim() === previousHopf.trim()))
      ? {
          ...file,
          body: BENCHMARK_EXAMPLES.find((e) => e.name === file.name)!.body,
        }
      : file,
  );
  const existingNames = new Set(updated.map((f) => f.name));
  const now = Date.now();
  const missing = BENCHMARK_EXAMPLES.filter(
    (e) => !existingNames.has(e.name),
  ).map((e, idx) => ({
    id: newId(),
    name: e.name,
    body: e.body,
    editedAt: now - (idx + 1) * 1000,
  }));
  return [...updated, ...missing];
};

export const loadFiles = () => {
  checkReset();
  const v2 = read<FileEntry[] | null>(FILES_KEY, null);
  if (v2) return ensureExamples(v2);
  const v1 = read<FileEntry[] | null>("cad-detect-free-motions.files.v1", null);
  return ensureExamples(v1 || []);
};
export const saveFiles = (files: FileEntry[]) => write(FILES_KEY, files);
export const loadActiveId = () => {
  checkReset();
  return read<string | null>(ACTIVE_KEY, null);
};
export const saveActiveId = (id: string | null) => write(ACTIVE_KEY, id);

/** Delete a file entry by id */
export const deleteFile = (files: FileEntry[], id: string): FileEntry[] =>
  files.filter((f) => f.id !== id);

/** Rename by uuid. Returns the input array unchanged if the id is unknown. */
export const renameFile = (
  files: FileEntry[],
  id: string,
  name: string,
): FileEntry[] => files.map((f) => (f.id === id ? { ...f, name } : f));

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 7],
  ["week", 4.348],
  ["month", 12],
  ["year", Infinity],
];

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function relativeTime(ts: number, now = Date.now()): string {
  let delta = (ts - now) / 1000;
  for (const [unit, span] of UNITS) {
    if (Math.abs(delta) < span) return rtf.format(Math.round(delta), unit);
    delta /= span;
  }
  return rtf.format(Math.round(delta), "year");
}
