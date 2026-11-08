import { loadPyodide } from "pyodide";
const modules = import.meta.glob("../kinematics/src/kinematics/**/*.py", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;
const ready = (async () => {
  const py = await loadPyodide({
    indexURL: new URL("/pyodide/", location.origin).href,
    packageBaseUrl: "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/",
  });
  await py.loadPackage(["numpy", "scipy", "sympy"]);
  for (const [name, source] of Object.entries(modules)) {
    const relative = name.split("/src/")[1];
    const path = `/home/pyodide/${relative}`;
    py.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
    py.FS.writeFile(path, source);
  }
  py.runPython(
    'import sys\nsys.path.insert(0,"/home/pyodide")\nfrom kinematics.core.runtime import dispatch_json',
  );
  return py;
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
