import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { request } from "../pyodide";
import { Dropdown } from "./dropdown";

// The previous default was 3; the displayed 1× now plays at twice that rate.
const BASE_PLAYBACK_RATE = 6;

type Config = Record<string, [number, number, number]>;
type Frame = { configuration: Config; time: number };
type Batch = { frames: Frame[]; status: string; reason: string };

export function WanderControls({
  revision,
  interrupt,
  pose,
  seed,
  disabled,
  speed,
  onSpeed,
  onBegin,
  onActive,
  onPose,
  onAdopt,
  command,
  onState,
}: {
  revision: number;
  interrupt: number;
  pose: Config;
  seed: number;
  disabled: boolean;
  speed: number;
  onSpeed: (speed: number) => void;
  onBegin: () => void;
  onActive: (active: boolean) => void;
  onPose: (pose: Config) => void;
  onAdopt: (pose: Config) => void;
  command: number;
  onState: (state: string) => void;
}) {
  const [state, setState] = useState("idle");
  const [message, setMessage] = useState("");
  const [buffering, setBuffering] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [turning, setTurning] = useState(".8");
  const [repulsion,setRepulsion]=useState(0.5);
  const repulsionRef=useRef(repulsion);repulsionRef.current=repulsion;
  const generation = useRef(0),
    job = useRef<number | null>(null);
  const frames = useRef<Frame[]>([]),
    shown = useRef<Frame | null>(null);
  const clock = useRef(0),
    playing = useRef(false),
    terminal = useRef(false);
  const lastCommand = useRef(command);
  useEffect(() => {
    onState(disabled ? "busy" : state);
  }, [state, disabled]);
  useEffect(() => {
    if (lastCommand.current === command) return;
    lastCommand.current = command;
    if (disabled || state === "starting") return;
    if (state === "playing" || state === "paused") {
      playing.current = state !== "playing";
      setState(state === "playing" ? "paused" : "playing");
    } else void start();
  }, [command]);

  function cancel() {
    generation.current++;
    playing.current = false;
    frames.current = [];
    const id = job.current;
    job.current = null;
    if (id !== null)
      void request({ op: "wander_cancel", revision, job_id: id }).catch(
        () => {},
      );
  }
  useLayoutEffect(() => {
    cancel();
    setState("idle");
    shown.current = null;
    setMessage("");
    onActive(false);
    return cancel;
  }, [interrupt, revision]);

  async function start() {
    cancel();
    const gen = generation.current;
    setState("starting");
    setMessage("");
    setElapsed(0);
    clock.current = 0;
    terminal.current = false;
    shown.current = null;
    onBegin();
    onActive(true);
    try {
      const initial = await request<Batch & { job_id: number }>({
        op: "wander_start",
        revision,
        configuration: pose,
        settings: { seed, turning: Number(turning), boundary_repulsion: repulsionRef.current },
      });
      if (gen !== generation.current) {
        void request({
          op: "wander_cancel",
          revision,
          job_id: initial.job_id,
        }).catch(() => {});
        return;
      }
      job.current = initial.job_id;
      frames.current = initial.frames;
      shown.current = initial.frames[0];
      onPose(initial.frames[0].configuration);
      playing.current = true;
      setState("playing");
      while (gen === generation.current) {
        const tail = frames.current.at(-1)?.time ?? clock.current;
        if (
          !playing.current ||
          tail - clock.current > 3 ||
          frames.current.length > 360
        ) {
          await new Promise((resolve) => setTimeout(resolve, 30));
          continue;
        }
        const batch = await request<Batch>({
          op: "wander_step",
          boundary_repulsion: repulsionRef.current,
          revision,
          job_id: initial.job_id,
        });
        if (gen !== generation.current) return;
        frames.current.push(...batch.frames);
        if (batch.status !== "running") {
          terminal.current = true;
          setMessage(batch.reason);
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    } catch (error) {
      if (gen !== generation.current) return;
      cancel();
      const text = String(error);
      const locked = text.includes("No continuous motion is available");
      const singular = text.includes("unresolved singular configuration");
      setState(locked || singular ? "unavailable" : "error");
      setMessage(locked
        ? "This configuration has no continuous motion. Try another scene or reassemble the construction before wandering."
        : singular ? "Motion is unresolved at this singular configuration. Try reassembling to a different pose."
        : "Wander could not start. Run the scene again and retry.");
      onActive(false);
    }
  }

  useEffect(() => {
    if (state !== "playing") return;
    let previous = performance.now(),
      id = 0;
    function tick(now: number) {
      const queue = frames.current;
      const tail = queue.at(-1)?.time ?? clock.current;
      clock.current = Math.min(
        tail,
        clock.current + Math.min((now - previous) / 1000, 0.1) * speed * BASE_PLAYBACK_RATE,
      );
      previous = now;
      while (queue.length > 1 && queue[1].time <= clock.current) queue.shift();
      if (queue[0] && queue[0] !== shown.current) {
        shown.current = queue[0];
        onPose(queue[0].configuration);
      }
      setBuffering(!terminal.current && clock.current >= tail);
      setElapsed(Math.floor(clock.current * 10) / 10);
      if (terminal.current && clock.current >= tail) {
        playing.current = false;
        setState("stopped");
        onActive(false);
        return;
      }
      id = requestAnimationFrame(tick);
    }
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [state, speed]);

  return (
    <div class="wander-controls">
      <div class="exploration-controls">
        <label class="wander-speed">
          <span>Speed <output>{speed.toFixed(2).replace(/\.?0+$/, "")}×</output></span>
          <input aria-label="Wander speed" type="range" style={{ "--range-progress": `${((speed - 0.25) / 3.75) * 100}%` }} min="0.25" max="4" step="0.25" value={speed} onInput={(e) => onSpeed(Number(e.currentTarget.value))} />
          <span class="wander-speed__scale"><span>0.25×</span><span>4×</span></span>
        </label>
        <label class="wander-speed">
          <span>Boundary repulsion <output>{repulsion===0?"Off":`${repulsion.toFixed(1)}×`}</output></span>
          <input aria-label="Boundary repulsion" type="range" min="0" max="4" step="0.1" value={repulsion} style={{"--range-progress":`${repulsion/4*100}%`}} onInput={(e)=>setRepulsion(Number(e.currentTarget.value))}/>
          <span class="wander-speed__scale"><span>Off</span><span>Strong</span></span>
        </label>
        <Dropdown
          label="Wander steering"
          value={turning}
          onChange={setTurning}
          disabled={
            state === "playing" || state === "paused" || state === "starting"
          }
          options={[
            { value: ".3", label: "Gentle turns" },
            { value: ".8", label: "Natural turns" },
            { value: "1.6", label: "Frequent turns" },
          ]}
        />
        {shown.current && (
          <button
            class="btn"
            onClick={async () => {
              const current = shown.current!.configuration;
              cancel();
              setState("stopped");
              onActive(false);
              const gen = generation.current;
              try {
                await request({
                  op: "adopt",
                  revision,
                  configuration: current,
                });
                if (gen !== generation.current) return;
                onAdopt(current);
                shown.current = null;
                setState("idle");
              } catch (error) {
                if (gen === generation.current) setMessage(String(error));
              }
            }}
          >
            Use wander pose
          </button>
        )}
      </div>
      {!["idle", "unavailable", "error"].includes(state) && (
        <small role="status">
          Wander · {state === "playing" && buffering ? "buffering" : state} ·{" "}
          {elapsed.toFixed(1)} s
        </small>
      )}
      {message && <div class={`wander-notice ${state === "unavailable" ? "wander-notice--unavailable" : ""}`} role="status"><strong>{state === "unavailable" ? "Wander unavailable" : "Wander paused"}</strong><p>{message}</p></div>}
      <small>
        Follow continuous motion from the current pose.
      </small>
    </div>
  );
}
