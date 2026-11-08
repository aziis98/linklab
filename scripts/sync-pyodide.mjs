// Copies the pyodide runtime out of node_modules into public/pyodide so the
// loader can fetch it from a stable, same-origin URL.
import { cp, mkdir, rm } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const from = join(root, 'node_modules', 'pyodide')
const to = join(root, 'public', 'pyodide')

const FILES = [
  'pyodide.asm.mjs',
  'pyodide.asm.wasm',
  'pyodide.mjs',
  'pyodide-lock.json',
  'python_stdlib.zip',
]

await rm(to, { recursive: true, force: true })
await mkdir(to, { recursive: true })
await Promise.all(FILES.map((f) => cp(join(from, f), join(to, f))))

console.log(`pyodide -> public/pyodide (${FILES.length} files)`)
