import { subscribePreview } from "../solver/client";
import type { VNode } from "preact";
import { createPortal, lazy, Suspense } from "preact/compat";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { ConstructionGrid } from "./construction-grid";
import { ExplorationPanel, type Roadmap } from "./exploration-panel";
import { MotionPopover } from "./motion-popover";
import { Dropdown } from "./dropdown";
import { request } from "../pyodide";
import { createCamera, type CameraSettings } from "../camera";
const ThreeConstruction = lazy(() => import("./three-construction"));
type V = [number, number, number];
type Config = Record<string, V>;
interface Mobility {
  first_order: number;
  second_order: string;
  residual: number;
  tangents: number[][][];
}
interface Cell {
  orbits: Record<string, V[]>;
  dimension: number;
  closed: boolean;
  configurations: Config[];
  witness: Config;
  certificate: unknown;
}
interface Preview {
  configuration: Config;
  grab: V;
  target_error: number;
  objects: Record<string, number>;
  edges: Record<string, number>;
  points: Record<string, number>;
  joints: {
    id: string;
    kind: string;
    a: V;
    b: V | null;
    error: number;
    severity: number;
  }[];
}
const previewColor = (severity = 0) =>
  `color-mix(in srgb, var(--cad-rod-drag-stroke) ${(1 - Math.max(0, Math.min(1, severity))) * 100}%, var(--danger))`;
