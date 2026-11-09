import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import IconPlayerPlay from "~icons/tabler/player-play";
import IconPlayerStop from "~icons/tabler/player-stop";
import IconRefresh from "~icons/tabler/refresh";
import IconArrowsMaximize from "~icons/tabler/arrows-maximize";
import IconRotate3d from "~icons/tabler/rotate-3d";
import { Split } from "@/components/splitter";
import { Editor } from "@/components/editor";
import { FileSwitcher } from "@/components/file-switcher";
import { Viewer, type SceneData } from "@/components/viewer";
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
import { request, stop } from "@/pyodide";

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
  const [version, setVersion] = useState("");
  const [solverMode, setSolverMode] = useState<"numerical" | "topological">(
    "numerical",
  );
  const [dimension, setDimension] = useState(0);
  const [scene, setScene] = useState<SceneData | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

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

  useEffect(() => {
    setState("ready");
    setVersion("worker");
  }, []);

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
          <IconRotate3d class="icon" width="14" height="14" />
          CAD Detect Free Motions
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
        <span class="dot" data-state={state === "ready" ? "ok" : state} />
        <span>{stateLabel[state]}</span>
        <button
          type="button"
          class="btn btn--primary"
          disabled={state === "loading" || !active}
          onClick={run}
        >
          <IconPlayerPlay class="icon" width="12" height="12" />
          Run
        </button>
        <button
          type="button"
          class="btn btn--danger"
          onClick={() => {
            stop();
            setState("ready");
            setScene(null);
          }}
          disabled={state !== "loading"}
        >
          <IconPlayerStop class="icon" width="12" height="12" />
          Stop
        </button>
      </header>

      <Split
        left={
          <section class="pane">
            <Editor
              key={active?.id ?? "empty"}
              value={active?.body ?? ""}
              onChange={(body) => active && patch(active.id, body)}
              onRun={run}
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
            <Viewer scene={scene} error={runError} />
          </section>
        }
      />

      <footer class="status">
        <span class="status__spacer" />
        <span>pyodide {version || "—"}</span>
      </footer>
    </div>
  );
}
