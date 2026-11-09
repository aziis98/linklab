import { useRef, useState } from "preact/hooks";
import { memo } from "preact/compat";
import type { Roadmap } from "./exploration-panel";

/** Orthographic view of Python's three PCA coordinates; camera stays in JS. */
export const RoadmapPreview = memo(function RoadmapPreview({
  graph,
  walk,
}: {
  graph: Roadmap;
  walk?: number[][];
}) {
  const [camera, setCamera] = useState({ yaw: 0.45, pitch: -0.3, zoom: 1 });
  const drag = useRef<{
    x: number;
    y: number;
    yaw: number;
    pitch: number;
  } | null>(null);
  function project(p: number[]) {
    const [x, y, z] = p;
    const a = Math.cos(camera.yaw),
      b = Math.sin(camera.yaw);
    const c = Math.cos(camera.pitch),
      d = Math.sin(camera.pitch);
    const horizontal = a * x + b * z,
      depth = -b * x + a * z;
    return [
      150 + 65 * camera.zoom * horizontal,
      100 - 65 * camera.zoom * (c * y - d * depth),
      d * y + c * depth,
    ];
  }
  const positions = graph.nodes.map((n) =>
    project(graph.layout3d?.[n.id] ?? [0, 0, 0]),
  );
  const highlighted = new Set(
    walk?.map(([a, b]) => `${Math.min(a, b)}:${Math.max(a, b)}`),
  );
  const reset = () => setCamera({ yaw: 0.45, pitch: -0.3, zoom: 1 });
  const zoom = (factor: number) =>
    setCamera((c) => ({
      ...c,
      zoom: Math.max(0.2, Math.min(8, c.zoom * factor)),
    }));
  return (
    <div class="roadmap-preview">
      <div class="exploration-controls">
        <small>3D configuration projection</small>
        <button class="btn" onClick={reset}>
          Reset graph view
        </button>
      </div>
      <svg
        viewBox="0 0 300 200"
        width="100%"
        height="200"
        aria-label="Explored configuration graph"
        role="img"
        tabindex={0}
        data-camera={`${camera.yaw},${camera.pitch},${camera.zoom}`}
        style={{
          touchAction: "none",
          cursor: drag.current ? "grabbing" : "grab",
        }}
        onPointerDown={(e) => {
          if (e.button !== 0) return;
          e.preventDefault();
          e.currentTarget.focus();
          e.currentTarget.setPointerCapture(e.pointerId);
          drag.current = {
            x: e.clientX,
            y: e.clientY,
            yaw: camera.yaw,
            pitch: camera.pitch,
          };
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const start = drag.current;
          setCamera((c) => ({
            ...c,
            yaw: start.yaw + (e.clientX - start.x) * 0.01,
            pitch: start.pitch + (e.clientY - start.y) * 0.01,
          }));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onLostPointerCapture={() => {
          drag.current = null;
        }}
        onWheel={(e) => {
          e.preventDefault();
          zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1);
        }}
        onKeyDown={(e) => {
          if (
            ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)
          ) {
            e.preventDefault();
            setCamera((c) => ({
              ...c,
              yaw:
                c.yaw +
                (e.key === "ArrowLeft"
                  ? -0.12
                  : e.key === "ArrowRight"
                    ? 0.12
                    : 0),
              pitch:
                c.pitch +
                (e.key === "ArrowUp"
                  ? -0.12
                  : e.key === "ArrowDown"
                    ? 0.12
                    : 0),
            }));
          } else if (e.key === "+" || e.key === "=") {
            e.preventDefault();
            zoom(1.1);
          } else if (e.key === "-") {
            e.preventDefault();
            zoom(1 / 1.1);
          } else if (e.key === "Home") {
            e.preventDefault();
            reset();
          }
        }}
      >
        <title>
          Roadmap in three principal coordinates. Drag or use arrow keys to
          orbit; scroll or use plus and minus to zoom.
        </title>
        {[0, 1, 2].map((axis) => {
          const v = [0, 0, 0];
          v[axis] = 1.25;
          const a = project([0, 0, 0]),
            b = project(v);
          return (
            <g key={axis} opacity=".6" pointer-events="none">
              <line
                x1={a[0]}
                y1={a[1]}
                x2={b[0]}
                y2={b[1]}
                stroke="var(--cad-axis)"
                stroke-dasharray="2 3"
              />
              <text x={b[0]} y={b[1]} font-size="8" fill="var(--fg-muted)">
                PC{axis + 1}
              </text>
            </g>
          );
        })}
        {graph.edges.map((edge) => {
          const a = positions[edge.a],
            b = positions[edge.b];
          const selected = highlighted.has(
            `${Math.min(edge.a, edge.b)}:${Math.max(edge.a, edge.b)}`,
          );
          return (
            <line
              key={edge.id}
              x1={a[0]}
              y1={a[1]}
              x2={b[0]}
              y2={b[1]}
              stroke="var(--cad-rod-stroke)"
              stroke-width={selected ? "2" : ".6"}
              opacity={selected ? ".9" : ".4"}
              pointer-events="none"
            />
          );
        })}
        {[...graph.nodes]
          .sort((a, b) => positions[a.id][2] - positions[b.id][2])
          .map((node) => {
            const [x, y, depth] = positions[node.id];
            const unresolved =
              node.singular || graph.unresolved_nodes?.includes(node.id);
            return (
              <circle
                key={node.id}
                cx={x}
                cy={y}
                r={unresolved ? "3" : "2"}
                opacity={Math.max(0.4, Math.min(1, 0.75 + depth * 0.15))}
                fill={unresolved ? "var(--cad-joint-pin)" : "var(--accent)"}
              >
                <title>
                  Configuration {node.id}
                  {unresolved ? " · unresolved or singular" : ""}
                </title>
              </circle>
            );
          })}
      </svg>
      <small>
        Drag to orbit · Scroll to zoom · Projection crossings are not graph
        junctions.
      </small>
    </div>
  );
});