export interface SceneData {
  revision: number;
  dimension: number;
  objects: {
    id: string;
    kind: string;
    fixed: boolean;
    points: string[];
    point_labels?: Record<string, string>;
    source_span?: [number, number, number, number];
  }[];
  constraints: {
    id: string;
    kind: string;
    a: string;
    b: string | null;
    source_span?: [number, number, number, number];
  }[];
  configuration: Config;
  mobility: Mobility;
  motion: { status: string; reason: string; complete: boolean; cells: Cell[] };
}
const add = (a: V, b: V): V => a.map((x, i) => x + b[i]) as V;
const sub = (a: V, b: V): V => a.map((x, i) => x - b[i]) as V;
const mul = (a: V, n: number): V => a.map((x) => x * n) as V;
const dot = (a: V, b: V) => a.reduce((s, x, i) => s + x * b[i], 0);
function ringPoints(cfg: Config, id: string, count = 64): V[] {
  const c = cfg[`${id}:origin`],
    x = sub(cfg[`${id}:x`], c),
    y = sub(cfg[`${id}:y`], c);
  return Array.from({ length: count }, (_, i) =>
    add(
      c,
      add(
        mul(x, Math.cos((i * 2 * Math.PI) / count)),
        mul(y, Math.sin((i * 2 * Math.PI) / count)),
      ),
    ),
  );
}
function ringPath(
  cfg: Config,
  id: string,
  projectPath: (points: V[], closed?: boolean) => string,
) {
  return projectPath(ringPoints(cfg, id), true);
}
export function Viewer({
  motionToolbar,
  scene,
  error,
  highlightElementId,
  onHoverElement,
}: {
  motionToolbar?: HTMLElement | null;
  scene: SceneData | null;
  error?: string | null;
  highlightElementId?: string | string[] | null;
  onHoverElement?: (id: string | string[] | null) => void;
}) {
  const highlightIds = useMemo(() => {
    if (!highlightElementId) return new Set<string>();
    if (Array.isArray(highlightElementId)) return new Set(highlightElementId);
    return new Set([highlightElementId]);
  }, [highlightElementId]);
  const [explorationEpoch, setExplorationEpoch] = useState(0);
  const [playbackInterrupt, setPlaybackInterrupt] = useState(0);
  const [wanderCommand, setWanderCommand] = useState(0);
  const [wanderState, setWanderState] = useState("idle");
  const [fitted, setFitted] = useState<{ center: V; extent: number } | null>(
    null,
  );
  const [roadmap, setRoadmap] = useState<Roadmap | null>(null);
  const [playback, setPlayback] = useState<Config | null>(null);
  const [live, setLive] = useState<Config | null>(null);
  const [mobility, setMobility] = useState<Mobility | null>(null);
  const [size, setSize] = useState([600, 400]);
  const [pan, setPan] = useState([0, 0]);
  const [zoom, setZoom] = useState(1);
  const [camera, setCamera] = useState([0, 0]);
  const [perspective, setPerspective] = useState(false);
  const [view, setView] = useState("3D");
  const [renderer, setRenderer] = useState("svg");
  const [orbits, setOrbits] = useState(false);
  const [tangents, setTangents] = useState(false);
  const [ghost, setGhost] = useState<Preview | null>(null);
  const interaction = useRef(0);
  const [reassembling, setReassembling] = useState(false);
  const [localMotion, setLocalMotion] = useState<SceneData["motion"] | null>(
    null,
  );
  const [problem, setProblem] = useState("");
  const [selected, setSelected] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);
  const revision = useRef(0);
  const busy = useRef(false);
  const queued = useRef<{
    keys: string[];
    targets: V[];
    generation: number;
    sceneRevision: number;
    interaction: number;
    weights: number[];
    kind: "drag" | "reassemble";
  } | null>(null);
  const drag = useRef<{
    keys: string[];
    origin: V;
    points: V[];
    screen: number[];
    pan: number[];
    camera: number[];
    rotate: boolean;
    reassemble: boolean;
    weights: number[];
    targets: V[];
  } | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize([entry.contentRect.width, entry.contentRect.height]),
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    revision.current++;
    queued.current = null;
    drag.current = null;
    setRoadmap(null);
    setFitted(null);
    setPlayback(null);
    setWanderState("idle");
    setLive(null);
    setMobility(null);
    setGhost(null);
    setLocalMotion(null);
    setReassembling(false);
    setProblem("");
    setSelected(-1);
    setPan([0, 0]);
    setZoom(1);
    setCamera(scene?.dimension === 3 ? [0.6, 0.4] : [0, 0]);
    setView(scene?.dimension === 3 ? "3D" : "XY");
    if (scene && scene.dimension !== 3) setPerspective(false);
  }, [scene]);
  useEffect(() => {
    const switchBackend = () => { drag.current = null; queued.current = null; interaction.current++; setGhost(null); void request({op:"sync_drag"}).catch(error=>setProblem(String(error))); };
    window.addEventListener("linklab-drag-backend-change",switchBackend);
    return ()=>window.removeEventListener("linklab-drag-backend-change",switchBackend);
  }, []);
  useEffect(() => subscribePreview(({preview,tag}) => {
    const current=drag.current;
    if (current && tag.generation === revision.current && tag.interaction === interaction.current) {
      const grab=current.targets.reduce((sum,point,i)=>add(sum,mul(point,current.weights[i])),[0,0,0] as V);
      setGhost({...preview,grab} as Preview);
    }
  }), []);
  const configuration = playback ?? live ?? scene?.configuration ?? {};
  const analysis = mobility ?? scene?.mobility;
  const initial =
    scene?.objects.flatMap((o) =>
      o.kind === "ring"
        ? ringPoints(scene.configuration, o.id, 32)
        : o.points.map((n) => scene.configuration[`${o.id}:${n}`]),
    ) ?? [];
  const center: V =
    fitted?.center ??
    (initial.length
      ? ([0, 1, 2].map(
          (i) => initial.reduce((s, p) => s + p[i], 0) / initial.length,
        ) as V)
      : [0, 0, 0]);
  const extent =
    fitted?.extent ??
    Math.max(1, ...initial.map((p) => Math.hypot(...sub(p, center))));
  const cameraSettings: CameraSettings = {
    center,
    extent,
    size,
    pan,
    zoom,
    angles: camera,
    perspective: perspective && scene?.dimension === 3,
    dimension: scene?.dimension ?? 2,
  };
  const useThree =
    scene?.dimension === 3 && view === "3D" && renderer === "three";
  const {
    ray,
    scale,
    project,
    visible,
    clipSegment,
    segment,
    projectPath,
    unproject,
    materialFraction,
  } = createCamera(cameraSettings);
  async function flush() {
    if (busy.current || !queued.current) return;
    busy.current = true;
    while (queued.current) {
      const job = queued.current;
      queued.current = null;
      try {
        const data = await request<{
          configuration: Config;
          mobility: Mobility;
          motion?: SceneData["motion"];
          preview?: Preview;
        }>({
          op: job.kind,
          preview_tag: {revision:job.sceneRevision,generation:job.generation,interaction:job.interaction},
          revision: job.sceneRevision,
          keys: job.keys,
          targets: job.targets,
          weights: job.weights,
        });
        if (job.generation === revision.current) {
          setLive(data.configuration);
          setMobility(data.mobility);
          if (
            data.preview &&
            drag.current &&
            job.interaction === interaction.current
          )
            setGhost(data.preview);
          if (data.motion) setLocalMotion(data.motion);
          if (job.kind === "reassemble") {
            setRoadmap(null);
            setExplorationEpoch((n) => n + 1);
            setGhost(null);
            setReassembling(false);
          }
        }
      } catch (err) {
        if (job.generation === revision.current) {
          setProblem(String(err));
          if (job.kind === "reassemble") {
            setGhost(null);
            setReassembling(false);
          }
        }
      }
    }
    busy.current = false;
    if (!drag.current) void request({op: "sync_drag"}).catch((error) => setProblem(String(error)));
  }
  async function start(
    e: PointerEvent,
    keys: string[],
    edge?: [string, string],
    ringGrab = false,
  ) {
    if (e.button !== 0 || reassembling) return;
    if (scene?.dimension !== 3 && e.shiftKey) return;
    // Shift pans over geometry as well as the background. Alt only acts on
    // movable objects; ordinary object dragging keeps its existing behavior.
    if (scene?.dimension === 3 && e.shiftKey) {
      keys = [];
      edge = undefined;
      ringGrab = false;
    }
    if (!keys.length && e.altKey && !e.shiftKey) return;
    if (
      keys.length &&
      scene?.objects.some(
        (o) =>
          o.fixed &&
          keys.every((k) => o.points.some((n) => `${o.id}:${n}` === k)),
      )
    )
      return;
    interaction.current++;
    e.stopPropagation();
    const capture = e.currentTarget as Element;
    capture.setPointerCapture(e.pointerId);
    if (playback && keys.length) {
      setPlaybackInterrupt((n) => n + 1);
      try {
        const result = await request<{
          configuration: Config;
          mobility: Mobility;
        }>({ op: "adopt", revision: scene?.revision, configuration: playback });
        setLive(result.configuration);
        setMobility(result.mobility);
        setPlayback(null);
      } catch (err) {
        setProblem(String(err));
        return;
      }
      if (!capture.hasPointerCapture(e.pointerId)) return;
    }
    const rect = ref.current!.getBoundingClientRect();
    const screen = [e.clientX - rect.left, e.clientY - rect.top];
    const points = keys.map((k) => configuration[k]);
    let anchor = points.length
      ? mul(points.reduce(add, [0, 0, 0]), 1 / points.length)
      : center;
    const weights: number[] = keys.map(() => (keys.length === 1 ? 1 : 0));
    if (ringGrab) {
      const id = keys[0].slice(0, keys[0].lastIndexOf(":"));
      const c = configuration[`${id}:origin`],
        x = sub(configuration[`${id}:x`], c),
        y = sub(configuration[`${id}:y`], c);
      const at = (angle: number) =>
        add(c, add(mul(x, Math.cos(angle)), mul(y, Math.sin(angle))));
      const distance = (angle: number) => {
        if (!visible(at(angle))) return Infinity;
        const p = project(at(angle));
        return (p[0] - screen[0]) ** 2 + (p[1] - screen[1]) ** 2;
      };
      let angle = 0;
      for (let i = 0; i < 64; i++)
        if (distance((i * 2 * Math.PI) / 64) < distance(angle))
          angle = (i * 2 * Math.PI) / 64;
      let lo = angle - (2 * Math.PI) / 64,
        hi = angle + (2 * Math.PI) / 64;
      for (let i = 0; i < 18; i++) {
        const a = lo + (hi - lo) / 3,
          b = hi - (hi - lo) / 3;
        if (distance(a) < distance(b)) hi = b;
        else lo = a;
      }
      angle = (lo + hi) / 2;
      weights[keys.indexOf(`${id}:origin`)] =
        1 - Math.cos(angle) - Math.sin(angle);
      weights[keys.indexOf(`${id}:x`)] = Math.cos(angle);
      weights[keys.indexOf(`${id}:y`)] = Math.sin(angle);
      anchor = at(angle);
    }
    if (edge) {
      const a = configuration[edge[0]],
        b = configuration[edge[1]];
      const clipped = clipSegment(a, b);
      if (!clipped) return;
      const p = project(clipped[0]),
        q = project(clipped[1]),
        dx = q[0] - p[0],
        dy = q[1] - p[1];
      const screenFraction = Math.max(
        0,
        Math.min(
          1,
          ((screen[0] - p[0]) * dx + (screen[1] - p[1]) * dy) /
            (dx * dx + dy * dy || 1),
        ),
      );
      anchor = add(
        clipped[0],
        mul(
          sub(clipped[1], clipped[0]),
          materialFraction(clipped[0], clipped[1], screenFraction),
        ),
      );
      const delta = sub(b, a);
      const t = Math.max(
        0,
        Math.min(1, dot(sub(anchor, a), delta) / dot(delta, delta)),
      );
      weights[keys.indexOf(edge[0])] = 1 - t;
      weights[keys.indexOf(edge[1])] = t;
    }
    setProblem("");
    drag.current = {
      keys,
      points,
      origin: anchor,
      screen,
      pan: [...pan],
      camera: [...camera],
      rotate: scene?.dimension === 3 && !e.shiftKey,
      reassemble: e.altKey,
      targets: points,
      weights,
    };
  }
  function move(e: PointerEvent) {
    const d = drag.current;
    if (!d) return;
    const rect = ref.current!.getBoundingClientRect();
    const screen = [e.clientX - rect.left, e.clientY - rect.top];
    if (!d.keys.length) {
      if (d.rotate) {
        setView("3D");
        setCamera([
          d.camera[0] - (screen[0] - d.screen[0]) * 0.008,
          Math.max(
            -1.5,
            Math.min(1.5, d.camera[1] + (screen[1] - d.screen[1]) * 0.008),
          ),
        ]);
      } else
        setPan([
          d.pan[0] + screen[0] - d.screen[0],
          d.pan[1] + screen[1] - d.screen[1],
        ]);
      return;
    }
    const target = unproject(screen, d.origin);
    const beginning = unproject(d.screen, d.origin);
    if (!target || !beginning) {
      setProblem("The drag plane is edge-on; select another view.");
      return;
    }
    const delta = sub(target, beginning);
    const targets = d.points.map((p) => add(p, delta));
    d.targets = targets;
    setGhost((previous) =>
      previous
        ? { ...previous, grab: add(d.origin, delta) }
        : {
            configuration,
            grab: add(d.origin, delta),
            target_error: 0,
            objects: {},
            edges: {},
            points: {},
            joints: [],
          },
    );
    queued.current = {
      keys: d.keys,
      targets,
      kind: "drag",
      weights: d.weights,
      sceneRevision: scene!.revision,
      interaction: interaction.current,
      generation: revision.current,
    };
    void flush();
  }
  function end(e: PointerEvent) {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    interaction.current++;
    if (
      e.type === "pointerup" &&
      d.keys.length &&
      d.reassemble &&
      scene &&
      scene.motion.status !== "certified"
    ) {
      setReassembling(true);
      queued.current = {
        kind: "reassemble",
        keys: d.keys,
        targets: d.targets,
        generation: revision.current,
        sceneRevision: scene.revision,
        interaction: interaction.current,
        weights: d.weights,
      };
      void flush();
    } else setGhost(null);
  }
  async function select(index: number) {
    setRoadmap(null);
    setExplorationEpoch((n) => n + 1);
    drag.current = null;
    setGhost(null);
    setReassembling(false);
    revision.current++;
    queued.current = null;
    const generation = revision.current;
    try {
      const result = await request<SceneData>({
        op: index < 0 ? "reset" : "select",
        revision: scene?.revision,
        index,
      });
      if (generation === revision.current) {
        setLive(result.configuration);
        setMobility(result.mobility);
        setSelected(index);
      }
    } catch (err) {
      setProblem(String(err));
    }
  }
  const pinned = new Set(
    scene?.constraints.filter((c) => c.kind === "pin").map((c) => c.a),
  );
  const elements: {
    id: string;
    kind: string;
    depth: number;
    layer: number;
    matchIds: string[];
    node: VNode;
  }[] = [];
  for (const obj of scene?.objects ?? []) {
    const keys = obj.points.map((n) => `${obj.id}:${n}`);
    const addElement = (
      id: string,
      kind: string,
      position: V,
      layer: number,
      node: VNode,
      matchIds: string[] = [id, obj.id],
    ) => elements.push({ id, kind, depth: dot(position, ray), layer, matchIds, node });
    if (obj.kind === "ring") {
      addElement(
        `${obj.id}:ring`,
        "ring",
        configuration[`${obj.id}:origin`],
        0,
        <g
          data-object={obj.id}
          data-ring={obj.id}
          onPointerDown={(e) => start(e, keys, undefined, true)}
          style={{ cursor: obj.fixed ? "default" : "grab" }}
        >
          <path
            d={ringPath(configuration, obj.id, projectPath)}
            fill="none"
            stroke={
              obj.fixed ? "var(--cad-ground-stroke)" : "var(--cad-rod-stroke)"
            }
            stroke-width="13"
          />
          <path
            d={ringPath(configuration, obj.id, projectPath)}
            fill="none"
            stroke="var(--cad-bg)"
            stroke-width="10"
            pointer-events="none"
          />
          <path
            d={ringPath(configuration, obj.id, projectPath)}
            fill="none"
            stroke={
              obj.fixed ? "var(--cad-ground-fill)" : "var(--cad-rod-fill)"
            }
            stroke-width="10"
            pointer-events="none"
          />
        </g>,
        [obj.id, `${obj.id}:ring`],
      );
    } else {
      keys.forEach((a, i) =>
        keys.slice(i + 1).forEach((b) => {
          const clipped = clipSegment(configuration[a], configuration[b]);
          if (!clipped) return;
          const p = project(clipped[0]),
            q = project(clipped[1]);
          addElement(
            `${a}|${b}`,
            "rod",
            mul(add(clipped[0], clipped[1]), 0.5),
            0,
            <g
              data-object={obj.id}
              onPointerDown={(e) => start(e, keys, [a, b])}
              style={{ cursor: obj.fixed ? "default" : "grab" }}
            >
              <line
                x1={p[0]}
                y1={p[1]}
                x2={q[0]}
                y2={q[1]}
                stroke={
                  obj.fixed
                    ? "var(--cad-ground-stroke)"
                    : "var(--cad-rod-stroke)"
                }
                stroke-width="13"
                stroke-linecap="round"
              />
              <line
                x1={p[0]}
                y1={p[1]}
                x2={q[0]}
                y2={q[1]}
                stroke="var(--cad-bg)"
                stroke-width="10"
                stroke-linecap="round"
                pointer-events="none"
              />
              <line
                x1={p[0]}
                y1={p[1]}
                x2={q[0]}
                y2={q[1]}
                stroke={
                  obj.fixed ? "var(--cad-ground-fill)" : "var(--cad-rod-fill)"
                }
                stroke-width="10"
                stroke-linecap="round"
                pointer-events="none"
              />
            </g>,
            [obj.id, `${a}|${b}`],
          );
        }),
      );
    }
    for (const key of keys.filter(
      (key) =>
        obj.kind !== "ring" ||
        scene?.constraints.some((c) => c.a === key || c.b === key),
    )) {
      if (!visible(configuration[key])) continue;
      const [x, y] = project(configuration[key]);
    const relatedConstraints =
      scene?.constraints.filter((c) => c.a === key || c.b === key) ?? [];
    const relatedConstraintIds = relatedConstraints.map((c) => c.id);
      addElement(
        key,
        "joint",
        configuration[key],
        1,
        <g
          data-point={key}
          data-constraints={relatedConstraintIds.join(" ")}
          onPointerDown={(e) => start(e, [key])}
          style={{ cursor: "grab" }}
        >
          <circle
            cx={x}
            cy={y}
            r="8"
            fill="var(--cad-bg)"
            stroke={
              pinned.has(key) || obj.fixed
                ? "var(--cad-ground-stroke)"
                : "var(--cad-joint-ring)"
            }
            stroke-width="1.5"
          />
          <circle
            cx={x}
            cy={y}
            r="2.5"
            fill="var(--cad-joint-pin)"
            pointer-events="none"
          />
        </g>,
        [...relatedConstraintIds, obj.id, key],
      );
    }
    const label =
      obj.kind === "ring"
        ? configuration[`${obj.id}:x`]
        : mul(
            keys.map((key) => configuration[key]).reduce(add, [0, 0, 0]),
            1 / keys.length,
          );
    const [x, y] = project(label);
    if (!visible(label)) continue;
    addElement(
      `${obj.id}:label`,
      "label",
      label,
      2,
      <text
        x={x + 10}
        y={y - 12}
        fill="var(--cad-badge-fg)"
        font-size="11"
        pointer-events="none"
      >
        {obj.id}
      </text>,
    );
  }
  elements.sort(
    (a, b) => {
      const aActive = a.matchIds.some((id) => highlightIds.has(id));
      const bActive = b.matchIds.some((id) => highlightIds.has(id));
      if (aActive !== bActive) return aActive ? 1 : -1;
      return a.depth - b.depth || a.layer - b.layer;
    },
  );
  const roadmapPaths = useMemo(
    () =>
      orbits &&
      roadmap?.edges.map((edge) =>
        scene?.objects
          .filter((o) => !o.fixed)
          .map((obj) => {
            const points = edge.path.map((cfg) =>
              obj.kind === "ring"
                ? cfg[`${obj.id}:origin`]
                : mul(
                    obj.points
                      .map((n) => cfg[`${obj.id}:${n}`])
                      .reduce(add, [0, 0, 0]),
                    1 / obj.points.length,
                  ),
            );
            return (
              <path
                key={`${edge.id}-${obj.id}`}
                d={projectPath(points)}
                fill="none"
                stroke="var(--cad-rod-stroke)"
                stroke-width="1"
                opacity=".35"
                pointer-events="none"
              />
            );
          }),
      ),
    [orbits, roadmap, scene, pan, zoom, camera, size, fitted, perspective],
  );
  return (
    <div
      class="viewer"
      ref={ref}
      style={{
        position: "relative",
        height: "100%",
        minHeight: 260,
        overflow: "hidden",
        background: "var(--cad-bg)",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 10,
          zIndex: 2,
          fontSize: 11,
          maxWidth: "45%",
          background: "var(--bg-raised)",
          padding: 8,
          border: "1px solid var(--line-color)",
          borderRadius: 5,
        }}
      >
        <strong>{scene?.motion.status ?? "No scene"}</strong>
        {reassembling && <div role="status">Reassembling near the ghost…</div>}
        {analysis && (
          <div>
            {scene?.dimension}D scene · 1st order: {analysis.first_order} · 2nd
            order: {analysis.second_order}
            <br />
            Residual: {analysis.residual.toExponential(2)}
          </div>
        )}
        {scene && (
          <details>
            <summary>Analysis</summary>
            {scene.motion.reason}
            <br />
            {scene.motion.complete
              ? "Global decomposition complete"
              : "Global completeness not established"}
          </details>
        )}
        {scene?.motion.status === "certified" &&
          scene.motion.cells.length > 1 && (
            <label>
              Component / chart{" "}
              <Dropdown
                label="Component or chart"
                value={String(selected)}
                onChange={(v) => void select(Number(v))}
                options={[
                  { value: "-1", label: "Current pose", disabled: true },
                  ...scene.motion.cells.map((c, i) => ({
                    value: String(i),
                    label: `${i + 1}: ${c.dimension}D ${c.closed ? "closed" : c.dimension === 0 ? "isolated" : "open"}`,
                  })),
                ]}
              />
            </label>
          )}
      </div>
      <div
        style={{
          position: "absolute",
          top: 10,
          right: 10,
          zIndex: 2,
          display: "flex",
          gap: 4,
          flexWrap: "wrap",
          maxWidth: "50%",
        }}
      >
        {(["XY", "XZ", "YZ", "3D"] as const).map((view) => (
          <button
            class="btn"
            onClick={() => {
              setView(view);
              if (view !== "3D") setPerspective(false);
              setCamera(
                view === "XY"
                  ? [0, 0]
                  : view === "XZ"
                    ? [0, Math.PI / 2]
                    : view === "YZ"
                      ? [Math.PI / 2, 0]
                      : [0.6, 0.4],
              );
            }}
          >
            {view}
          </button>
        ))}
        <button
          class="btn"
          onClick={() => {
            setPan([0, 0]);
            setZoom(1);
          }}
        >
          1x
        </button>
        <button
          class="btn"
          disabled={!roadmap}
          onClick={() => {
            if (!roadmap || !scene) return;
            const positions = roadmap.nodes.flatMap((n) =>
              scene.objects.flatMap((o) =>
                o.kind === "ring"
                  ? ringPoints(n.configuration, o.id, 16)
                  : o.points.map((p) => n.configuration[`${o.id}:${p}`]),
              ),
            );
            const low: V = [Infinity, Infinity, Infinity],
              high: V = [-Infinity, -Infinity, -Infinity];
            for (const p of positions)
              for (let i = 0; i < 3; i++) {
                low[i] = Math.min(low[i], p[i]);
                high[i] = Math.max(high[i], p[i]);
              }
            const c = mul(add(low, high), 0.5);
            setFitted({
              center: c,
              extent: positions.reduce(
                (r, p) => Math.max(r, Math.hypot(...sub(p, c))),
                1,
              ),
            });
            setPan([0, 0]);
            setZoom(1);
          }}
        >
          Fit motion
        </button>
        <button class="btn" disabled={!scene} onClick={() => void select(-1)}>
          Reset
        </button>
        {scene?.dimension === 3 && (
          <button
            class={`btn ${perspective ? "btn--active" : ""}`}
            aria-label="Perspective view"
            aria-pressed={perspective}
            onClick={() => setPerspective((p) => !p)}
          >
            {perspective ? "Perspective" : "Orthographic"}
          </button>
        )}
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 10,
          left: 10,
          zIndex: 2,
          display: "flex",
          gap: 6,
        }}
      >
        <button
          class={`btn ${orbits ? "btn--active" : ""}`}
          aria-pressed={orbits}
          onClick={() => setOrbits(!orbits)}
        >
          ⌖ Orbits
        </button>
        <button
          class={`btn ${tangents ? "btn--active" : ""}`}
          aria-pressed={tangents}
          onClick={() => setTangents(!tangents)}
        >
          ∂² Tangents
        </button>
        {scene?.dimension === 3 && view === "3D" && (
          <Dropdown
            label="3D renderer"
            value={renderer}
            onChange={setRenderer}
            options={[
              { value: "svg", label: "SVG" },
              { value: "three", label: "Three.js" },
            ]}
          />
        )}
        <span style={{ color: "var(--fg-muted)", fontSize: 11 }}>
          {scene?.dimension === 3
            ? "Drag background to orbit · Shift-drag to pan · Scroll to zoom"
            : "Drag background to pan · Scroll to zoom"}
          {scene?.motion.status !== "certified" &&
            " · Alt-drag object to reassemble"}
        </span>
      </div>
      {(error || problem) && (
        <pre
          role="alert"
          style={{
            position: "absolute",
            bottom: 45,
            left: 10,
            color: "var(--danger)",
            zIndex: 3,
            whiteSpace: "pre-wrap",
            maxWidth: "90%",
          }}
        >
          {error || problem}
        </pre>
      )}
      {scene && motionToolbar && createPortal(
        <MotionPopover state={wanderState} disabled={!scene} onToggle={() => setWanderCommand((n) => n + 1)}>
        <ExplorationPanel
          key={`${scene.revision}-${explorationEpoch}`}
          revision={scene.revision}
          pose={configuration}
          onGraph={setRoadmap}
          onPose={setPlayback}
          interrupt={playbackInterrupt}
          wanderCommand={wanderCommand}
          onWanderState={setWanderState}
          onAdopt={(pose) => {
            setLive(pose);
            setPlayback(null);
          }}
        />
        </MotionPopover>, motionToolbar)}
      <svg
        data-cad-camera={camera.join(",")}
        data-projection={
          perspective && scene?.dimension === 3 ? "perspective" : "orthographic"
        }
        data-cad-pan={pan.join(",")}
        width="100%"
        height="100%"
        style={{
          touchAction: "none",
          userSelect: "none",
          pointerEvents: useThree ? "none" : undefined,
        }}
        onPointerDown={(e) => start(e, [])}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        onLostPointerCapture={end}
        onWheel={(e) => {
          e.preventDefault();
          setZoom((z) =>
            Math.max(0.1, Math.min(20, z * (e.deltaY < 0 ? 1.1 : 1 / 1.1))),
          );
        }}
      >
        <ConstructionGrid
          ray={ray}
          project={project}
          scale={scale}
          extent={extent}
          perspective={perspective && scene?.dimension === 3}
          segment={segment}
        />
        {ghost && (
          <g data-drag-ghost="construction" pointer-events="none" opacity=".24">
            {scene?.objects.map((obj) => {
              const keys = obj.points.map((n) => `${obj.id}:${n}`);
              return (
                <g key={obj.id} data-ghost-object={obj.id}>
                  {obj.kind === "ring" ? (
                    <path
                      data-ghost-ring={obj.id}
                      d={ringPath(ghost.configuration, obj.id, projectPath)}
                      fill="none"
                      stroke={previewColor(ghost.objects[obj.id])}
                      stroke-width="12"
                    />
                  ) : (
                    keys.flatMap((a, i) =>
                      keys.slice(i + 1).map((b) => {
                        const clipped = segment(
                          ghost.configuration[a],
                          ghost.configuration[b],
                        );
                        if (!clipped) return null;
                        const [p, q] = clipped;
                        const severity = ghost.edges[`${a}|${b}`] ?? 0;
                        return (
                          <g
                            key={`${a}|${b}`}
                            data-ghost-edge={`${a}|${b}`}
                            data-severity={severity}
                          >
                            <rect
                              x="-6"
                              y="-6"
                              width={Math.hypot(q[0] - p[0], q[1] - p[1]) + 12}
                              height="12"
                              rx="6"
                              transform={`translate(${p[0]} ${p[1]}) rotate(${(Math.atan2(q[1] - p[1], q[0] - p[0]) * 180) / Math.PI})`}
                              fill={previewColor(severity)}
                              stroke="none"
                            />
                          </g>
                        );
                      }),
                    )
                  )}
                  {keys
                    .filter(
                      (key) =>
                        obj.kind !== "ring" ||
                        scene?.constraints.some(
                          (c) => c.a === key || c.b === key,
                        ),
                    )
                    .map((key) => {
                      if (!visible(ghost.configuration[key])) return null;
                      const [x, y] = project(ghost.configuration[key]);
                      return (
                        <circle
                          key={key}
                          data-ghost-point={key}
                          data-severity={ghost.points[key] ?? 0}
                          cx={x}
                          cy={y}
                          r="3"
                          fill={previewColor(ghost.points[key])}
                          stroke="none"
                        />
                      );
                    })}
                </g>
              );
            })}
            {ghost.joints
              .filter((j) => j.b && j.error > 1e-7)
              .map((j) => {
                const clipped = segment(j.a, j.b!);
                if (!clipped) return null;
                const [a, b] = clipped;
                return (
                  <line
                    key={j.id}
                    data-ghost-constraint={j.id}
                    data-severity={j.severity}
                    x1={a[0]}
                    y1={a[1]}
                    x2={b[0]}
                    y2={b[1]}
                    stroke={previewColor(j.severity)}
                    stroke-width="1"
                    stroke-dasharray="3 3"
                  >
                    <title>
                      {j.kind}: {j.error.toPrecision(3)} relative error
                    </title>
                  </line>
                );
              })}
            {visible(ghost.grab) && (
              <circle
                data-grab-target="true"
                cx={project(ghost.grab)[0]}
                cy={project(ghost.grab)[1]}
                r="3"
                fill="var(--cad-rod-drag-stroke)"
              />
            )}
          </g>
        )}
        {orbits &&
          scene &&
          !roadmap &&
          (localMotion ?? scene?.motion)?.cells.map((cell, ci) =>
            scene.objects.map((obj) => {
              const centroids = cell.orbits[obj.id] ?? [];
              if (obj.fixed || !centroids.length) return null;
              if (cell.dimension === 0 || cell.dimension > 1)
                return centroids.map((p) => {
                  if (!visible(p)) return null;
                  const [x, y] = project(p);
                  return (
                    <circle
                      key={`${ci}-${obj.id}-${x}-${y}`}
                      cx={x}
                      cy={y}
                      r="3"
                      fill="var(--cad-joint-pin)"
                    />
                  );
                });
              return (
                <path
                  key={`${ci}-${obj.id}`}
                  d={projectPath(centroids, cell.closed)}
                  fill="none"
                  stroke="var(--cad-rod-stroke)"
                  stroke-dasharray="4 3"
                  opacity=".55"
                  pointer-events="none"
                />
              );
            }),
          )}
        {roadmapPaths}
        {!useThree &&
          elements.map((item) => {
            const isActive = item.matchIds.some((id) => highlightIds.has(id));
            return (
              <g
                key={item.id}
                data-scene-element={item.id}
                data-element-kind={item.kind}
                data-depth={item.depth}
                class={isActive ? "is-active" : undefined}
                onMouseEnter={() => {
                  onHoverElement?.(item.matchIds[0] ?? null);
                }}
                onMouseLeave={() => onHoverElement?.(null)}
              >
                {item.node}
              </g>
            );
          })}
        {tangents &&
          analysis?.tangents.map((tangent, ti) =>
            Object.keys(configuration).map((key, i) => {
              const a = configuration[key],
                v = tangent[i];
              if (!v) return null;
              const b = add(a, mul([v[0], v[1], v[2] ?? 0], extent * 0.3));
              const clipped = segment(a, b);
              if (!clipped) return null;
              const [p, q] = clipped;
              return (
                <line
                  key={`${ti}-${key}`}
                  x1={p[0]}
                  y1={p[1]}
                  x2={q[0]}
                  y2={q[1]}
                  stroke={
                    analysis.second_order === "locked"
                      ? "var(--danger)"
                      : "var(--ok)"
                  }
                  stroke-width="1.5"
                  pointer-events="none"
                />
              );
            }),
          )}
      </svg>
      {useThree && scene && (
        <Suspense
          fallback={
            <div class="renderer-loading" role="status">
              Loading 3D renderer…
            </div>
          }
        >
          <ThreeConstruction
            scene={scene}
            configuration={configuration}
            camera={cameraSettings}
            highlightElementId={highlightElementId}
            onHoverElement={onHoverElement}
            onStart={(event, pick) => {
              const fixed = scene.objects.some(
                (object) =>
                  object.fixed &&
                  pick.keys.length &&
                  pick.keys.every((key) =>
                    object.points.some(
                      (name) => `${object.id}:${name}` === key,
                    ),
                  ),
              );
              void start(
                event,
                fixed ? [] : pick.keys,
                fixed ? undefined : pick.edge,
                !fixed && pick.ring,
              );
            }}
            onMove={move}
            onEnd={end}
            onZoom={(delta) =>
              setZoom((z) =>
                Math.max(0.1, Math.min(20, z * (delta < 0 ? 1.1 : 1 / 1.1))),
              )
            }
            onError={(message) => {
              setRenderer("svg");
              setProblem(message);
            }}
          />
        </Suspense>
      )}
      <svg class="cad-point-labels" width="100%" height="100%" aria-label="Point labels">
        {scene?.objects.flatMap((object) => Object.entries(object.point_labels ?? {}).map(([name, label]) => {
          const point = configuration[`${object.id}:${name}`];
          if (!point || !visible(point)) return null;
          const [x, y] = project(point);
          return <text key={`${object.id}:${name}:label`} data-point-label={label} x={x + 10} y={y - 10} class="cad-point-label" pointer-events="none">{label}</text>;
        }))}
      </svg>
    </div>
  );
}
