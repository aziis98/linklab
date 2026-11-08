import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import preact from '@preact/preset-vite'
import Icons from 'unplugin-icons/vite'
import { defineConfig, type Plugin } from 'vite'

const rootDir = fileURLToPath(new URL('.', import.meta.url))

function pyodideServerPlugin(): Plugin {
  return {
    name: 'pyodide-serve',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const rawUrl = req.url || ''
        if (!rawUrl.startsWith('/pyodide/')) return next()
        const filename = rawUrl.replace(/^\/pyodide\//, '').split('?')[0]
        const candidatePaths = [
          join(rootDir, 'public', 'pyodide', filename),
          join(rootDir, 'node_modules', 'pyodide', filename),
        ]
        for (const p of candidatePaths) {
          if (existsSync(p)) {
            const ext = filename.split('.').pop() || ''
            const types: Record<string, string> = {
              mjs: 'application/javascript',
              js: 'application/javascript',
              wasm: 'application/wasm',
              json: 'application/json',
              zip: 'application/zip',
            }
            res.setHeader('Content-Type', types[ext] || 'application/octet-stream')
            const content = await readFile(p)
            res.end(content)
            return
          }
        }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    pyodideServerPlugin(),
    preact(),
    // `~icons/tabler/<name>` -> preact components, resolved at build time from
    // @iconify-json/tabler so nothing is fetched from an icon CDN at runtime.
    Icons({ compiler: 'jsx', jsx: 'preact' }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
