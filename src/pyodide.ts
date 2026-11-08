let worker: Worker | null = null;
let nextId = 0;
const pending = new Map<
  number,
  { resolve: (value: unknown) => void; reject: (reason: Error) => void }
>();
export function request<T = unknown>(request: object): Promise<T> {
  if (!worker) {
    worker = new Worker(new URL("./pyodide.worker.ts", import.meta.url), {
      type: "module",
    });
    worker.onmessage = ({ data }) => {
      const entry = pending.get(data.id);
      pending.delete(data.id);
      if (data.error) entry?.reject(new Error(data.error));
      else entry?.resolve(data.result);
    };
    worker.onerror = (event) => {
      stop(new Error(event.message));
    };
  }
  const id = ++nextId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve: (value) => resolve(value as T), reject });
    worker!.postMessage({ id, request });
  });
}
export function stop(reason = new Error("Python execution stopped")) {
  worker?.terminate();
  worker = null;
  for (const entry of pending.values()) entry.reject(reason);
  pending.clear();
}
