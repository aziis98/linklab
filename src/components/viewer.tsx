import { useEffect, useMemo, useRef, useState } from 'preact/hooks'
import {
  buildLinkageGraph,
  checkConstraintViolations,
  computeLinkageOrbitsWithConfigs,
  snapToNearestStableConfig,
  solveInteractiveJoint,
  solveInteractiveRod,
  type SolverResult,
} from './solver'

export interface EntityData {
  id: string
  type: string
  length: number
  pose: { pos: [number, number, number]; rot: number[][] }
  p1: [number, number, number]
  p2: [number, number, number]
}

export interface JointData {
  id: string
  type: string
  pos: [number, number, number]
  entity_a?: string | null
  point_a?: string | null
  entity_b?: string | null
  point_b?: string | null
}

export interface TangentVectorData {
  basis_idx: number
  vector: [number, number]
  obstructed: boolean
  obstruction_norm: number
}

export interface NodeAnalysisData {
  id: number
  pos: [number, number]
  fixed: boolean
  joint_ids: string[]
  rod_ids: string[]
  tangents: TangentVectorData[]
}

export interface ObstructedVectorData {
  basis_idx: number
  obstruction_norm: number
  is_obstructed: boolean
  centripetal_vector: number[]
  acceleration_mismatch: number[]
}

export interface MobilityAnalysis {
  dof_1st: number
  dof_2nd: number
  rank: number
  n_vars: number
  m_constraints: number
  singular_values: number[]
  is_singular: boolean
  is_dead_center: boolean
  status: 'dead_center_singularity' | 'mobile' | 'rigid'
  message: string
  nodes: NodeAnalysisData[]
  obstructed_vectors: ObstructedVectorData[]
}

export interface SceneData {
  name: string
  entities: EntityData[]
  joints: JointData[]
  is_planar: boolean
  analysis?: MobilityAnalysis
}

interface ViewerProps {
  scene: SceneData | null
  error?: string | null
}

const entIsGround = (id: string) =>
  id.toLowerCase().includes('ground') || id.toLowerCase().startsWith('g')

/**
 * Returns an SVG path for an engineering capsule (obround) rod link:
 * a rectangular body spanning between (x1, y1) and (x2, y2) with
 * semicircular arcs of radius `radius` centered at both endpoints.
 */
function getCapsulePath(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  radius: number,
): string {
  const dx = x2 - x1
  const dy = y2 - y1
  const len = Math.hypot(dx, dy)
  if (len < 1e-4) {
    return `M ${x1 - radius} ${y1} A ${radius} ${radius} 0 1 0 ${x1 + radius} ${y1} A ${radius} ${radius} 0 1 0 ${x1 - radius} ${y1} Z`
  }
  const ux = dx / len
  const uy = dy / len
  // Normal vector perpendicular to rod (90 deg CCW in screen space with +Y down)
  const nx = uy
  const ny = -ux

  const ax = x1 + radius * nx
  const ay = y1 + radius * ny
  const bx = x2 + radius * nx
  const by = y2 + radius * ny
  const cx = x2 - radius * nx
  const cy = y2 - radius * ny
  const dxPt = x1 - radius * nx
  const dyPt = y1 - radius * ny

  return `M ${ax.toFixed(2)} ${ay.toFixed(2)} L ${bx.toFixed(2)} ${by.toFixed(2)} A ${radius} ${radius} 0 0 1 ${cx.toFixed(2)} ${cy.toFixed(2)} L ${dxPt.toFixed(2)} ${dyPt.toFixed(2)} A ${radius} ${radius} 0 0 1 ${ax.toFixed(2)} ${ay.toFixed(2)} Z`
}

