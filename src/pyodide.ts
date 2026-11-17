import { dispatch, stopDragWorker } from "./solver/client";

export interface PyodideStatus {
  phase: "idle" | "loading" | "ready" | "error";
  progress: number;
  label: string;
  loadedBytes?: number;
  totalBytes?: number;
  error?: string;
}

let worker: Worker | null = null;
let nextId = 0;
let status: PyodideStatus = {
  phase: "idle",
  progress: 0,
  label: "Starting Pyodide…",
};
const statusListeners = new Set<(status: PyodideStatus) => void>();

function updateStatus(next: PyodideStatus) {
  status = next;
  for (const listener of statusListeners) listener(status);
}

export function getPyodideStatus(): PyodideStatus {
  return status;
}

export function subscribePyodideStatus(
  listener: (status: PyodideStatus) => void,
) {
  statusListeners.add(listener);
  listener(status);
  return () => {
    statusListeners.delete(listener);
  };
}

const pending = new Map<
  number,
  { resolve: (value: unknown) => void; reject: (reason: Error) => void }
>();

function pythonRequest<T = unknown>(request: object): Promise<T> {
  if (!worker) {
    updateStatus({
      phase: "loading",
      progress: 0,
      label: "Starting Pyodide…",
    });
    worker = new Worker(new URL("./pyodide.worker.ts", import.meta.url), {
      type: "module",
    });
    worker.onmessage = ({ data }) => {
      if (data?.type === "pyodide-status") {
        updateStatus({
          phase: data.phase,
          progress: data.progress,
          label: data.label,
          loadedBytes: data.loadedBytes,
          totalBytes: data.totalBytes,
          error: data.error,
        });
        return;
      }
      const entry = pending.get(data.id);
      pending.delete(data.id);
      if (data.error) entry?.reject(new Error(data.error));
      else entry?.resolve(data.result);
    };
    worker.onerror = (event) => {
      const error = new Error(event.message || "Pyodide worker failed");
      updateStatus({
        phase: "error",
        progress: status.progress,
        label: "Something went wrong",
        error: error.message,
      });
      stop(error, true);
    };
  }
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve: (value) => resolve(value as T), reject });
    worker!.postMessage({ id, request });
  });
}

export function stop(
  reason = new Error("Python execution stopped"),
  preserveError = false,
) {
  stopDragWorker();
  worker?.terminate();
  worker = null;
  for (const entry of pending.values()) entry.reject(reason);
  pending.clear();
  if (!preserveError) {
    updateStatus({
      phase: "idle",
      progress: 0,
      label: "Starting Pyodide…",
    });
  }
}

// Serialize handoffs as well as solves, so Python never observes a stale JS pose.
let dispatchQueue: Promise<unknown> = Promise.resolve();
export function request<T = unknown>(message: object): Promise<T> {
  const result = dispatchQueue.then(() => dispatch<T>(message, pythonRequest));
  dispatchQueue = result.catch(() => {});
  return result;
}
