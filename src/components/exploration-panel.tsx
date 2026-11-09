import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { request } from "../pyodide";
import { Dropdown } from "./dropdown";
import { WanderControls } from "./wander-controls";
import { RoadmapPreview } from "./roadmap-preview";
type Config = Record<string, [number, number, number]>;
export interface Roadmap {
  job_id: number;
  delta?: boolean;
  node_cursor?: number;
  edge_cursor?: number;
  removed_edges?: number[];
  layout?: number[][];
  layout3d?: number[][];
  status: string;
  used: number;
  seconds: number;
  limit: number;
  pending: number;
  unresolved: number;
  unresolved_nodes?: number[];
  boundaries?: number;
  nodes: {
    id: number;
    configuration: Config;
    dimension: number;
    singular?: boolean;
  }[];
  edges: { id: number; a: number; b: number; path: Config[]; length: number }[];
}
export function ExplorationPanel({
  revision,
  interrupt,
  onAdopt,
  onGraph,
  onPose,
  pose,
  wanderCommand,
  onWanderState,
}: {
  revision: number;
  interrupt: number;
  onAdopt: (p: Config) => void;
  onGraph: (g: Roadmap | null) => void;
  onPose: (p: Config | null) => void;
  pose: Config;
  wanderCommand: number;
  onWanderState: (state: string) => void;
}) {
  const [graph, setGraph] = useState<Roadmap | null>(null),
    [running, setRunning] = useState(false),
    [error, setError] = useState("");
  const [spacing, setSpacing] = useState(".5"),
    [radius, setRadius] = useState(2),
    [seconds, setSeconds] = useState(30),
    [limit, setLimit] = useState(2000);
  const [turn, setTurn] = useState(15),
    [correction, setCorrection] = useState(0.25);
  const [showGraph, setShowGraph] = useState(false),
    [count, setCount] = useState(16),
    [seed, setSeed] = useState(0),
    [tour, setTour] = useState<{
      frames: Config[];
      duration: number;
      walk?: number[][];
    } | null>(null);
  const [playing, setPlaying] = useState(false),
    [frame, setFrame] = useState(0),
    [speed, setSpeed] = useState(3),
    [preparing, setPreparing] = useState(false);
  const [prepared, setPrepared] = useState({ done: 0, total: 1 });
  const [wanderActive, setWanderActive] = useState(false);
  const [wanderReset, setWanderReset] = useState(0);
  const panel = useRef<HTMLDetailsElement>(null);
  const lastWanderCommand = useRef(wanderCommand);
  useEffect(() => {
    if (wanderCommand !== lastWanderCommand.current && panel.current)
      panel.current.open = true;
    lastWanderCommand.current = wanderCommand;
  }, [wanderCommand]);
  useLayoutEffect(() => {
    setPlaying(false);
    setTour(null);
  }, [interrupt]);
  const graphRef = useRef<Roadmap | null>(null);
  const active = useRef(false),
    generation = useRef(0);
  useEffect(
    () => () => {
      active.current = false;
      generation.current++;
    },
    [revision],
  );
  function update(g: Roadmap) {
    if (g.delta && graphRef.current && g.job_id === graphRef.current.job_id) {
      const old = graphRef.current;
      g = {
        ...g,
        nodes: [...old.nodes, ...g.nodes],
        edges: [
          ...old.edges.filter((e) => !g.removed_edges?.includes(e.id)),
          ...g.edges,
        ],
      };
    }
    graphRef.current = g;
    setGraph(g);
    onGraph(g);
  }
  async function loop() {
    const gen = generation.current;
    active.current = true;
    setRunning(true);
    try {
      while (active.current && gen === generation.current) {
        const g = await request<Roadmap>({
          op: "explore_step",
          job_id: graphRef.current?.job_id,
          revision,
          node_cursor: graphRef.current?.node_cursor,
          edge_cursor: graphRef.current?.edge_cursor,
        });
        if (gen !== generation.current) return;
        update(g);
        if (g.status !== "running") break;
        await new Promise((r) => setTimeout(r, 0));
      }
    } catch (e) {
      setError(String(e));
    } finally {
      if (gen === generation.current) {
        active.current = false;
        setRunning(false);
      }
    }
  }
  async function pause() {
    active.current = false;
    const gen = generation.current;
    try {
      const g = await request<Roadmap>({
        op: "explore_pause",
        revision,
        job_id: graphRef.current?.job_id,
      });
      if (gen === generation.current) update(g);
    } catch (e) {
      if (gen === generation.current) setError(String(e));
    }
  }
  async function start() {
    setWanderReset((n) => n + 1);
    active.current = false;
    generation.current++;
    setTour(null);
    setPlaying(false);
    onPose(null);
    setError("");
    try {
      update(
        await request<Roadmap>({
          op: "explore_start",
          revision,
          settings: {
            spacing: Number(spacing),
            radius,
            seconds,
            limit,
            seed,
            turn_degrees: turn,
            correction_ratio: correction,
          },
        }),
      );
      void loop();
    } catch (e) {
      setError(String(e));
    }
  }
  async function build() {
    setWanderReset((n) => n + 1);
    active.current = false;
    setPreparing(true);
    setPrepared({ done: 0, total: 1 });
    setError("");
    setPlaying(false);
    try {
      const gen = generation.current;
      const t = await request<{
        frames: Config[];
        duration: number;
        graph: Roadmap;
      }>({
        op: "explore_tour_start",
        revision,
        job_id: graphRef.current?.job_id,
        count,
        seed,
      });
      if (gen !== generation.current) return;
      if (t.graph) update(t.graph);
      while (gen === generation.current) {
        const batch = await request<{
          frames: Config[];
          prepared: number;
          total: number;
          done: boolean;
        }>({
          op: "explore_tour_step",
          revision,
          job_id: graphRef.current?.job_id,
        });
        if (gen !== generation.current) return;
        t.frames.push(...batch.frames);
        setPrepared({ done: batch.prepared, total: batch.total });
        if (batch.done) break;
        await new Promise((r) => setTimeout(r, 0));
      }
      setTour(t);
      setFrame(0);
      onPose(t.frames[0]);
    } catch (e) {
      setError(String(e));
    } finally {
      setPreparing(false);
    }
  }
  useEffect(() => {
    if (!playing || !tour) return;
    let last = performance.now(),
      position = frame;
    let id = 0;
    function tick(now: number) {
      position =
        (position +
          (((now - last) / 1000) * speed * tour!.frames.length) /
            tour!.duration) %
        tour!.frames.length;
      last = now;
      const i = Math.floor(position);
      setFrame(i);
      onPose(tour!.frames[i]);
      id = requestAnimationFrame(tick);
    }
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [playing, tour, speed]);
  return (
    <details class="exploration-panel" ref={panel}>
      <summary>Exploration</summary>
      <div class="exploration-controls">
        <Dropdown
          label="Exploration quality"
          value={spacing}
          onChange={setSpacing}
          options={[
            { value: "1", label: "Coarse" },
            { value: ".5", label: "Medium" },
            { value: ".25", label: "Fine" },
          ]}
        />
        <button
          class="btn"
          disabled={running || preparing || wanderActive}
          onClick={start}
        >
          Explore
        </button>
        <button
          class="btn"
          disabled={!graph || preparing || wanderActive}
          onClick={() => (running ? void pause() : void loop())}
        >
          {running ? "Pause" : "Resume"}
        </button>
        <button
          class="btn"
          disabled={!graph || running || preparing || wanderActive}
          onClick={async () => {
            update(await request<Roadmap>({ op: "explore_extend", revision }));
            void loop();
          }}
        >
          Extend budget
        </button>
        <button
          class="btn"
          onClick={() => {
            setWanderReset((n) => n + 1);
            active.current = false;
            void request({
              op: "explore_cancel",
              revision,
              job_id: graphRef.current?.job_id,
            }).catch(() => {});
            generation.current++;
            setRunning(false);
            setPlaying(false);
            setTour(null);
            setPreparing(false);
            setGraph(null);
            onGraph(null);
            onPose(null);
          }}
        >
          Cancel
        </button>
      </div>
      {graph && (
        <>
          <label>
            Search budget used{" "}
            <progress
              max="1"
              value={Math.min(
                1,
                Math.max(
                  graph.used / graph.seconds,
                  graph.nodes.length / graph.limit,
                ),
              )}
            />
          </label>
          <div>
            {!running && graph.status === "running" ? "paused" : graph.status} ·{" "}
            {graph.nodes.length} nodes · {graph.edges.length} edges ·{" "}
            {graph.pending} pending · {graph.unresolved} unresolved
          </div>
          <small>Numerical coverage only; completeness is not certified.</small>
        </>
      )}
      <details>
        <summary>Advanced</summary>
        <label>
          Region radius{" "}
          <input
            type="number"
            min=".1"
            step=".5"
            value={radius}
            onChange={(e) => setRadius(Number(e.currentTarget.value))}
          />
        </label>
        <label>
          Active seconds{" "}
          <input
            type="number"
            min="1"
            value={seconds}
            onChange={(e) => setSeconds(Number(e.currentTarget.value))}
          />
        </label>
        <label>
          Node limit{" "}
          <input
            type="number"
            min="10"
            value={limit}
            onChange={(e) => setLimit(Number(e.currentTarget.value))}
          />
        </label>
        <label>
          Max tangent turn{" "}
          <input
            aria-label="Max tangent turn"
            type="number"
            min="1"
            max="45"
            value={turn}
            onChange={(e) => setTurn(Number(e.currentTarget.value))}
          />
        </label>
        <label>
          Correction / step{" "}
          <input
            aria-label="Correction ratio"
            type="number"
            min=".01"
            max=".5"
            step=".05"
            value={correction}
            onChange={(e) => setCorrection(Number(e.currentTarget.value))}
          />
        </label>
        <button
          class="btn"
          disabled={!graph || running || preparing || wanderActive}
          onClick={async () => {
            try {
              update(
                await request<Roadmap>({
                  op: "explore_refine",
                  revision,
                  spacing: Number(spacing),
                }),
              );
              void loop();
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          Refine with selected spacing
        </button>
        <small>
          Spacing uses scene-normalized RMS configuration distance. Feasibility:
          1e-9.
        </small>
      </details>
      <div class="exploration-controls">
        <label>
          Targets{" "}
          <input
            type="number"
            min="10"
            max="20"
            value={count}
            onChange={(e) => setCount(Number(e.currentTarget.value))}
          />
        </label>
        <label>
          Seed{" "}
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(Number(e.currentTarget.value))}
          />
        </label>
        <button
          class="btn"
          disabled={
            !graph || graph.nodes.length < 2 || preparing || wanderActive
          }
          onClick={build}
        >
          {preparing ? "Preparing tour…" : "Sample & build tour"}
        </button>
      </div>
      {preparing && (
        <label>
          Preparing feasible tour frames{" "}
          <progress max={prepared.total} value={prepared.done} />
          {prepared.done}/{prepared.total}
        </label>
      )}
      {tour && (
        <>
          <button class="btn" onClick={() => setPlaying(!playing)}>
            {playing ? "Pause tour" : "Play tour"}
          </button>
          <input
            aria-label="Tour position"
            type="range"
            min="0"
            max={tour.frames.length - 1}
            value={frame}
            onInput={(e) => {
              setPlaying(false);
              const i = Number(e.currentTarget.value);
              setFrame(i);
              onPose(tour.frames[i]);
            }}
          />
          <Dropdown
            label="Playback speed"
            value={String(speed)}
            onChange={(v) => setSpeed(Number(v))}
            options={[0.75, 1.5, 3, 6].map((v) => ({
              value: String(v),
              label: `${v}×`,
            }))}
          />
          <button
            class="btn"
            onClick={async () => {
              setPlaying(false);
              await request({
                op: "adopt",
                revision,
                configuration: tour.frames[frame],
              });
              onAdopt(tour.frames[frame]);
              setTour(null);
            }}
          >
            Use this pose
          </button>
        </>
      )}
      <WanderControls
        command={wanderCommand}
        onState={onWanderState}
        revision={revision}
        interrupt={interrupt + wanderReset}
        pose={pose}
        seed={seed}
        disabled={running || preparing}
        speed={speed}
        onSpeed={setSpeed}
        onBegin={() => {
          setPlaying(false);
          setTour(null);
          setError("");
        }}
        onActive={setWanderActive}
        onPose={onPose}
        onAdopt={onAdopt}
      />
      {graph && (
        <>
          <button class="btn" onClick={() => setShowGraph(!showGraph)}>
            Roadmap (3D projection)
          </button>
          {showGraph && <RoadmapPreview graph={graph} walk={tour?.walk} />}
        </>
      )}
      {error && (
        <div role="alert" style={{ color: "var(--danger)" }}>
          {error}
        </div>
      )}
    </details>
  );
}