export function Viewer({ scene, error }: ViewerProps) {
  const [mode, setMode] = useState<'2d' | '3d'>('2d')
  const [pan, setPan] = useState<[number, number]>([0, 0])
  const [zoom, setZoom] = useState(1.0) // canonical 1x zoom
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 600, h: 400 })
  const [live, setLive] = useState<SolverResult | null>(null)
  const [activeDrag, setActiveDrag] = useState<string | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const [showOrbits, setShowOrbits] = useState(false)
  const [showTangents, setShowTangents] = useState(true)
  const [showAnalysisDetails, setShowAnalysisDetails] = useState(false)
  const [dragTrails, setDragTrails] = useState<Record<string, [number, number][]>>({})

  const containerRef = useRef<HTMLDivElement | null>(null)
  const panStartRef = useRef<{ x: number; y: number } | null>(null)
  const rodDragRef = useRef<{ id: string; lastWorld: [number, number] } | null>(null)

  // Measure container
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => {
      const rect = el.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        setSize({ w: rect.width, h: rect.height })
      }
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Reset positions and view on new scene ("run" or file switch)
  useEffect(() => {
    if (scene) {
      setMode(scene.is_planar ? '2d' : '3d')
      setPan([0, 0])
      setZoom(1.0)
      setLive(null)
      setActiveDrag(null)
      setHovered(null)
      setDragTrails({})
    }
  }, [scene])

  // Active positions: either dragged live positions or initial scene definition
  const currentData = useMemo(() => {
    if (!scene) return null
    const joints: Record<string, [number, number]> = {}
    scene.joints.forEach((j) => {
      joints[j.id] = live?.joints[j.id] ?? [j.pos[0], j.pos[1]]
    })

    const rods: Record<string, { p1: [number, number]; p2: [number, number] }> = {}
    scene.entities.forEach((e) => {
      rods[e.id] = live?.rods[e.id] ?? {
        p1: [e.p1[0], e.p1[1]],
        p2: [e.p2[0], e.p2[1]],
      }
    })
    return { joints, rods }
  }, [scene, live])

  // Precomputed full centroid orbits and valid manifold configurations across all connected components
  const orbitData = useMemo(() => {
    if (!scene) return { orbits: {}, configs: [] }
    try {
      return computeLinkageOrbitsWithConfigs(scene, 72)
    } catch {
      return { orbits: {}, configs: [] }
    }
  }, [scene])

  const precomputedOrbits = orbitData.orbits
  const validConfigs = orbitData.configs

  // Real-time constraint violations calculation
  const violations = useMemo(() => {
    if (!scene || !currentData) {
      return {
        violatedRods: new Set<string>(),
        violatedJoints: new Set<string>(),
        maxError: 0,
      }
    }
    return checkConstraintViolations(scene, currentData, 0.04)
  }, [scene, currentData])

  // Snap to nearest stable configuration on mouse/pointer release
  useEffect(() => {
    if (!activeDrag) return
    const handleGlobalUp = () => {
      if (scene) {
        setActiveDrag(null)
        rodDragRef.current = null
        const snapped = snapToNearestStableConfig(scene, live, validConfigs)
        setLive(snapped)
        updateDragTrails(snapped)
      }
    }
    window.addEventListener('pointerup', handleGlobalUp)
    window.addEventListener('pointercancel', handleGlobalUp)
    return () => {
      window.removeEventListener('pointerup', handleGlobalUp)
      window.removeEventListener('pointercancel', handleGlobalUp)
    }
  }, [activeDrag, scene, live, validConfigs])

  // Fixed joints set (anchors to ground)
  const fixedJoints = useMemo(() => {
    if (!scene) return new Set<string>()
    const graph = buildLinkageGraph(scene, live)
    const set = new Set<string>()
    scene.joints.forEach((j) => {
      const nid = graph.jointToNode.get(j.id)
      if (nid !== undefined && graph.nodes[nid].fixed) {
        set.add(j.id)
      }
    })
    return set
  }, [scene, live])

  // Model bounds
  const bounds = useMemo(() => {
    if (!scene) return { cx: 0, cy: 0, span: 4 }
    const pts: [number, number][] = []
    scene.entities.forEach((e) => pts.push([e.p1[0], e.p1[1]], [e.p2[0], e.p2[1]]))
    scene.joints.forEach((j) => pts.push([j.pos[0], j.pos[1]]))

    if (!pts.length) return { cx: 0, cy: 0, span: 4 }
    const xs = pts.map((p) => p[0])
    const ys = pts.map((p) => p[1])
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    const span = Math.max(maxX - minX, maxY - minY, 1.0) * 1.35
    return { cx, cy, span }
  }, [scene])

  // Canonical 1x zoom incorporates comfortable 2x framing into the base scale
  const scale = useMemo(() => {
    const minDim = Math.min(size.w, size.h)
    return (minDim / (bounds.span * 2.0)) * zoom
  }, [size, bounds.span, zoom])

  const toScreen = (x: number, y: number): [number, number] => [
    size.w / 2 + (x - bounds.cx) * scale + pan[0],
    size.h / 2 - (y - bounds.cy) * scale + pan[1],
  ]

  const toWorld = (sx: number, sy: number): [number, number] => [
    bounds.cx + (sx - size.w / 2 - pan[0]) / scale,
    bounds.cy - (sy - size.h / 2 - pan[1]) / scale,
  ]

  // Accumulate live drag centroids for orbits
  const updateDragTrails = (nextSol: SolverResult) => {
    if (!scene) return
    setDragTrails((prev) => {
      const next = { ...prev }
      scene.entities.forEach((ent) => {
        const isGround =
          ent.id.toLowerCase().includes('ground') ||
          ent.id.toLowerCase().startsWith('g')
        if (isGround) return
        const r = nextSol.rods[ent.id]
        if (r) {
          const pt: [number, number] = [
            (r.p1[0] + r.p2[0]) / 2,
            (r.p1[1] + r.p2[1]) / 2,
          ]
          const cur = next[ent.id] ? [...next[ent.id]] : []
          if (
            !cur.length ||
            Math.hypot(cur[cur.length - 1][0] - pt[0], cur[cur.length - 1][1] - pt[1]) >
              0.03
          ) {
            cur.push(pt)
            if (cur.length > 250) cur.shift()
            next[ent.id] = cur
          }
        }
      })
      return next
    })
  }

  // Pointer events for Canvas Pan
  const onCanvasPointerDown = (e: PointerEvent) => {
    panStartRef.current = { x: e.clientX - pan[0], y: e.clientY - pan[1] }
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  }

  const onCanvasPointerMove = (e: PointerEvent) => {
    if (!panStartRef.current) return
    setPan([e.clientX - panStartRef.current.x, e.clientY - panStartRef.current.y])
  }

  const onCanvasPointerUp = (e: PointerEvent) => {
    panStartRef.current = null
    if (activeDrag && scene) {
      setActiveDrag(null)
      rodDragRef.current = null
      const snapped = snapToNearestStableConfig(scene, live, validConfigs)
      setLive(snapped)
      updateDragTrails(snapped)
    }
    try {
      ;(e.currentTarget as Element).releasePointerCapture(e.pointerId)
    } catch {}
  }

  const onWheel = (e: WheelEvent) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.15 : 0.85
    setZoom((z) => Math.max(0.1, Math.min(20.0, z * factor)))
  }

  // Pointer events for Joint Dragging
  const onJointPointerDown = (e: PointerEvent, id: string) => {
    if (fixedJoints.has(id)) return
    e.stopPropagation()
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
    setActiveDrag(`joint:${id}`)
  }

  const onJointPointerMove = (e: PointerEvent, id: string) => {
    if (activeDrag !== `joint:${id}` || !scene) return
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const [wx, wy] = toWorld(e.clientX - rect.left, e.clientY - rect.top)

    const { sol } = solveInteractiveJoint(scene, id, [wx, wy], validConfigs, live, 0.75)
    setLive(sol)
    updateDragTrails(sol)
  }

  const onJointPointerUp = (e: PointerEvent) => {
    setActiveDrag(null)
    if (scene) {
      const snapped = snapToNearestStableConfig(scene, live, validConfigs)
      setLive(snapped)
      updateDragTrails(snapped)
    }
    try {
      ;(e.currentTarget as Element).releasePointerCapture(e.pointerId)
    } catch {}
  }

  // Pointer events for Rod Dragging
  const onRodPointerDown = (e: PointerEvent, id: string) => {
    const isGround =
      entIsGround(id)
    if (isGround) return

    e.stopPropagation()
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const wPos = toWorld(e.clientX - rect.left, e.clientY - rect.top)
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
    rodDragRef.current = { id, lastWorld: wPos }
    setActiveDrag(`rod:${id}`)
  }

  const onRodPointerMove = (e: PointerEvent, id: string) => {
    if (activeDrag !== `rod:${id}` || !rodDragRef.current || !scene) return
    const el = containerRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const [curX, curY] = toWorld(e.clientX - rect.left, e.clientY - rect.top)
    const dx = curX - rodDragRef.current.lastWorld[0]
    const dy = curY - rodDragRef.current.lastWorld[1]
    rodDragRef.current.lastWorld = [curX, curY]

    const { sol } = solveInteractiveRod(scene, id, [dx, dy], live, 0.75)
    setLive(sol)
    updateDragTrails(sol)
  }

  const onRodPointerUp = (e: PointerEvent) => {
    setActiveDrag(null)
    rodDragRef.current = null
    if (scene) {
      const snapped = snapToNearestStableConfig(scene, live, validConfigs)
      setLive(snapped)
      updateDragTrails(snapped)
    }
    try {
      ;(e.currentTarget as Element).releasePointerCapture(e.pointerId)
    } catch {}
  }

  // CAD Grid calculations
  const gridStep = useMemo(() => {
    const raw = 50 / scale
    const power = Math.pow(10, Math.floor(Math.log10(raw)))
    const frac = raw / power
    if (frac <= 1.5) return power
    if (frac <= 3.5) return 2 * power
    if (frac <= 7.5) return 5 * power
    return 10 * power
  }, [scale])

  const [ox, oy] = toScreen(0, 0)
  const xMin = bounds.cx - (size.w / 2 + pan[0]) / scale
  const xMax = bounds.cx + (size.w / 2 - pan[0]) / scale
  const yMin = bounds.cy - (size.h / 2 - pan[1]) / scale
  const yMax = bounds.cy + (size.h / 2 + pan[1]) / scale

  const vGridLines: number[] = []
  const firstX = Math.floor(xMin / gridStep) * gridStep
  for (let x = firstX; x <= xMax; x += gridStep) vGridLines.push(x)

  const hGridLines: number[] = []
  const firstY = Math.floor(yMin / gridStep) * gridStep
  for (let y = firstY; y <= yMax; y += gridStep) hGridLines.push(y)

  return (
    <div
      class="viewer"
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        background: 'var(--cad-bg)',
      }}
    >
      {/* Top Left Mobility & Singularity HUD */}
      {scene?.analysis && (
        <div
          class="mobility-hud"
          style={{
            position: 'absolute',
            top: '8px',
            left: '8px',
            zIndex: 10,
            maxWidth: '380px',
            background: 'var(--bg-raised)',
            border: `1px solid ${
              scene.analysis.is_dead_center
                ? '#f43f5e'
                : scene.analysis.dof_2nd > 0
                  ? '#10b981'
                  : 'var(--line-color)'
            }`,
            borderRadius: '6px',
            boxShadow: scene.analysis.is_dead_center
              ? '0 0 12px rgba(244, 63, 94, 0.22), var(--shadow-pop)'
              : 'var(--shadow-pop)',
            backdropFilter: 'blur(8px)',
            fontSize: '11px',
            padding: '7px 10px',
            userSelect: 'none',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  display: 'inline-block',
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: scene.analysis.is_dead_center
                    ? '#f43f5e'
                    : scene.analysis.dof_2nd > 0
                      ? '#10b981'
                      : '#94a3b8',
                }}
              />
              <span style={{ fontWeight: 650, fontSize: '11px', letterSpacing: '0.02em' }}>
                {scene.analysis.is_dead_center
                  ? 'DEAD-CENTER SINGULARITY'
                  : scene.analysis.dof_2nd > 0
                    ? 'CERTIFIED MOBILE MANIFOLD'
                    : 'RIGID ASSEMBLY'}
              </span>
            </div>
            <button
              type="button"
              class="btn"
              style={{
                height: '18px',
                padding: '0 6px',
                fontSize: '9px',
                fontFamily: 'var(--font-mono)',
                lineHeight: 1,
              }}
              onClick={() => setShowAnalysisDetails((v) => !v)}
              title="Toggle mathematical diagnostics"
            >
              {showAnalysisDetails ? 'Hide' : 'Math ▾'}
            </button>
          </div>

          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '5px',
              marginTop: '5px',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
            }}
          >
            <span
              style={{
                padding: '1px 5px',
                borderRadius: '3px',
                background: scene.analysis.is_dead_center ? 'rgba(244, 63, 94, 0.15)' : 'var(--bg-sunken)',
                color: scene.analysis.is_dead_center ? '#e11d48' : 'var(--fg)',
                fontWeight: 600,
              }}
            >
              1st-ord: {scene.analysis.dof_1st} DOF {scene.analysis.is_dead_center ? '(Phantom)' : ''}
            </span>
            <span
              style={{
                padding: '1px 5px',
                borderRadius: '3px',
                background: scene.analysis.dof_2nd > 0 ? 'rgba(16, 185, 129, 0.15)' : 'var(--bg-sunken)',
                color: scene.analysis.dof_2nd > 0 ? '#059669' : 'var(--fg)',
                fontWeight: 600,
              }}
            >
              2nd-ord: {scene.analysis.dof_2nd} DOF {scene.analysis.is_dead_center ? '(Locked)' : ''}
            </span>
            <span
              style={{
                padding: '1px 5px',
                borderRadius: '3px',
                background: 'var(--bg-sunken)',
                color: 'var(--fg-muted)',
              }}
            >
              Rank: {scene.analysis.rank}/{scene.analysis.m_constraints}
            </span>
          </div>

          {showAnalysisDetails && (
            <div
              style={{
                marginTop: '7px',
                paddingTop: '6px',
                borderTop: '1px solid var(--line-color)',
                fontSize: '10px',
                lineHeight: 1.4,
                color: 'var(--fg-muted)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              <div style={{ color: 'var(--fg)', marginBottom: '4px' }}>{scene.analysis.message}</div>
              <div>Singular values σ: [{scene.analysis.singular_values.map((v) => v.toFixed(3)).join(', ')}]</div>
              {scene.analysis.obstructed_vectors.map((ob, idx) => (
                <div key={idx} style={{ marginTop: '2px', color: ob.is_obstructed ? '#e11d48' : '#059669' }}>
                  Kernel direction {idx + 1}: {ob.is_obstructed ? 'Curvature Obstructed' : 'Free Motion'} (Δa = {ob.obstruction_norm.toFixed(3)})
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Top right view buttons */}
      <div
        style={{
          position: 'absolute',
          top: '8px',
          right: '8px',
          zIndex: 10,
          display: 'flex',
          gap: '4px',
        }}
      >
        <button
          type="button"
          class={`btn ${mode === '2d' ? 'btn--active' : ''}`}
          onClick={() => setMode('2d')}
          title="2D View"
        >
          2D
        </button>
        <button
          type="button"
          class={`btn ${mode === '3d' ? 'btn--active' : ''}`}
          onClick={() => setMode('3d')}
          title="3D View"
        >
          3D
        </button>
        <button
          type="button"
          class="btn"
          onClick={() => {
            setZoom(1.0)
            setPan([0, 0])
          }}
          title="Reset Zoom & Pan to 1x"
        >
          1x
        </button>
        {live && (
          <button
            type="button"
            class="btn"
            onClick={() => {
              setLive(null)
              setDragTrails({})
            }}
            title="Reset dragged positions to script"
          >
            Reset
          </button>
        )}
      </div>

      {/* Bottom left Orbits & Tangents Toggles */}
      <div
        style={{
          position: 'absolute',
          bottom: '10px',
          left: '10px',
          zIndex: 10,
          display: 'flex',
          gap: '6px',
          alignItems: 'center',
        }}
      >
        <button
          type="button"
          class={`btn ${showOrbits ? 'btn--active' : ''}`}
          onClick={() => setShowOrbits((v) => !v)}
          title="Toggle centroid orbits of all objects"
        >
          <span style={{ fontSize: '13px', lineHeight: 1 }}>⌖</span>
          <span>Orbits</span>
        </button>
        <button
          type="button"
          class={`btn ${showTangents ? 'btn--active' : ''}`}
          onClick={() => setShowTangents((v) => !v)}
          title="Toggle tangent velocity vectors & 2nd-order curvature stop barriers"
        >
          <span style={{ fontSize: '12px', fontWeight: 700, lineHeight: 1 }}>∂²</span>
          <span>Tangents</span>
        </button>
      </div>

      {error ? (
        <div class="viewer__empty" style={{ color: 'var(--danger)', padding: '16px' }}>
          <span style={{ fontWeight: 600 }}>Python Error:</span>
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
            {error}
          </pre>
        </div>
      ) : !scene || !currentData ? (
        <div class="viewer__empty">
          <span>no output yet</span>
          <span>press run</span>
        </div>
      ) : mode === '3d' ? (
        <div class="viewer__empty">
          <span>3D view skipped for now</span>
          <button type="button" class="btn btn--primary" onClick={() => setMode('2d')}>
            Switch to 2D SVG
          </button>
        </div>
      ) : (
        <svg
          viewBox={`0 0 ${size.w} ${size.h}`}
          style={{
            width: '100%',
            height: '100%',
            display: 'block',
            cursor: panStartRef.current ? 'grabbing' : 'grab',
            userSelect: 'none',
          }}
          onPointerDown={onCanvasPointerDown}
          onPointerMove={onCanvasPointerMove}
          onPointerUp={onCanvasPointerUp}
          onWheel={onWheel}
        >
          <defs>
            {/* Engineering Ground Hatch Pattern */}
            <pattern id="cadGroundHatch" width="8" height="8" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
              <line x1="0" y1="0" x2="0" y2="8" stroke="var(--cad-ground-hatch)" strokeWidth="1.2" strokeOpacity="0.4" />
            </pattern>
          </defs>

          {/* Technical Engineering Grid */}
          <g stroke="var(--cad-grid)" strokeWidth="1" shapeRendering="crispEdges">
            {vGridLines.map((x) => {
              const [sx] = toScreen(x, 0)
              return <line key={`gx_${x}`} x1={Math.round(sx) + 0.5} y1={0} x2={Math.round(sx) + 0.5} y2={size.h} />
            })}
            {hGridLines.map((y) => {
              const [, sy] = toScreen(0, y)
              return <line key={`gy_${y}`} x1={0} y1={Math.round(sy) + 0.5} x2={size.w} y2={Math.round(sy) + 0.5} />
            })}
          </g>

          {/* Coordinate Axes */}
          {oy >= 0 && oy <= size.h && (
            <g>
              <line
                x1={0}
                y1={Math.round(oy) + 0.5}
                x2={size.w}
                y2={Math.round(oy) + 0.5}
                stroke="var(--cad-axis)"
                strokeWidth="1.5"
                shapeRendering="crispEdges"
              />
              <text
                x={size.w - 18}
                y={Math.round(oy) - 6}
                fill="var(--cad-axis-label)"
                fontSize="10"
                fontFamily="var(--font-mono)"
                fontWeight="600"
              >
                +X
              </text>
            </g>
          )}
          {ox >= 0 && ox <= size.w && (
            <g>
              <line
                x1={Math.round(ox) + 0.5}
                y1={0}
                x2={Math.round(ox) + 0.5}
                y2={size.h}
                stroke="var(--cad-axis)"
                strokeWidth="1.5"
                shapeRendering="crispEdges"
              />
              <text
                x={Math.round(ox) + 8}
                y={18}
                fill="var(--cad-axis-label)"
                fontSize="10"
                fontFamily="var(--font-mono)"
                fontWeight="600"
              >
                +Y
              </text>
            </g>
          )}

          {/* Origin Target Marker */}
          {ox >= -10 && ox <= size.w + 10 && oy >= -10 && oy <= size.h + 10 && (
            <g style={{ pointerEvents: 'none' }}>
              <circle cx={ox} cy={oy} r="6" fill="none" stroke="var(--cad-axis-label)" strokeWidth="1" strokeDasharray="2 2" />
              <line x1={ox - 9} y1={oy} x2={ox + 9} y2={oy} stroke="var(--cad-axis-label)" strokeWidth="1" />
              <line x1={ox} y1={oy - 9} x2={ox + 9} y2={oy} stroke="var(--cad-axis-label)" strokeWidth="1" />
              <text x={ox + 8} y={oy + 14} fill="var(--cad-axis-label)" fontSize="9" fontFamily="var(--font-mono)">
                (0,0)
              </text>
            </g>
          )}

          {/* Centroid Orbits Trajectory Paths */}
          {showOrbits &&
            scene.entities.map((ent) => {
              const isGround =
                ent.id.toLowerCase().includes('ground') ||
                ent.id.toLowerCase().startsWith('g')
              if (isGround) return null

              const pts =
                precomputedOrbits[ent.id]?.length && precomputedOrbits[ent.id].length > 4
                  ? precomputedOrbits[ent.id]
                  : dragTrails[ent.id]

              if (!pts || pts.length < 2) return null

              const screenPts = pts.map((p) => toScreen(p[0], p[1]))
              let pathD = `M ${screenPts[0][0].toFixed(1)} ${screenPts[0][1].toFixed(1)}`
              for (let i = 1; i < screenPts.length; i++) {
                pathD += ` L ${screenPts[i][0].toFixed(1)} ${screenPts[i][1].toFixed(1)}`
              }
              if (precomputedOrbits[ent.id]?.length > 4) {
                pathD += ' Z'
              }

              const isCurrentDragging = activeDrag === `rod:${ent.id}`
              const isHovered = hovered === `rod:${ent.id}`
              const orbitColor = isCurrentDragging || isHovered
                ? 'var(--cad-rod-drag-stroke)'
                : 'var(--cad-rod-stroke)'

              const r = currentData.rods[ent.id]
              const [curMx, curMy] = toScreen(
                (r.p1[0] + r.p2[0]) / 2,
                (r.p1[1] + r.p2[1]) / 2,
              )

              return (
                <g key={`orbit_${ent.id}`} style={{ pointerEvents: 'none' }}>
                  <path
                    d={pathD}
                    fill="none"
                    stroke={orbitColor}
                    strokeWidth="1.2"
                    strokeDasharray="4 3"
                    strokeOpacity={isHovered || isCurrentDragging ? 0.85 : 0.45}
                  />
                  {/* Current Centroid ⌖ symbol */}
                  <circle
                    cx={curMx}
                    cy={curMy}
                    r="3.5"
                    fill="none"
                    stroke={orbitColor}
                    strokeWidth="1"
                    strokeOpacity={0.8}
                  />
                  <circle cx={curMx} cy={curMy} r="1" fill={orbitColor} />
                </g>
              )
            })}

          {/* CAD Rod Links (Rect with Semicircular Arcs at Endpoints) */}
          {scene.entities.map((ent) => {
            const r = currentData.rods[ent.id]
            const [x1, y1] = toScreen(r.p1[0], r.p1[1])
            const [x2, y2] = toScreen(r.p2[0], r.p2[1])
            const mx = (x1 + x2) / 2
            const my = (y1 + y2) / 2
            const isGround = entIsGround(ent.id)
            const isDragging = activeDrag === `rod:${ent.id}`
            const isHovered = hovered === `rod:${ent.id}`
            const isViolated = violations.violatedRods.has(ent.id)
            const showLabel = isHovered || isDragging || isViolated

            const curLen = Math.hypot(r.p2[0] - r.p1[0], r.p2[1] - r.p1[1])
            const delta = curLen - ent.length
            const deltaText = `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`

            const rodRadius = 11 // half-width of obround slot link
            const pathD = getCapsulePath(x1, y1, x2, y2, rodRadius)
            const hitPathD = getCapsulePath(x1, y1, x2, y2, rodRadius + 8)

            const strokeColor = isViolated
              ? 'var(--cad-violation-stroke, #ef4444)'
              : isGround
                ? 'var(--cad-ground-stroke)'
                : isDragging || isHovered
                  ? 'var(--cad-rod-drag-stroke)'
                  : 'var(--cad-rod-stroke)'
            const fillColor = isViolated
              ? 'var(--cad-violation-fill, rgba(239, 68, 68, 0.22))'
              : isGround
                ? 'var(--cad-ground-fill)'
                : isDragging || isHovered
                  ? 'var(--cad-rod-drag-fill)'
                  : 'var(--cad-rod-fill)'

            return (
              <g
                key={ent.id}
                style={{ cursor: isGround ? 'default' : isDragging ? 'grabbing' : 'move' }}
                onPointerEnter={() => setHovered(`rod:${ent.id}`)}
                onPointerLeave={() => setHovered((h) => (h === `rod:${ent.id}` ? null : h))}
                onPointerDown={(e) => onRodPointerDown(e, ent.id)}
                onPointerMove={(e) => onRodPointerMove(e, ent.id)}
                onPointerUp={onRodPointerUp}
              >
                {/* Wide invisible hit area */}
                <path d={hitPathD} fill="transparent" />

                {/* Ground Hatch Fill if grounded */}
                {isGround && (
                  <path d={pathD} fill="url(#cadGroundHatch)" opacity="0.65" />
                )}

                {/* CAD Capsule Link Body (Rect with Semicircle Arcs) */}
                <path
                  d={pathD}
                  fill={fillColor}
                  stroke={strokeColor}
                  strokeWidth={isViolated ? '2' : isDragging || isHovered ? '2' : '1.5'}
                />

                {/* Engineering Centerline Axis */}
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={isViolated ? '#ef4444' : strokeColor}
                  strokeWidth={isViolated ? '1.5' : '1'}
                  strokeDasharray={isViolated ? '3 3' : '6 3'}
                  strokeOpacity={isViolated ? '0.9' : '0.6'}
                />

                {/* Concentric Pivot End Holes */}
                <circle
                  cx={x1}
                  cy={y1}
                  r="4"
                  fill="var(--cad-bg)"
                  stroke={isViolated ? '#ef4444' : strokeColor}
                  strokeWidth="1"
                />
                <circle
                  cx={x2}
                  cy={y2}
                  r="4"
                  fill="var(--cad-bg)"
                  stroke={isViolated ? '#ef4444' : strokeColor}
                  strokeWidth="1"
                />

                {/* CAD Technical Label Badge */}
                {showLabel && (
                  <g style={{ pointerEvents: 'none', userSelect: 'none' }}>
                    <rect
                      x={mx - (isViolated ? 34 : 22)}
                      y={my - 23}
                      width={isViolated ? 68 : 44}
                      height="17"
                      rx="3"
                      fill={
                        isViolated
                          ? 'var(--cad-violation-badge-bg, #fee2e2)'
                          : 'var(--cad-badge-bg)'
                      }
                      fillOpacity="0.95"
                      stroke={
                        isViolated
                          ? 'var(--cad-violation-badge-border, #f87171)'
                          : 'var(--cad-badge-border)'
                      }
                      strokeWidth="1"
                    />
                    <text
                      x={mx}
                      y={my - 11}
                      textAnchor="middle"
                      fill={
                        isViolated
                          ? 'var(--cad-violation-badge-fg, #b91c1c)'
                          : isGround
                            ? 'var(--cad-axis-label)'
                            : 'var(--cad-badge-fg)'
                      }
                      fontSize="10"
                      fontWeight="600"
                      fontFamily="var(--font-mono)"
                    >
                      {isViolated ? `${ent.id} Δ${deltaText}` : ent.id}
                    </text>
                  </g>
                )}
              </g>
            )
          })}

          {/* 1st-Order Tangent Space & 2nd-Order Obstruction Glyphs */}
          {showTangents &&
            scene.analysis?.nodes?.map((node) => {
              if (node.fixed || !node.tangents?.length) return null

              let wx = node.pos[0]
              let wy = node.pos[1]
              for (const jid of node.joint_ids) {
                if (currentData.joints[jid]) {
                  wx = currentData.joints[jid][0]
                  wy = currentData.joints[jid][1]
                  break
                }
              }

              const [nx, ny] = toScreen(wx, wy)

              return (
                <g key={`tangent_node_${node.id}`} style={{ pointerEvents: 'none', userSelect: 'none' }}>
                  {node.tangents.map((t, tidx) => {
                    const vx = t.vector[0]
                    const vy = t.vector[1]
                    const vlen = Math.hypot(vx, vy)
                    if (vlen < 0.01) return null

                    const dirX = vx / vlen
                    const dirY = vy / vlen
                    // In screen coords, SVG +Y points downward, so invert vy
                    const screenVx = dirX
                    const screenVy = -dirY
                    const arrowLen = 54

                    const pEndX = nx + screenVx * arrowLen
                    const pEndY = ny + screenVy * arrowLen
                    const pStartX = nx - screenVx * arrowLen
                    const pStartY = ny - screenVy * arrowLen

                    // Perpendicular direction in screen coordinates
                    const perpX = -screenVy
                    const perpY = screenVx
                    const barSpan = 15

                    if (t.obstructed) {
                      // Dead-center phantom tangent: obstructed at 2nd order
                      return (
                        <g key={`t_${tidx}`}>
                          {/* Pulsating dashed bidirectional phantom velocity line */}
                          <line
                            x1={pStartX}
                            y1={pStartY}
                            x2={pEndX}
                            y2={pEndY}
                            stroke="#f43f5e"
                            strokeWidth="2.2"
                            strokeDasharray="4 3"
                          />

                          {/* Perpendicular Stop Barrier at positive tip (⊥) */}
                          <line
                            x1={pEndX - perpX * barSpan}
                            y1={pEndY - perpY * barSpan}
                            x2={pEndX + perpX * barSpan}
                            y2={pEndY + perpY * barSpan}
                            stroke="#e11d48"
                            strokeWidth="3.5"
                            strokeLinecap="square"
                          />

                          {/* Perpendicular Stop Barrier at negative tip (⊥) */}
                          <line
                            x1={pStartX - perpX * barSpan}
                            y1={pStartY - perpY * barSpan}
                            x2={pStartX + perpX * barSpan}
                            y2={pStartY + perpY * barSpan}
                            stroke="#e11d48"
                            strokeWidth="3.5"
                            strokeLinecap="square"
                          />

                          {/* Central Stop Symbol & Curvature Mismatch Badge */}
                          <g transform={`translate(${pEndX + screenVx * 10}, ${pEndY + screenVy * 10})`}>
                            <rect
                              x="-45"
                              y="-11"
                              width="90"
                              height="17"
                              rx="3"
                              fill="var(--cad-violation-badge-bg, #fee2e2)"
                              stroke="#f43f5e"
                              strokeWidth="1"
                              fillOpacity="0.95"
                            />
                            <text
                              x="0"
                              y="1"
                              textAnchor="middle"
                              fill="#b91c1c"
                              fontSize="9.5"
                              fontWeight="700"
                              fontFamily="var(--font-mono)"
                            >
                              ⊥ 2nd-order lock
                            </text>
                          </g>
                        </g>
                      )
                    } else {
                      // Genuine continuous free-motion tangent direction
                      const headSize = 8
                      const leftX = pEndX - screenVx * headSize + perpX * (headSize * 0.6)
                      const leftY = pEndY - screenVy * headSize + perpY * (headSize * 0.6)
                      const rightX = pEndX - screenVx * headSize - perpX * (headSize * 0.6)
                      const rightY = pEndY - screenVy * headSize - perpY * (headSize * 0.6)

                      return (
                        <g key={`t_${tidx}`}>
                          <line
                            x1={nx}
                            y1={ny}
                            x2={pEndX}
                            y2={pEndY}
                            stroke="#10b981"
                            strokeWidth="2.2"
                          />
                          <polygon
                            points={`${pEndX},${pEndY} ${leftX},${leftY} ${rightX},${rightY}`}
                            fill="#10b981"
                          />
                          <g transform={`translate(${pEndX + screenVx * 10}, ${pEndY + screenVy * 10})`}>
                            <rect
                              x="-28"
                              y="-10"
                              width="56"
                              height="16"
                              rx="3"
                              fill="#ecfdf5"
                              stroke="#34d399"
                              strokeWidth="1"
                              fillOpacity="0.95"
                            />
                            <text
                              x="0"
                              y="2"
                              textAnchor="middle"
                              fill="#065f46"
                              fontSize="9"
                              fontWeight="600"
                              fontFamily="var(--font-mono)"
                            >
                              v (DOF {t.basis_idx + 1})
                            </text>
                          </g>
                        </g>
                      )
                    }
                  })}
                </g>
              )
            })}

          {/* CAD Precision Point Joints */}
          {scene.joints.map((j) => {
            const pos = currentData.joints[j.id]
            const [jx, jy] = toScreen(pos[0], pos[1])
            const isDragging = activeDrag === `joint:${j.id}`
            const isHovered = hovered === `joint:${j.id}`
            const isFixed = fixedJoints.has(j.id)
            const isViolated = violations.violatedJoints.has(j.id)
            const showLabel = isHovered || isDragging || isViolated

            const pinColor = isViolated
              ? '#ef4444'
              : isDragging
                ? 'var(--cad-joint-drag-pin)'
                : isFixed
                  ? 'var(--cad-joint-fixed-pin)'
                  : 'var(--cad-joint-pin)'
            const ringStroke = isViolated
              ? '#ef4444'
              : isDragging || isHovered
                ? 'var(--cad-joint-drag-pin)'
                : isFixed
                  ? 'var(--cad-joint-fixed-ring)'
                  : 'var(--cad-joint-ring)'

            return (
              <g
                key={j.id}
                style={{ cursor: isFixed ? 'default' : isDragging ? 'grabbing' : 'grab' }}
                onPointerEnter={() => setHovered(`joint:${j.id}`)}
                onPointerLeave={() => setHovered((h) => (h === `joint:${j.id}` ? null : h))}
                onPointerDown={(e) => onJointPointerDown(e, j.id)}
                onPointerMove={(e) => onJointPointerMove(e, j.id)}
                onPointerUp={onJointPointerUp}
              >
                {/* Wide invisible hit area */}
                <circle cx={jx} cy={jy} r="18" fill="transparent" />

                {/* Active Drag, Hover, or Violation Halo */}
                {(isDragging || isHovered || isViolated) && (
                  <circle
                    cx={jx}
                    cy={jy}
                    r="15"
                    fill="none"
                    stroke={isViolated ? '#ef4444' : 'var(--cad-rod-drag-stroke)'}
                    strokeWidth={isViolated ? '1.8' : '1.5'}
                    strokeDasharray="3 3"
                  />
                )}

                {/* Outer Bearing Flange Ring */}
                <circle
                  cx={jx}
                  cy={jy}
                  r="7.5"
                  fill="var(--cad-bg)"
                  stroke={ringStroke}
                  strokeWidth={isViolated ? '2' : '1.5'}
                />

                {/* Precision Center Crosshair Ticks */}
                <line
                  x1={jx - 10}
                  y1={jy}
                  x2={jx - 4}
                  y2={jy}
                  stroke={isViolated ? '#ef4444' : 'var(--cad-joint-ticks)'}
                  strokeWidth="1"
                />
                <line
                  x1={jx + 4}
                  y1={jy}
                  x2={jx + 10}
                  y2={jy}
                  stroke={isViolated ? '#ef4444' : 'var(--cad-joint-ticks)'}
                  strokeWidth="1"
                />
                <line
                  x1={jx}
                  y1={jy - 10}
                  x2={jx}
                  y2={jy - 4}
                  stroke={isViolated ? '#ef4444' : 'var(--cad-joint-ticks)'}
                  strokeWidth="1"
                />
                <line
                  x1={jx}
                  y1={jy + 4}
                  x2={jx}
                  y2={jy + 10}
                  stroke={isViolated ? '#ef4444' : 'var(--cad-joint-ticks)'}
                  strokeWidth="1"
                />

                {/* Ground Anchor Mark if Fixed */}
                {isFixed && (
                  <g stroke="var(--cad-joint-fixed-pin)" strokeWidth="1" shapeRendering="crispEdges">
                    <line x1={jx - 8} y1={jy + 11} x2={jx + 8} y2={jy + 11} strokeWidth="1.5" />
                    <line x1={jx - 6} y1={jy + 11} x2={jx - 9} y2={jy + 15} />
                    <line x1={jx - 1} y1={jy + 11} x2={jx - 4} y2={jy + 15} />
                    <line x1={jx + 4} y1={jy + 11} x2={jx + 1} y2={jy + 15} />
                  </g>
                )}

                {/* Central Metallic Pivot Pin */}
                <circle cx={jx} cy={jy} r="3.5" fill={pinColor} />

                {/* Monospace CAD Label */}
                {showLabel && (
                  <g style={{ pointerEvents: 'none', userSelect: 'none' }}>
                    <rect
                      x={jx + 9}
                      y={jy - 14}
                      width={Math.max(j.id.length * 8 + 10, 24)}
                      height="16"
                      rx="3"
                      fill={
                        isViolated
                          ? 'var(--cad-violation-badge-bg, #fee2e2)'
                          : 'var(--cad-badge-bg)'
                      }
                      fillOpacity="0.95"
                      stroke={
                        isViolated
                          ? 'var(--cad-violation-badge-border, #f87171)'
                          : 'var(--cad-badge-border)'
                      }
                      strokeWidth="1"
                    />
                    <text
                      x={jx + 14}
                      y={jy - 3}
                      fill={
                        isViolated
                          ? 'var(--cad-violation-badge-fg, #b91c1c)'
                          : isFixed
                            ? 'var(--cad-axis-label)'
                            : 'var(--fg)'
                      }
                      fontSize="10"
                      fontWeight="600"
                      fontFamily="var(--font-mono)"
                    >
                      {j.id}
                    </text>
                  </g>
                )}
              </g>
            )
          })}
        </svg>
      )}

      {/* Constraint Violation Status Pill */}
      {violations.violatedRods.size > 0 && (
        <div
          style={{
            position: 'absolute',
            bottom: '10px',
            right: '10px',
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            borderRadius: '4px',
            backgroundColor: 'var(--cad-violation-badge-bg, #fee2e2)',
            border: '1px solid var(--cad-violation-badge-border, #f87171)',
            color: 'var(--cad-violation-badge-fg, #b91c1c)',
            fontSize: '11px',
            fontWeight: '600',
            fontFamily: 'var(--font-mono)',
            boxShadow: 'var(--shadow-pop)',
            pointerEvents: 'none',
          }}
        >
          <span style={{ fontSize: '13px' }}>⚠</span>
          <span>
            Constraint Violation: {violations.violatedRods.size} link{violations.violatedRods.size > 1 ? 's' : ''} (Δmax {violations.maxError.toFixed(2)})
          </span>
        </div>
      )}
    </div>
  )
}
