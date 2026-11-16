export interface FileEntry {
  /** Stable uuid — the identity of the entry, independent of its (editable) name. */
  id: string;
  name: string;
  body: string;
  editedAt: number;
}

const FILES_KEY = "linklab.files.v2";
const ACTIVE_KEY = "linklab.active.v1";

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

const EXAMPLE_MODULES = import.meta.glob<string>("./examples/*.py", {
  query: "?raw",
  import: "default",
  eager: true,
});

const EXAMPLE_ORDER = [
  "hopf-link-four-cables-3d.py",
  "concentric-rings-three-braces-3d.py",
  "concentric-rings-3d.py",
  "spatial-linked-pendulum.py",
  "spatial-rotor.py",
  "planar-4-bar-v2.py",
  "collinear-2-rod.py",
  "mixed-dimensions-4-rod-v2.py",
  "disjoint-modes-triangle.py",
  "spatial-arm.py",
  "concentric-rings.py",
] as const;

export const BENCHMARK_EXAMPLES = EXAMPLE_ORDER.map((name) => {
  const body = EXAMPLE_MODULES[`./examples/${name}`];
  if (body === undefined) {
    throw new Error(`Missing example file: ${name}`);
  }
  return { name, body };
});

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
    } catch {
      /* ignore */
    }
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
  const previousHopfExplicit = `# Hopf link: A=(cos(theta),sin(theta),0), B=(1+cos(phi),0,sin(phi)).
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
`;
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
     (file.name === "hopf-link-four-cables-3d.py" && [previousHopf,previousHopfExplicit].some(previous=>file.body.trim() === previous.trim())))
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
  return ensureExamples(v2 || []);
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
