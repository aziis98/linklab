import { useEffect, useRef, useState } from "preact/hooks";
import { ConstructionGrid } from "./construction-grid";
import { Dropdown } from "./dropdown";
import { request } from "../pyodide";
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
  objects: { id: string; kind: string; fixed: boolean; points: string[] }[];
  constraints: { id: string; kind: string; a: string; b: string | null }[];
  configuration: Config;
  mobility: Mobility;
  motion: { status: string; reason: string; complete: boolean; cells: Cell[] };
}
const add = (a: V, b: V): V => a.map((x, i) => x + b[i]) as V;
const sub = (a: V, b: V): V => a.map((x, i) => x - b[i]) as V;
const mul = (a: V, n: number): V => a.map((x) => x * n) as V;
const dot = (a: V, b: V) => a.reduce((s, x, i) => s + x * b[i], 0);
export function Viewer({
  scene,
  error,
}: {
  scene: SceneData | null;
  error?: string | null;
}) {
  const [live, setLive] = useState<Config | null>(null);
  const [mobility, setMobility] = useState<Mobility | null>(null);
  const [size, setSize] = useState([600, 400]);
  const [pan, setPan] = useState([0, 0]);
  const [zoom, setZoom] = useState(1);
  const [camera, setCamera] = useState([0, 0]);
  const [plane, setPlane] = useState("view");
  const [orbits, setOrbits] = useState(false);
  const [tangents, setTangents] = useState(true);
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
  }, [scene]);
  const configuration = live ?? scene?.configuration ?? {};
  const analysis = mobility ?? scene?.mobility;
  const initial = Object.values(scene?.configuration ?? {});
  const center: V = initial.length
    ? ([0, 1, 2].map(
        (i) => initial.reduce((s, p) => s + p[i], 0) / initial.length,
      ) as V)
    : [0, 0, 0];
  const extent = Math.max(
    1,
    ...initial.map((p) => Math.hypot(...sub(p, center))),
  );
  const scale = (Math.min(size[0], size[1]) / (extent * 2.8)) * zoom;
  const [yaw, pitch] = camera;
  const right: V = [Math.cos(yaw), 0, -Math.sin(yaw)];
  const up: V = [
    -Math.sin(yaw) * Math.sin(pitch),
    Math.cos(pitch),
    -Math.cos(yaw) * Math.sin(pitch),
  ];
  const ray: V = [
    Math.sin(yaw) * Math.cos(pitch),
    Math.sin(pitch),
    Math.cos(yaw) * Math.cos(pitch),
  ];
  const project = (p: V) => [
    size[0] / 2 + pan[0] + scale * dot(sub(p, center), right),
    size[1] / 2 + pan[1] - scale * dot(sub(p, center), up),
  ];
  const svgPoint = (p: V) => project(p).join(",");
  const unproject = (screen: number[], anchor: V): V | null => {
    const base = add(
      center,
      add(
        mul(right, (screen[0] - size[0] / 2 - pan[0]) / scale),
        mul(up, -(screen[1] - size[1] / 2 - pan[1]) / scale),
      ),
    );
    const normal: V =
      scene?.dimension === 2 || plane === "xy"
        ? [0, 0, 1]
        : plane === "xz"
          ? [0, 1, 0]
          : plane === "yz"
            ? [1, 0, 0]
            : ray;
    const denominator = dot(ray, normal);
    return Math.abs(denominator) < 1e-6
      ? null
      : add(base, mul(ray, dot(sub(anchor, base), normal) / denominator));
  };
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
  }
  function start(e: PointerEvent, keys: string[], edge?: [string, string]) {
    if (e.button !== 0 || reassembling) return;
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
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    const rect = ref.current!.getBoundingClientRect();
    const screen = [e.clientX - rect.left, e.clientY - rect.top];
    const points = keys.map((k) => configuration[k]);
    let anchor = points.length
      ? mul(points.reduce(add, [0, 0, 0]), 1 / points.length)
      : center;
    const weights: number[] = keys.map(() => (keys.length === 1 ? 1 : 0));
    if (edge) {
      const a = configuration[edge[0]],
        b = configuration[edge[1]];
      const p = project(a),
        q = project(b),
        dx = q[0] - p[0],
        dy = q[1] - p[1];
      const t = Math.max(
        0,
        Math.min(
          1,
          ((screen[0] - p[0]) * dx + (screen[1] - p[1]) * dy) /
            (dx * dx + dy * dy || 1),
        ),
      );
      anchor = add(a, mul(sub(b, a), t));
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
      rotate: e.altKey,
      reassemble: e.shiftKey,
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
      if (d.rotate)
        setCamera([
          d.camera[0] + (screen[0] - d.screen[0]) * 0.008,
          Math.max(
            -1.5,
            Math.min(1.5, d.camera[1] + (screen[1] - d.screen[1]) * 0.008),
          ),
        ]);
      else
        setPan([
          d.pan[0] + screen[0] - d.screen[0],
          d.pan[1] + screen[1] - d.screen[1],
        ]);
      return;
    }
    const target = unproject(screen, d.origin);
    const beginning = unproject(d.screen, d.origin);
    if (!target || !beginning) {
      setProblem("Drag plane is edge-on; select another view or plane.");
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
      (d.reassemble || e.shiftKey) &&
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
  const ordered = [...(scene?.objects ?? [])].sort((a, b) => {
    const depth = (o: typeof a) =>
      o.points.reduce(
        (s, n) => s + dot(configuration[`${o.id}:${n}`], ray),
        0,
      ) / o.points.length;
    return depth(a) - depth(b);
  });
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
            onClick={() =>
              setCamera(
                view === "XY"
                  ? [0, 0]
                  : view === "XZ"
                    ? [0, Math.PI / 2]
                    : view === "YZ"
                      ? [Math.PI / 2, 0]
                      : [0.6, 0.4],
              )
            }
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
        <button class="btn" disabled={!scene} onClick={() => void select(-1)}>
          Reset
        </button>
        {scene?.dimension === 3 && (
          <Dropdown
            label="Drag plane"
            value={plane}
            onChange={setPlane}
            options={["view", "xy", "xz", "yz"].map((p) => ({
              value: p,
              label: p === "view" ? "View plane" : p.toUpperCase(),
            }))}
          />
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
        <span style={{ color: "var(--fg-muted)", fontSize: 11 }}>
          Drag to pan · Alt-drag to rotate · Scroll to zoom
          {scene?.motion.status !== "certified" &&
            " · Shift-drag to reassemble"}
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
      <svg
        width="100%"
        height="100%"
        style={{ touchAction: "none", userSelect: "none" }}
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
        />
        {ghost && (
          <g data-drag-ghost="construction" pointer-events="none" opacity=".24">
            {scene?.objects.map((obj) => {
              const keys = obj.points.map((n) => `${obj.id}:${n}`);
              return (
                <g key={obj.id} data-ghost-object={obj.id}>
                  {keys.flatMap((a, i) =>
                    keys.slice(i + 1).map((b) => {
                      const p = project(ghost.configuration[a]),
                        q = project(ghost.configuration[b]);
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
                  )}
                  {keys.map((key) => {
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
                const a = project(j.a),
                  b = project(j.b!);
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
            <circle
              data-grab-target="true"
              cx={project(ghost.grab)[0]}
              cy={project(ghost.grab)[1]}
              r="3"
              fill="var(--cad-rod-drag-stroke)"
            />
          </g>
        )}
        {orbits &&
          scene &&
          (localMotion ?? scene?.motion)?.cells.map((cell, ci) =>
            scene.objects.map((obj) => {
              const centroids = cell.orbits[obj.id] ?? [];
              if (obj.fixed || !centroids.length) return null;
              if (cell.dimension === 0 || cell.dimension > 1)
                return centroids.map((p) => {
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
                  d={`M ${centroids.map(svgPoint).join(" L ")}${cell.closed ? " Z" : ""}`}
                  fill="none"
                  stroke="var(--cad-rod-stroke)"
                  stroke-dasharray="4 3"
                  opacity=".55"
                  pointer-events="none"
                />
              );
            }),
          )}
        {ordered.map((obj) => {
          const keys = obj.points.map((n) => `${obj.id}:${n}`);
          return (
            <g key={obj.id}>
              {keys.flatMap((a, i) =>
                keys.slice(i + 1).map((b) => {
                  const p = project(configuration[a]),
                    q = project(configuration[b]);
                  return (
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
                          obj.fixed
                            ? "var(--cad-ground-fill)"
                            : "var(--cad-rod-fill)"
                        }
                        stroke-width="10"
                        stroke-linecap="round"
                        pointer-events="none"
                      />
                    </g>
                  );
                }),
              )}
              {keys.map((key) => {
                const [x, y] = project(configuration[key]);
                return (
                  <g
                    data-point={key}
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
                  </g>
                );
              })}
              <text
                x={
                  project(
                    mul(
                      keys.map((k) => configuration[k]).reduce(add, [0, 0, 0]),
                      1 / keys.length,
                    ),
                  )[0] + 10
                }
                y={
                  project(
                    mul(
                      keys.map((k) => configuration[k]).reduce(add, [0, 0, 0]),
                      1 / keys.length,
                    ),
                  )[1] - 12
                }
                fill="var(--cad-badge-fg)"
                font-size="11"
                pointer-events="none"
              >
                {obj.id}
              </text>
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
              const p = project(a),
                q = project(b);
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
    </div>
  );
}
