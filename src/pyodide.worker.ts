import { loadPyodide } from "pyodide";

const modules = import.meta.glob("../kinematics/src/kinematics/**/*.py", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

type Phase = "loading" | "ready" | "error";

interface StatusPayload {
  type: "pyodide-status";
  phase: Phase;
  progress: number;
  label: string;
  loadedBytes?: number;
  totalBytes?: number;
  error?: string;
}

function postStatus(payload: Omit<StatusPayload, "type">) {
  self.postMessage({ type: "pyodide-status", ...payload });
}

interface FetchEntry {
  loaded: number;
  total: number;
  hasKnownTotal: boolean;
}

const ready = (async () => {
  const originalFetch = self.fetch.bind(self);
  const PACKAGE_ESTIMATE_BYTES = 21 * 1024 * 1024;
  let stage: "runtime" | "packages" = "runtime";
  let priorBytes = 0;
  let stageFetches = new Map<number, FetchEntry>();
  let nextFetchId = 0;
  let maxProgress = 0;
  let lastLabel = "Loading Pyodide runtime…";
  let lastEmit = 0;

  const emitProgress = (force = false) => {
    const now = performance.now();
    if (!force && now - lastEmit < 60) return;
    lastEmit = now;

    let loadedBytes = 0;
    let totalBytes = 0;
    let allKnown = stageFetches.size > 0;
    let ratioSum = 0;
    let ratioCount = 0;

    for (const entry of stageFetches.values()) {
      loadedBytes += entry.loaded;
      if (entry.hasKnownTotal && entry.total > 0) {
        totalBytes += entry.total;
        ratioSum += Math.min(1, entry.loaded / entry.total);
        ratioCount += 1;
      } else {
        allKnown = false;
      }
    }

    const stageRatio =
      allKnown && totalBytes > 0
        ? Math.min(1, loadedBytes / totalBytes)
        : ratioCount > 0
          ? ratioSum / Math.max(stageFetches.size, ratioCount)
          : stage === "packages" && loadedBytes > 0
            ? Math.min(0.98, loadedBytes / PACKAGE_ESTIMATE_BYTES)
            : 0;

    const rawProgress =
      stage === "runtime" ? stageRatio * 0.42 : 0.42 + stageRatio * 0.46;
    maxProgress = Math.max(maxProgress, Math.min(0.88, rawProgress));

    const cumulativeLoaded = priorBytes + loadedBytes;
    const showTotal =
      stage === "runtime" && allKnown && totalBytes >= loadedBytes;

    postStatus({
      phase: "loading",
      progress: maxProgress,
      label: lastLabel,
      loadedBytes: cumulativeLoaded > 0 ? cumulativeLoaded : undefined,
      totalBytes: showTotal ? priorBytes + totalBytes : undefined,
    });
  };

  self.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const res = await originalFetch(input, init);
    if (!res.ok || !res.body) return res;

    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.endsWith("pyodide.asm.wasm")) {
      lastLabel = "Loading Pyodide WASM…";
    } else if (url.endsWith("python_stdlib.zip")) {
      lastLabel = "Loading Python stdlib…";
    }

    const contentEncoding = res.headers.get("content-encoding");
    const rawLength = Number(res.headers.get("content-length") || 0);
    const hasKnownTotal = !contentEncoding && Number.isFinite(rawLength) && rawLength > 0;
    const entry: FetchEntry = {
      loaded: 0,
      total: hasKnownTotal ? rawLength : 0,
      hasKnownTotal,
    };
    const fetchId = ++nextFetchId;
    stageFetches.set(fetchId, entry);
    emitProgress(true);

    const reader = res.body.getReader();
    const stream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        const { done, value } = await reader.read();
        if (done) {
          if (entry.hasKnownTotal) entry.loaded = Math.max(entry.loaded, entry.total);
          emitProgress(true);
          controller.close();
          return;
        }
        entry.loaded += value.byteLength;
        emitProgress();
        controller.enqueue(value);
      },
      cancel(reason) {
        return reader.cancel(reason);
      },
    });

    return new Response(stream, {
      status: res.status,
      statusText: res.statusText,
      headers: res.headers,
    });
  };

  try {
    postStatus({
      phase: "loading",
      progress: 0.02,
      label: lastLabel,
    });

    const py = await loadPyodide({
      indexURL: new URL("/pyodide/", location.origin).href,
      packageBaseUrl: "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/",
    });

    for (const entry of stageFetches.values()) {
      priorBytes += entry.loaded;
    }
    stage = "packages";
    stageFetches = new Map();
    maxProgress = Math.max(maxProgress, 0.42);
    lastLabel = "Loading scientific packages…";
    postStatus({
      phase: "loading",
      progress: maxProgress,
      label: lastLabel,
      loadedBytes: priorBytes > 0 ? priorBytes : undefined,
    });

    await py.loadPackage(["numpy", "scipy", "sympy"], {
      messageCallback: (message: string) => {
        if (message.startsWith("Loading ") || message.startsWith("Loaded ")) {
          lastLabel = message.endsWith("…") ? message : `${message}…`;
          emitProgress(true);
        }
      },
    });

    for (const entry of stageFetches.values()) {
      priorBytes += entry.loaded;
    }
    maxProgress = Math.max(maxProgress, 0.9);
    postStatus({
      phase: "loading",
      progress: maxProgress,
      label: "Initializing kinematics runtime…",
      loadedBytes: priorBytes > 0 ? priorBytes : undefined,
    });

    for (const [name, source] of Object.entries(modules)) {
      const relative = name.split("/src/")[1];
      const path = `/home/pyodide/${relative}`;
      py.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
      py.FS.writeFile(path, source);
    }
    py.runPython(
      'import sys\nsys.path.insert(0,"/home/pyodide")\nfrom kinematics.core.runtime import dispatch_json',
    );

    postStatus({
      phase: "ready",
      progress: 1,
      label: "Solving initial scene…",
    });
    return py;
  } catch (error) {
    postStatus({
      phase: "error",
      progress: maxProgress,
      label: "Something went wrong",
      error: String(error),
    });
    throw error;
  } finally {
    self.fetch = originalFetch;
  }
})();

let queue = Promise.resolve();
self.onmessage = ({ data }) => {
  queue = queue.then(async () => {
    try {
      const py = await ready;
      py.globals.set("_request", JSON.stringify(data.request));
      const result = JSON.parse(
        py.runPython("dispatch_json(_request)") as string,
      );
      self.postMessage({ id: data.id, result });
    } catch (error) {
      self.postMessage({ id: data.id, error: String(error) });
    }
  });
};
