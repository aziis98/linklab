import { loadPyodide, type PyodideInterface } from 'pyodide'
import cadSource from './cad.py?raw'

/** The runtime files are copied to /public/pyodide by scripts/sync-pyodide.mjs. */
const INDEX_URL = new URL('/pyodide/', location.origin).href

let pending: Promise<PyodideInterface> | null = null

export function initPyodide(): Promise<PyodideInterface> {
  pending ??= loadPyodide({
    indexURL: INDEX_URL,
    packageBaseUrl: 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/',
  }).then(async (p) => {
    try {
      p.FS.writeFile('/home/pyodide/cad.py', cadSource)
    } catch {}
    try {
      p.FS.writeFile('/lib/python3.14/site-packages/cad.py', cadSource)
    } catch {}
    p.runPython(`
import sys
if '/home/pyodide' not in sys.path:
    sys.path.insert(0, '/home/pyodide')
import cad
from cad import *
`)
    try {
      await p.loadPackage(['numpy', 'scipy'])
    } catch (err) {
      console.warn('Scipy/numpy not loaded in pyodide (offline/cdn):', err)
    }
    return p
  })
  return pending
}

export type { PyodideInterface }
