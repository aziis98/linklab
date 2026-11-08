import { useEffect, useMemo, useState } from 'preact/hooks'
import IconPlayerPlay from '~icons/tabler/player-play'
import IconPlayerStop from '~icons/tabler/player-stop'
import IconRefresh from '~icons/tabler/refresh'
import IconArrowsMaximize from '~icons/tabler/arrows-maximize'
import IconRotate3d from '~icons/tabler/rotate-3d'
import { Split } from '@/components/splitter'
import { Editor } from '@/components/editor'
import { FileSwitcher } from '@/components/file-switcher'
import { Viewer, type SceneData } from '@/components/viewer'
import {
  createFile,
  deleteFile,
  ensureExamples,
  loadActiveId,
  loadFiles,
  renameFile,
  saveActiveId,
  saveFiles,
  type FileEntry,
} from '@/files'
import { initPyodide, type PyodideInterface } from '@/pyodide'

type State = 'idle' | 'loading' | 'ready' | 'error'

const SEED_BODY = `# Planar 4-Bar Linkage
l1 = 2.0
l2 = 3.0
d = 3.0

g1 = rod(origin, origin + right * d, id="g1")
r1 = rod(origin, up * l1, id="r1")
r2 = rod(g1.end, g1.end + up * l2, id="r2")
r3 = rod(r1.end, r2.end, id="r3")

constraint_point_point(g1.start, r1.start, id="j1")
constraint_point_point(r1.end, r3.start, id="j2")
constraint_point_point(r3.end, r2.end, id="j3")
constraint_point_point(r2.start, g1.end, id="j4")
`

const seedFiles = (): FileEntry[] => [createFile('main.py', SEED_BODY)]

export function App() {
  const [files, setFiles] = useState<FileEntry[]>(() => loadFiles())
  const [activeId, setActiveId] = useState<string | null>(() => {
    const saved = loadActiveId()
    const fs = loadFiles()
    if (saved && fs.some((f) => f.id === saved)) return saved
    return fs[0]?.id ?? null
  })
  const [state, setState] = useState<State>('idle')
  const [version, setVersion] = useState('')
  const [py, setPy] = useState<PyodideInterface | null>(null)
  const [scene, setScene] = useState<SceneData | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  // first run: seed a starter file
  useEffect(() => {
    if (files.length) return
    const seed = seedFiles()
    setFiles(seed)
    setActiveId(seed[0].id)
  }, [files.length])

  useEffect(() => saveFiles(files), [files])
  useEffect(() => saveActiveId(activeId), [activeId])
  useEffect(() => {
    setFiles((fs) => ensureExamples(fs))
  }, [])

  useEffect(() => {
    let alive = true
    setState('loading')
    initPyodide()
      .then((p) => {
        if (!alive) return
        setPy(p)
        setVersion(p.version)
        setState('ready')
      })
      .catch((err) => {
        if (!alive) return
        console.error(err)
        setState('error')
      })
    return () => {
      alive = false
    }
  }, [])

  const active = useMemo(
    () => files.find((f) => f.id === activeId) ?? null,
    [files, activeId],
  )

  const patch = (id: string, body: string) =>
    setFiles((fs) =>
      fs.map((f) => (f.id === id ? { ...f, body, editedAt: Date.now() } : f)),
    )

  const addFile = () => {
    const file = createFile(`untitled-${files.length + 1}.py`)
    setFiles([file, ...files])
    setActiveId(file.id)
  }

  const rename = (id: string, name: string) =>
    setFiles((fs) => renameFile(fs, id, name))

  const removeFile = (id: string) => {
    const next = deleteFile(files, id)
    setFiles(next)
    if (activeId === id) {
      setActiveId(next[0]?.id ?? null)
    }
  }

  const run = async () => {
    if (!py || !active) return
    setRunError(null)
    try {
      await py.runPythonAsync('import cad\ncad.reset()\nfrom cad import *\n')
      await py.runPythonAsync(active.body)
      const jsonStr = (await py.runPythonAsync(
        'cad.export_json()',
      )) as string
      const data: SceneData = JSON.parse(jsonStr)
      setScene(data)
    } catch (err: any) {
      console.error(err)
      setRunError(String(err?.message || err))
    }
  }

  useEffect(() => {
    if (state === 'ready' && active) {
      run()
    }
  }, [state, activeId])

  const stateLabel: Record<State, string> = {
    idle: 'idle',
    loading: 'loading',
    ready: 'ready',
    error: 'error',
  }

  return (
    <div class="app">
      <header class="bar bar--app">
        <span class="brand">
          <IconRotate3d class="icon" width="14" height="14" />
          CAD Detect Free Motions
        </span>
        <FileSwitcher
          files={files}
          activeId={activeId}
          onSelect={setActiveId}
          onNew={addFile}
          onRename={rename}
          onDelete={removeFile}
        />
        <span class="bar__spacer" />
        <span class="dot" data-state={state === 'ready' ? 'ok' : state} />
        <span>{stateLabel[state]}</span>
        <button
          type="button"
          class="btn btn--primary"
          disabled={state !== 'ready' || !active}
          onClick={run}
        >
          <IconPlayerPlay class="icon" width="12" height="12" />
          Run
        </button>
        <button type="button" class="btn btn--danger" disabled>
          <IconPlayerStop class="icon" width="12" height="12" />
          Stop
        </button>
      </header>

      <Split
        left={
          <section class="pane">
            <Editor
              value={active?.body ?? ''}
              onChange={(body) => active && patch(active.id, body)}
              onRun={run}
            />
          </section>
        }
        right={
          <section class="pane">
            <div class="bar bar--pane">
              <span class="bar__title">Render</span>
              <span class="bar__spacer" />
              <button
                type="button"
                class="btn btn--icon"
                title="Re-run"
                disabled={state !== 'ready' || !active}
                onClick={run}
              >
                <IconRefresh class="icon" width="14" height="14" />
              </button>
              <button type="button" class="btn btn--icon" title="Fullscreen" disabled>
                <IconArrowsMaximize class="icon" width="14" height="14" />
              </button>
            </div>
            <Viewer scene={scene} error={runError} />
          </section>
        }
      />

      <footer class="status">
        <span class="status__spacer" />
        <span>pyodide {version || '—'}</span>
      </footer>
    </div>
  )
}
