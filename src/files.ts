export interface FileEntry {
  /** Stable uuid — the identity of the entry, independent of its (editable) name. */
  id: string
  name: string
  body: string
  editedAt: number
}

const FILES_KEY = 'cad-detect-free-motions.files.v2'
const ACTIVE_KEY = 'cad-detect-free-motions.active.v1'

const read = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

const write = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* quota / private mode — persistence is best-effort */
  }
}

export const BENCHMARK_EXAMPLES = [
  {
    name: 'planar-4-bar.py',
    body: `# Planar 4-Bar Linkage
l1 = 2.0
l2 = 3.0
d = 3.0

g1 = rod(origin, origin + right * d, id="g1")
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
    name: 'collinear-2-rod.py',
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
    name: 'mixed-dimensions-4-rod.py',
    body: `# Mixed Dimensions (4-Rod: 1D ⊔ 0D)
r1 = rod(left, up, id="r1")
r2 = rod(up, origin, id="r2")
r3 = rod(origin, down, id="r3")
r4 = rod(down, right, id="r4")

constraint_point_point(left, r1.start, id="j1")
constraint_point_point(r1.end, r2.start, id="j2")
constraint_point_point(r2.end, r3.start, id="j3")
constraint_point_point(r3.end, r4.start, id="j4")
constraint_point_point(r4.end, right, id="j5")
`,
  },
  {
    name: 'disjoint-modes-triangle.py',
    body: `# Disjoint Modes (Triangle)
y = (2.0**2 - 1.5**2) ** 0.5
r1 = rod(left * 1.5, up * y, id="r1")
r2 = rod(right * 1.5, up * y, id="r2")

constraint_point_point(left * 1.5, r1.start, id="j1")
constraint_point_point(right * 1.5, r2.start, id="j2")
constraint_point_point(r1.end, r2.end, id="j3")
`,
  },
]

export const newId = () =>
  crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`

export const createFile = (name: string, body = ''): FileEntry => ({
  id: newId(),
  name,
  body,
  editedAt: Date.now(),
})

export const ensureExamples = (files: FileEntry[]): FileEntry[] => {
  const exampleMap = new Map(BENCHMARK_EXAMPLES.map((e) => [e.name, e.body]))
  // Prefill/refresh benchmark examples with latest letter+number syntax at startup
  const updated = files.map((f) => {
    if (exampleMap.has(f.name)) {
      return { ...f, body: exampleMap.get(f.name)! }
    }
    return f
  })

  const existingNames = new Set(updated.map((f) => f.name))
  const now = Date.now()
  const missing = BENCHMARK_EXAMPLES.filter((e) => !existingNames.has(e.name)).map(
    (e, idx) => ({
      id: newId(),
      name: e.name,
      body: e.body,
      editedAt: now - (idx + 1) * 1000,
    }),
  )
  return [...updated, ...missing]
}

export const loadFiles = () => {
  const v2 = read<FileEntry[] | null>(FILES_KEY, null)
  if (v2) return ensureExamples(v2)
  const v1 = read<FileEntry[] | null>('cad-detect-free-motions.files.v1', null)
  return ensureExamples(v1 || [])
}
export const saveFiles = (files: FileEntry[]) => write(FILES_KEY, files)
export const loadActiveId = () => read<string | null>(ACTIVE_KEY, null)
export const saveActiveId = (id: string | null) => write(ACTIVE_KEY, id)

/** Delete a file entry by id */
export const deleteFile = (files: FileEntry[], id: string): FileEntry[] =>
  files.filter((f) => f.id !== id)

/** Rename by uuid. Returns the input array unchanged if the id is unknown. */
export const renameFile = (
  files: FileEntry[],
  id: string,
  name: string,
): FileEntry[] =>
  files.map((f) => (f.id === id ? { ...f, name } : f))

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.348],
  ['month', 12],
  ['year', Infinity],
]

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

export function relativeTime(ts: number, now = Date.now()): string {
  let delta = (ts - now) / 1000
  for (const [unit, span] of UNITS) {
    if (Math.abs(delta) < span) return rtf.format(Math.round(delta), unit)
    delta /= span
  }
  return rtf.format(Math.round(delta), 'year')
}
