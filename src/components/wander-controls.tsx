import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { request } from "../pyodide";
import { Dropdown } from "./dropdown";

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
        settings: { seed, turning: Number(turning) },
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
      setState("stopped");
      setMessage(String(error));
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
        clock.current + Math.min((now - previous) / 1000, 0.1) * speed,
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
        <button
          class="btn"
          disabled={
            disabled ||
            state === "starting" ||
            state === "playing" ||
            state === "paused"
          }
          onClick={start}
        >
          {state === "starting" ? "Starting wander…" : "Start wander"}
        </button>
        {(state === "playing" || state === "paused") && (
          <button
            class="btn"
            onClick={() => {
              playing.current = state !== "playing";
              setState(state === "playing" ? "paused" : "playing");
            }}
          >
            {state === "playing" ? "Pause wander" : "Resume wander"}
          </button>
        )}
        {(state === "playing" ||
          state === "paused" ||
          state === "starting") && (
          <button
            class="btn"
            onClick={() => {
              cancel();
              setState("stopped");
              onActive(false);
            }}
          >
            Stop wander
          </button>
        )}
        <Dropdown
          label="Wander speed"
          value={String(speed)}
          onChange={(v) => onSpeed(Number(v))}
          options={[0.75, 1.5, 3, 6].map((value) => ({
            value: String(value),
            label: `${value}×`,
          }))}
        />
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
      {state !== "idle" && (
        <small role="status">
          Wander · {state === "playing" && buffering ? "buffering" : state} ·{" "}
          {elapsed.toFixed(1)} s
        </small>
      )}
      {message && <div role="status">{message}</div>}
      <small>
        Smooth random steering from the displayed pose. No exploration required.
      </small>
    </div>
  );
}
