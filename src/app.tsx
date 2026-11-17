import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import IconPlayerPlay from "~icons/tabler/player-play";
import IconRefresh from "~icons/tabler/refresh";
import IconArrowsMaximize from "~icons/tabler/arrows-maximize";
import { Split } from "@/components/splitter";
import { Editor } from "@/components/editor";
import { FileSwitcher } from "@/components/file-switcher";
import { Viewer, type SceneData } from "@/components/viewer";
import { spanToOffsets, type SourceSpan } from "./source-spans";
import { Text } from "@codemirror/state";
import {
  createFile,
  deleteFile,
  ensureExamples,
  loadActiveId,
  loadFiles,
  renameFile,
  saveActiveId,
  saveFiles,
  type FileEntry,
} from "@/files";
import { Dropdown } from "./components/dropdown";
import {
  getPyodideStatus,
  request,
  stop,
  subscribePyodideStatus,
  type PyodideStatus,
} from "@/pyodide";

type State = "idle" | "loading" | "ready" | "error";

const SEED_BODY = `# Planar 4-Bar Linkage
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
`;

const seedFiles = (): FileEntry[] => [createFile("main.py", SEED_BODY)];

export function App() {
  const [files, setFiles] = useState<FileEntry[]>(() => loadFiles());
  const [activeId, setActiveId] = useState<string | null>(() => {
    const saved = loadActiveId();
    const fs = files;
    if (saved && fs.some((f) => f.id === saved)) return saved;
    return fs[0]?.id ?? null;
  });
  const [state, setState] = useState<State>("idle");
  const [pyodideStatus, setPyodideStatus] = useState<PyodideStatus>(() =>
    getPyodideStatus(),
  );
  const [initialBootSettled, setInitialBootSettled] = useState(false);
  const [solverMode, setSolverMode] = useState<"numerical" | "topological">(
    "numerical",
  );
  const [dimension, setDimension] = useState(0);
  const [motionToolbar, setMotionToolbar] = useState<HTMLDivElement | null>(null);
  const [scene, setScene] = useState<SceneData | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [activeElementId, setActiveElementId] = useState<string | string[] | null>(null);

  // first run: seed a starter file
  useEffect(() => {
    if (files.length) return;
    const seed = seedFiles();
    setFiles(seed);
    setActiveId(seed[0].id);
  }, [files.length]);

  useEffect(() => saveFiles(files), [files]);
  useEffect(() => saveActiveId(activeId), [activeId]);
  useEffect(() => {
    setFiles((fs) => ensureExamples(fs));
  }, []);

  useEffect(() => subscribePyodideStatus(setPyodideStatus), []);

  useEffect(() => {
    if (scene !== null || (runError !== null && pyodideStatus.phase === "ready")) {
      setInitialBootSettled(true);
    }
  }, [scene, runError, pyodideStatus.phase]);

  const active = useMemo(
    () => files.find((f) => f.id === activeId) ?? null,
    [files, activeId],
  );

  const patch = (id: string, body: string) =>
    setFiles((fs) =>
      fs.map((f) => (f.id === id ? { ...f, body, editedAt: Date.now() } : f)),
    );

  const addFile = () => {
    const file = createFile(`untitled-${files.length + 1}.py`);
    setFiles([file, ...files]);
    setActiveId(file.id);
  };

  const rename = (id: string, name: string) =>
    setFiles((fs) => renameFile(fs, id, name));

  const removeFile = (id: string) => {
    const next = deleteFile(files, id);
    setFiles(next);
    if (activeId === id) {
      setActiveId(next[0]?.id ?? null);
    }
  };

  const runRevision = useRef(0);
  const run = async () => {
    const revision = ++runRevision.current;
    if (!active) return;
    setRunError(null);
    setScene(null);
    setState("loading");
    try {
      const data = await request<SceneData>({
        op: "run",
        source: active.body,
        dimension: dimension || null,
        mode: solverMode,
      });
      if (revision === runRevision.current) setScene(data);
    } catch (err) {
      if (revision === runRevision.current) setRunError(String(err));
    } finally {
      if (revision === runRevision.current) setState("ready");
    }
  };

  useEffect(() => {
    if (active) run();
  }, [activeId, dimension, solverMode]);

  const sourceSpans = useMemo<SourceSpan[]>(() => {
    if (!scene || !active?.body) return [];
    const doc = Text.of(active.body.split("\n"));
    const map = new Map<string, SourceSpan>();

    const addSpan = (id: string, spanTuple: [number, number, number, number]) => {
      const offsets = spanToOffsets(doc, spanTuple);
      if (!offsets) return;
      const key = `${offsets.from}:${offsets.to}`;
      const existing = map.get(key);
      if (existing) {
        if (!existing.ids.includes(id)) {
          existing.ids.push(id);
        }
      } else {
        map.set(key, {
          id,
          ids: [id],
          from: offsets.from,
          to: offsets.to,
        });
      }
    };

    for (const obj of scene.objects) {
      if (obj.source_span) addSpan(obj.id, obj.source_span);
    }
    for (const c of scene.constraints) {
      if (c.source_span) addSpan(c.id, c.source_span);
    }
    return Array.from(map.values());
  }, [scene, active?.body]);

  const stateLabel: Record<State, string> = {
    idle: "idle",
    loading: "loading",
    ready: "ready",
    error: "error",
  };

  return (
    <div class="app">
      <header class="bar bar--app">
        <span class="brand">
          LinkLab
        </span>
        <FileSwitcher
          files={files}
          activeId={activeId}
          onSelect={setActiveId}
          onNew={addFile}
          onRename={rename}
          onDelete={removeFile}
        />
        <span class="bar__spacer" />
        <span
          class="dot"
          data-state={
            pyodideStatus.phase === "error"
              ? "error"
              : state === "ready"
                ? "ok"
                : state
          }
        />
        <span>{pyodideStatus.phase === "error" ? "error" : stateLabel[state]}</span>
        <Dropdown
          label="Scene dimension"
          value={String(dimension)}
          onChange={(v) => setDimension(Number(v))}
          options={[
            { value: "0", label: "Auto dimension" },
            { value: "2", label: "Planar (2D)" },
            { value: "3", label: "Spatial (3D)" },
          ]}
        />
        <Dropdown
          label="Solver mode"
          value={solverMode}
          onChange={(v) => setSolverMode(v as "numerical" | "topological")}
          options={[
            { value: "numerical", label: "Numerical" },
            { value: "topological", label: "Topological" },
          ]}
        />
        <button
          type="button"
          class="btn btn--primary"
          disabled={state === "loading" || !active}
          onClick={run}
        >
          <IconPlayerPlay class="icon" width="12" height="12" />
          Run
        </button>
        <div class="motion-toolbar" ref={setMotionToolbar} />
      </header>

      <Split
        left={
          <section class="pane">
            <Editor
              key={active?.id ?? "empty"}
              value={active?.body ?? ""}
              onChange={(body) => active && patch(active.id, body)}
              onRun={run}
              spans={sourceSpans}
              activeElementId={activeElementId}
              onHoverElement={setActiveElementId}
              onCaretElement={setActiveElementId}
            />
          </section>
        }
        right={
          <section class="pane">
            <div class="bar bar--pane">
              <span class="bar__title">Render</span>
              <span class="bar__spacer" />
              <button
                type="button"
                class="btn btn--icon"
                title="Re-run"
                disabled={state === "loading" || !active}
                onClick={run}
              >
                <IconRefresh class="icon" width="14" height="14" />
              </button>
              <button
                type="button"
                class="btn btn--icon"
                title="Fullscreen"
                disabled
              >
                <IconArrowsMaximize class="icon" width="14" height="14" />
              </button>
            </div>
            <Viewer
              motionToolbar={motionToolbar}
              scene={scene}
              error={runError}
              pyodideStatus={!initialBootSettled ? pyodideStatus : null}
              onRetryPyodide={() => {
                stop();
                void run();
              }}
              highlightElementId={activeElementId}
              onHoverElement={setActiveElementId}
            />
          </section>
        }
      />

      <footer class="status">
        <span class="status__spacer" />
        <span>
          pyodide{" "}
          {pyodideStatus.phase === "ready"
            ? "ready"
            : pyodideStatus.phase === "error"
              ? "error"
              : `${Math.round(pyodideStatus.progress * 100)}%`}
        </span>
      </footer>
    </div>
  );
}
