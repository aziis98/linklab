import type { SceneData } from './viewer'

export interface LinkageNode {
  id: number
  x: number
  y: number
  fixed: boolean
  jointIds: string[]
  rodEndpoints: Array<{ rodId: string; end: 'p1' | 'p2' }>
}

export interface LinkageEdge {
  nodeA: number
  nodeB: number
  length: number
  rodId: string
}

export interface LinkageGraph {
  nodes: LinkageNode[]
  edges: LinkageEdge[]
  jointToNode: Map<string, number>
  rodEndToNode: Map<string, number> // key: `${rodId}:${end}`
}

export interface SolverResult {
  joints: Record<string, [number, number]>
  rods: Record<string, { p1: [number, number]; p2: [number, number] }>
}

class DisjointSet {
  parent: Map<string, string> = new Map()

  find(x: string): string {
    if (!this.parent.has(x)) this.parent.set(x, x)
    const p = this.parent.get(x)!
    if (p !== x) {
      const root = this.find(p)
      this.parent.set(x, root)
      return root
    }
    return p
  }

  union(a: string, b: string): void {
    const ra = this.find(a)
    const rb = this.find(b)
    if (ra !== rb) {
      this.parent.set(ra, rb)
    }
  }
}

export function buildLinkageGraph(
  scene: SceneData,
  current?: SolverResult | null,
): LinkageGraph {
  const dsu = new DisjointSet()
  const fixedPositions = new Map<string, [number, number]>()

  // Register all rod endpoints
  scene.entities.forEach((ent) => {
    const isGround = ent.id.toLowerCase().includes('ground') || ent.id.toLowerCase().startsWith('g')
    const k1 = `rod:${ent.id}:p1`
    const k2 = `rod:${ent.id}:p2`
    dsu.find(k1)
    dsu.find(k2)

    if (isGround) {
      const fix1 = `fixed:ground:${ent.id}:p1`
      const fix2 = `fixed:ground:${ent.id}:p2`
      fixedPositions.set(fix1, [ent.p1[0], ent.p1[1]])
      fixedPositions.set(fix2, [ent.p2[0], ent.p2[1]])
      dsu.union(k1, fix1)
      dsu.union(k2, fix2)
    }
  })

  // Register joints and connections
  scene.joints.forEach((j) => {
    const jk = `joint:${j.id}`
    dsu.find(jk)

    // Entity A
    if (j.entity_a) {
      const ptA = j.point_a === 'b' ? 'p2' : 'p1'
      dsu.union(jk, `rod:${j.entity_a}:${ptA}`)
    } else {
      const fixA = `fixed:joint:${j.id}`
      fixedPositions.set(fixA, [j.pos[0], j.pos[1]])
      dsu.union(jk, fixA)
    }

    // Entity B
    if (j.entity_b) {
      const ptB = j.point_b === 'b' ? 'p2' : 'p1'
      dsu.union(jk, `rod:${j.entity_b}:${ptB}`)
    } else {
      const fixB = `fixed:joint:${j.id}`
      fixedPositions.set(fixB, [j.pos[0], j.pos[1]])
      dsu.union(jk, fixB)
    }
  })

  // Group keys by root
  const groups = new Map<string, string[]>()
  for (const ent of scene.entities) {
    const k1 = `rod:${ent.id}:p1`
    const k2 = `rod:${ent.id}:p2`
    const r1 = dsu.find(k1)
    const r2 = dsu.find(k2)
    if (!groups.has(r1)) groups.set(r1, [])
    groups.get(r1)!.push(k1)
    if (!groups.has(r2)) groups.set(r2, [])
    groups.get(r2)!.push(k2)
  }
  for (const j of scene.joints) {
    const jk = `joint:${j.id}`
    const r = dsu.find(jk)
    if (!groups.has(r)) groups.set(r, [])
    groups.get(r)!.push(jk)
  }
  for (const fixKey of fixedPositions.keys()) {
    const r = dsu.find(fixKey)
    if (!groups.has(r)) groups.set(r, [])
    groups.get(r)!.push(fixKey)
  }

  // Deduplicate and build nodes
  const nodes: LinkageNode[] = []
  const jointToNode = new Map<string, number>()
  const rodEndToNode = new Map<string, number>()

  for (const [, rawKeys] of groups.entries()) {
    const keys = Array.from(new Set(rawKeys))
    const isFixed = keys.some((k) => k.startsWith('fixed:'))
    let x = 0
    let y = 0
    let foundPos = false

    if (isFixed) {
      for (const k of keys) {
        if (fixedPositions.has(k)) {
          const p = fixedPositions.get(k)!
          x = p[0]
          y = p[1]
          foundPos = true
          break
        }
      }
    }

    if (!foundPos) {
      // Find from current or scene
      for (const k of keys) {
        if (k.startsWith('joint:')) {
          const jid = k.slice(6)
          if (current?.joints[jid]) {
            ;[x, y] = current.joints[jid]
            foundPos = true
            break
          }
          const jObj = scene.joints.find((j) => j.id === jid)
          if (jObj) {
            ;[x, y] = [jObj.pos[0], jObj.pos[1]]
            foundPos = true
            break
          }
        } else if (k.startsWith('rod:')) {
          const parts = k.split(':')
          const rid = parts[1]
          const end = parts[2] as 'p1' | 'p2'
          if (current?.rods[rid]) {
            ;[x, y] = current.rods[rid][end]
            foundPos = true
            break
          }
          const rObj = scene.entities.find((e) => e.id === rid)
          if (rObj) {
            const pt = end === 'p1' ? rObj.p1 : rObj.p2
            ;[x, y] = [pt[0], pt[1]]
            foundPos = true
            break
          }
        }
      }
    }

    const nodeId = nodes.length
    const jointIds: string[] = []
    const rodEndpoints: Array<{ rodId: string; end: 'p1' | 'p2' }> = []

    for (const k of keys) {
      if (k.startsWith('joint:')) {
        const jid = k.slice(6)
        jointIds.push(jid)
        jointToNode.set(jid, nodeId)
      } else if (k.startsWith('rod:')) {
        const parts = k.split(':')
        const rid = parts[1]
        const end = parts[2] as 'p1' | 'p2'
        rodEndpoints.push({ rodId: rid, end })
        rodEndToNode.set(`${rid}:${end}`, nodeId)
      }
    }

    nodes.push({
      id: nodeId,
      x,
      y,
      fixed: isFixed,
      jointIds,
      rodEndpoints,
    })
  }

  // Build edges for non-ground rods
  const edges: LinkageEdge[] = []
  scene.entities.forEach((ent) => {
    const isGround = ent.id.toLowerCase().includes('ground') || ent.id.toLowerCase().startsWith('g')
    if (isGround) return

    const u = rodEndToNode.get(`${ent.id}:p1`)
    const v = rodEndToNode.get(`${ent.id}:p2`)
    if (u !== undefined && v !== undefined && u !== v) {
      edges.push({
        nodeA: u,
        nodeB: v,
        length: ent.length,
        rodId: ent.id,
      })
    }
  })

  return { nodes, edges, jointToNode, rodEndToNode }
}

export interface ConnectedComponent {
  id: number
  nodeIds: Set<number>
  edges: LinkageEdge[]
  drivingEdge: LinkageEdge | null
  anchorNode: LinkageNode | null
  crankNodeId: number | null
}

export function findConnectedComponents(graph: LinkageGraph): ConnectedComponent[] {
  const nodeToEdges = new Map<number, LinkageEdge[]>()
  for (const n of graph.nodes) nodeToEdges.set(n.id, [])
  for (const e of graph.edges) {
    nodeToEdges.get(e.nodeA)?.push(e)
    nodeToEdges.get(e.nodeB)?.push(e)
  }

  const visitedNodes = new Set<number>()
  const components: ConnectedComponent[] = []

  for (const n of graph.nodes) {
    const edges = nodeToEdges.get(n.id) || []
    if (edges.length === 0 || visitedNodes.has(n.id)) continue

    const compNodes = new Set<number>()
    const compEdges = new Set<LinkageEdge>()
    const queue: number[] = [n.id]
    visitedNodes.add(n.id)
    compNodes.add(n.id)

    while (queue.length > 0) {
      const cur = queue.shift()!
      const incident = nodeToEdges.get(cur) || []
      for (const edge of incident) {
        compEdges.add(edge)
        const other = edge.nodeA === cur ? edge.nodeB : edge.nodeA
        if (!visitedNodes.has(other)) {
          visitedNodes.add(other)
          compNodes.add(other)
          queue.push(other)
        }
      }
    }

    let drivingEdge: LinkageEdge | null = null
    let anchorNode: LinkageNode | null = null
    let crankNodeId: number | null = null

    // Priority 1: Edge connected to a fixed ground node
    for (const edge of compEdges) {
      const nA = graph.nodes[edge.nodeA]
      const nB = graph.nodes[edge.nodeB]
      if (nA.fixed && !nB.fixed) {
        drivingEdge = edge
        anchorNode = nA
        crankNodeId = edge.nodeB
        break
      } else if (nB.fixed && !nA.fixed) {
        drivingEdge = edge
        anchorNode = nB
        crankNodeId = edge.nodeA
        break
      }
    }

    // Priority 2: Floating component without ground node
    if (!drivingEdge && compEdges.size > 0) {
      const firstEdge = Array.from(compEdges)[0]
      drivingEdge = firstEdge
      anchorNode = graph.nodes[firstEdge.nodeA]
      crankNodeId = firstEdge.nodeB
    }

    components.push({
      id: components.length,
      nodeIds: compNodes,
      edges: Array.from(compEdges),
      drivingEdge,
      anchorNode,
      crankNodeId,
    })
  }

  return components
}

export function solveLinkage(
  graph: LinkageGraph,
  scene: SceneData,
  pinned: Map<number, { pos: [number, number]; weight?: number }>,
  iterations = 55,
): SolverResult {
  const pos: [number, number][] = graph.nodes.map((n) => [n.x, n.y])
  const invMass: number[] = graph.nodes.map((n, i) => {
    if (n.fixed) return 0.0
    const p = pinned.get(i)
    if (p) return p.weight ?? 0.05
    return 1.0
  })

  // Initialize pinned positions
  for (const [nodeId, p] of pinned.entries()) {
    if (!graph.nodes[nodeId].fixed) {
      pos[nodeId] = [p.pos[0], p.pos[1]]
    }
  }

  // PBD relaxation loop
  for (let iter = 0; iter < iterations; iter++) {
    for (const e of graph.edges) {
      const u = e.nodeA
      const v = e.nodeB
      const wU = invMass[u]
      const wV = invMass[v]
      const wSum = wU + wV
      if (wSum <= 1e-9) continue

      let dx = pos[v][0] - pos[u][0]
      let dy = pos[v][1] - pos[u][1]
      let dist = Math.hypot(dx, dy)
      if (dist < 1e-9) {
        dx = 1e-4
        dy = 0
        dist = 1e-4
      }

      const err = dist - e.length
      const nx = dx / dist
      const ny = dy / dist

      pos[u][0] += nx * err * (wU / wSum)
      pos[u][1] += ny * err * (wU / wSum)
      pos[v][0] -= nx * err * (wV / wSum)
      pos[v][1] -= ny * err * (wV / wSum)
    }
  }

  // Extract updated positions
  const outJoints: Record<string, [number, number]> = {}
  scene.joints.forEach((j) => {
    const nid = graph.jointToNode.get(j.id)
    if (nid !== undefined) {
      outJoints[j.id] = [pos[nid][0], pos[nid][1]]
    } else {
      outJoints[j.id] = [j.pos[0], j.pos[1]]
    }
  })

  const outRods: Record<string, { p1: [number, number]; p2: [number, number] }> = {}
  scene.entities.forEach((ent) => {
    const isGround = ent.id.toLowerCase().includes('ground') || ent.id.toLowerCase().startsWith('g')
    if (isGround) {
      outRods[ent.id] = {
        p1: [ent.p1[0], ent.p1[1]],
        p2: [ent.p2[0], ent.p2[1]],
      }
      return
    }

    const u = graph.rodEndToNode.get(`${ent.id}:p1`)
    const v = graph.rodEndToNode.get(`${ent.id}:p2`)
    const p1: [number, number] = u !== undefined ? [pos[u][0], pos[u][1]] : [ent.p1[0], ent.p1[1]]
    const p2: [number, number] = v !== undefined ? [pos[v][0], pos[v][1]] : [ent.p2[0], ent.p2[1]]
    outRods[ent.id] = { p1, p2 }
  })

  return { joints: outJoints, rods: outRods }
}

export interface OrbitResult {
  orbits: Record<string, [number, number][]>
  configs: SolverResult[]
}

export function computeLinkageOrbits(
  scene: SceneData,
  steps = 72,
): Record<string, [number, number][]> {
  const res = computeLinkageOrbitsWithConfigs(scene, steps)
  return res.orbits
}

export function computeLinkageOrbitsWithConfigs(
  scene: SceneData,
  steps = 72,
): OrbitResult {
  const orbits: Record<string, [number, number][]> = {}
  scene.entities.forEach((e) => {
    const isGround =
      e.id.toLowerCase().includes('ground') || e.id.toLowerCase().startsWith('g')
    if (!isGround) orbits[e.id] = []
  })

  const baseGraph = buildLinkageGraph(scene)
  const components = findConnectedComponents(baseGraph)
  const allConfigs: SolverResult[] = []

  // Probe every connected component independently
  for (const comp of components) {
    if (!comp.drivingEdge || !comp.anchorNode || comp.crankNodeId === null) continue

    const anchorX = comp.anchorNode.x
    const anchorY = comp.anchorNode.y
    const crankLen = comp.drivingEdge.length
    const crankNode = comp.crankNodeId

    const compRods = new Set(comp.edges.map((e) => e.rodId))
    const compOrbits: Record<string, [number, number][]> = {}
    for (const rId of compRods) {
      compOrbits[rId] = []
    }

    let prevSol: SolverResult | null = null

    // 1. Full 360-degree sweep
    for (let i = 0; i <= steps; i++) {
      const angle = (i * 2 * Math.PI) / steps
      const tx = anchorX + crankLen * Math.cos(angle)
      const ty = anchorY + crankLen * Math.sin(angle)

      const pinned = new Map<number, { pos: [number, number]; weight?: number }>()
      pinned.set(crankNode, { pos: [tx, ty], weight: 0.001 })

      const curGraph = buildLinkageGraph(scene, prevSol)
      const sol = solveLinkage(curGraph, scene, pinned, 45)

      let valid = true
      for (const edge of comp.edges) {
        const r = sol.rods[edge.rodId]
        if (r) {
          const d = Math.hypot(r.p2[0] - r.p1[0], r.p2[1] - r.p1[1])
          if (Math.abs(d - edge.length) > 0.04) {
            valid = false
            break
          }
        }
      }

      if (valid) {
        prevSol = sol
        allConfigs.push(sol)
        for (const rId of compRods) {
          const r = sol.rods[rId]
          if (r) {
            compOrbits[rId].push([(r.p1[0] + r.p2[0]) / 2, (r.p1[1] + r.p2[1]) / 2])
          }
        }
      }
    }

    // 2. If 360-degree sweep yielded few points (e.g. rocking mechanism),
    // sweep forward and backward from current configuration angle
    const sampleCount = Math.max(...Object.values(compOrbits).map((pts) => pts.length), 0)
    if (sampleCount < 10) {
      const initCrank = baseGraph.nodes[crankNode]
      const angle0 = Math.atan2(initCrank.y - anchorY, initCrank.x - anchorX)
      const arcSteps = steps / 2
      const maxDelta = Math.PI

      // Sweep forward
      prevSol = null
      for (let i = 1; i <= arcSteps; i++) {
        const angle = angle0 + (i / arcSteps) * maxDelta
        const tx = anchorX + crankLen * Math.cos(angle)
        const ty = anchorY + crankLen * Math.sin(angle)
        const pinned = new Map<number, { pos: [number, number]; weight?: number }>()
        pinned.set(crankNode, { pos: [tx, ty], weight: 0.001 })
        const sol = solveLinkage(buildLinkageGraph(scene, prevSol), scene, pinned, 45)
        let valid = true
        for (const edge of comp.edges) {
          const r = sol.rods[edge.rodId]
          if (r && Math.abs(Math.hypot(r.p2[0] - r.p1[0], r.p2[1] - r.p1[1]) - edge.length) > 0.04) {
            valid = false
            break
          }
        }
        if (!valid) break
        prevSol = sol
        allConfigs.push(sol)
        for (const rId of compRods) {
          const r = sol.rods[rId]
          if (r) compOrbits[rId].push([(r.p1[0] + r.p2[0]) / 2, (r.p1[1] + r.p2[1]) / 2])
        }
      }

      // Sweep backward
      prevSol = null
      for (let i = 1; i <= arcSteps; i++) {
        const angle = angle0 - (i / arcSteps) * maxDelta
        const tx = anchorX + crankLen * Math.cos(angle)
        const ty = anchorY + crankLen * Math.sin(angle)
        const pinned = new Map<number, { pos: [number, number]; weight?: number }>()
        pinned.set(crankNode, { pos: [tx, ty], weight: 0.001 })
        const sol = solveLinkage(buildLinkageGraph(scene, prevSol), scene, pinned, 45)
        let valid = true
        for (const edge of comp.edges) {
          const r = sol.rods[edge.rodId]
          if (r && Math.abs(Math.hypot(r.p2[0] - r.p1[0], r.p2[1] - r.p1[1]) - edge.length) > 0.04) {
            valid = false
            break
          }
        }
        if (!valid) break
        prevSol = sol
        allConfigs.push(sol)
        for (const rId of compRods) {
          const r = sol.rods[rId]
          if (r) compOrbits[rId].unshift([(r.p1[0] + r.p2[0]) / 2, (r.p1[1] + r.p2[1]) / 2])
        }
      }
    }

    // Merge into global orbits
    for (const rId of compRods) {
      if (compOrbits[rId]?.length) {
        orbits[rId] = compOrbits[rId]
      }
    }
  }

  return { orbits, configs: allConfigs }
}

export interface ConstraintViolations {
  violatedRods: Set<string>
  violatedJoints: Set<string>
  maxError: number
}

export function checkConstraintViolations(
  scene: SceneData,
  current: SolverResult,
  tol = 0.04,
): ConstraintViolations {
  const violatedRods = new Set<string>()
  const violatedJoints = new Set<string>()
  let maxError = 0

  // Check rod length constraints
  for (const ent of scene.entities) {
    const isGround =
      ent.id.toLowerCase().includes('ground') || ent.id.toLowerCase().startsWith('g')
    if (isGround) continue

    const r = current.rods[ent.id]
    if (!r) continue
    const curLen = Math.hypot(r.p2[0] - r.p1[0], r.p2[1] - r.p1[1])
    const err = Math.abs(curLen - ent.length)
    if (err > maxError) maxError = err
    if (err > Math.max(tol, ent.length * 0.02)) {
      violatedRods.add(ent.id)
    }
  }

  // Check joint coincidence constraints
  for (const j of scene.joints) {
    const jPos = current.joints[j.id]
    if (!jPos) continue

    let jointSeparated = false
    let ptA: [number, number] | null = null
    let ptB: [number, number] | null = null

    if (j.entity_a && current.rods[j.entity_a]) {
      const rA = current.rods[j.entity_a]
      ptA = j.point_a === 'b' ? rA.p2 : rA.p1
      if (Math.hypot(ptA[0] - jPos[0], ptA[1] - jPos[1]) > tol) {
        jointSeparated = true
      }
      if (violatedRods.has(j.entity_a)) {
        violatedJoints.add(j.id)
      }
    }
    if (j.entity_b && current.rods[j.entity_b]) {
      const rB = current.rods[j.entity_b]
      ptB = j.point_b === 'b' ? rB.p2 : rB.p1
      if (Math.hypot(ptB[0] - jPos[0], ptB[1] - jPos[1]) > tol) {
        jointSeparated = true
      }
      if (violatedRods.has(j.entity_b)) {
        violatedJoints.add(j.id)
      }
    }

    if (ptA && ptB && Math.hypot(ptA[0] - ptB[0], ptA[1] - ptB[1]) > tol) {
      jointSeparated = true
    }

    if (jointSeparated) {
      violatedJoints.add(j.id)
    }
  }

  return { violatedRods, violatedJoints, maxError }
}

export function solveInteractiveJoint(
  scene: SceneData,
  jointId: string,
  targetPos: [number, number],
  validConfigs: SolverResult[],
  currentLive: SolverResult | null,
  snapDistance = 0.75,
): { sol: SolverResult; snapped: boolean } {
  const baseGraph = buildLinkageGraph(scene, currentLive)
  const nodeId = baseGraph.jointToNode.get(jointId)
  if (nodeId === undefined || baseGraph.nodes[nodeId].fixed) {
    return { sol: currentLive || solveLinkage(baseGraph, scene, new Map()), snapped: true }
  }

  // 1. Test closest precomputed valid candidate configuration
  let bestCandidate: SolverResult | null = null
  let bestCandDist = Infinity
  for (const cfg of validConfigs) {
    const pt = cfg.joints[jointId]
    if (pt) {
      const d = Math.hypot(pt[0] - targetPos[0], pt[1] - targetPos[1])
      if (d < bestCandDist) {
        bestCandDist = d
        bestCandidate = cfg
      }
    }
  }

  // 2. Rigid Manifold Solve (Zero-violation priority)
  // Non-fixed nodes have equal mass (1.0), so distance constraints have hard stiffness
  const seedGraph = buildLinkageGraph(scene, bestCandDist < 1.4 ? bestCandidate : currentLive)
  const rigidPinned = new Map<number, { pos: [number, number]; weight?: number }>()
  rigidPinned.set(nodeId, { pos: targetPos, weight: 1.0 })

  const manifoldSol = solveLinkage(seedGraph, scene, rigidPinned, 75)
  const manifoldViolations = checkConstraintViolations(scene, manifoldSol, 0.04)

  const solvedJointPos = manifoldSol.joints[jointId] || targetPos
  const distToMouse = Math.hypot(solvedJointPos[0] - targetPos[0], solvedJointPos[1] - targetPos[1])

  // If constraints are satisfied and the mouse is within snap range of the manifold
  if (manifoldViolations.maxError < 0.04 && distToMouse <= snapDistance) {
    return { sol: manifoldSol, snapped: true }
  }

  // 3. Violation Mode: user is dragging beyond the reachable kinematic boundary
  // Displace the joint towards the mouse so the user experiences the constraint stretch
  const pullFactor = Math.min((distToMouse - snapDistance) * 0.8, 5.0)
  const dirX = (targetPos[0] - solvedJointPos[0]) / (distToMouse || 1)
  const dirY = (targetPos[1] - solvedJointPos[1]) / (distToMouse || 1)
  const stretchedPos: [number, number] = [
    solvedJointPos[0] + dirX * pullFactor,
    solvedJointPos[1] + dirY * pullFactor,
  ]

  const violSol: SolverResult = {
    joints: { ...manifoldSol.joints, [jointId]: stretchedPos },
    rods: { ...manifoldSol.rods },
  }

  for (const ent of scene.entities) {
    const isGround = ent.id.toLowerCase().includes('ground') || ent.id.toLowerCase().startsWith('g')
    if (isGround) continue
    const r = violSol.rods[ent.id]
    if (!r) continue
    const u = baseGraph.rodEndToNode.get(`${ent.id}:p1`)
    const v = baseGraph.rodEndToNode.get(`${ent.id}:p2`)
    const p1: [number, number] = u === nodeId ? stretchedPos : r.p1
    const p2: [number, number] = v === nodeId ? stretchedPos : r.p2
    violSol.rods[ent.id] = { p1, p2 }
  }

  return { sol: violSol, snapped: false }
}

export function solveInteractiveRod(
  scene: SceneData,
  rodId: string,
  delta: [number, number],
  currentLive: SolverResult | null,
  snapDistance = 0.75,
): { sol: SolverResult; snapped: boolean } {
  const baseGraph = buildLinkageGraph(scene, currentLive)
  const u = baseGraph.rodEndToNode.get(`${rodId}:p1`)
  const v = baseGraph.rodEndToNode.get(`${rodId}:p2`)

  const pinned = new Map<number, { pos: [number, number]; weight?: number }>()
  if (u !== undefined && !baseGraph.nodes[u].fixed) {
    pinned.set(u, {
      pos: [baseGraph.nodes[u].x + delta[0], baseGraph.nodes[u].y + delta[1]],
      weight: 0.8,
    })
  }
  if (v !== undefined && !baseGraph.nodes[v].fixed) {
    pinned.set(v, {
      pos: [baseGraph.nodes[v].x + delta[0], baseGraph.nodes[v].y + delta[1]],
      weight: 0.8,
    })
  }

  if (pinned.size === 0) {
    return { sol: currentLive || solveLinkage(baseGraph, scene, new Map()), snapped: true }
  }

  // Rigid manifold solve
  const manifoldSol = solveLinkage(baseGraph, scene, pinned, 70)
  const violations = checkConstraintViolations(scene, manifoldSol, 0.04)

  let maxDisplacement = 0
  for (const [, p] of pinned.entries()) {
    const r = manifoldSol.rods[rodId]
    if (r) {
      const d1 = Math.hypot(r.p1[0] - p.pos[0], r.p1[1] - p.pos[1])
      const d2 = Math.hypot(r.p2[0] - p.pos[0], r.p2[1] - p.pos[1])
      maxDisplacement = Math.max(maxDisplacement, Math.min(d1, d2))
    }
  }

  if (violations.maxError < 0.04 && maxDisplacement <= snapDistance) {
    return { sol: manifoldSol, snapped: true }
  }

  // Violation mode: translate rod towards drag direction
  const pullDist = maxDisplacement - snapDistance
  const pullScale = Math.min(pullDist * 0.8, 4.0) / (maxDisplacement || 1)
  const violSol: SolverResult = {
    joints: { ...manifoldSol.joints },
    rods: { ...manifoldSol.rods },
  }

  const curRod = violSol.rods[rodId]
  if (curRod) {
    const shiftedP1: [number, number] = [curRod.p1[0] + delta[0] * pullScale, curRod.p1[1] + delta[1] * pullScale]
    const shiftedP2: [number, number] = [curRod.p2[0] + delta[0] * pullScale, curRod.p2[1] + delta[1] * pullScale]
    violSol.rods[rodId] = { p1: shiftedP1, p2: shiftedP2 }
    if (u !== undefined && baseGraph.nodes[u].jointIds[0]) {
      violSol.joints[baseGraph.nodes[u].jointIds[0]] = shiftedP1
    }
    if (v !== undefined && baseGraph.nodes[v].jointIds[0]) {
      violSol.joints[baseGraph.nodes[v].jointIds[0]] = shiftedP2
    }
  }

  return { sol: violSol, snapped: false }
}

export function snapToNearestStableConfig(
  scene: SceneData,
  current: SolverResult | null,
  validConfigs: SolverResult[],
): SolverResult {
  if (!current) {
    const baseGraph = buildLinkageGraph(scene)
    return solveLinkage(baseGraph, scene, new Map(), 80)
  }

  const violations = checkConstraintViolations(scene, current, 0.04)

  // 1. If already valid (<0.04 max error), run a clean relaxation pass to ensure exact rigid link lengths
  if (violations.maxError < 0.04) {
    const refinedGraph = buildLinkageGraph(scene, current)
    return solveLinkage(refinedGraph, scene, new Map(), 60)
  }

  // 2. If in violation mode, find the closest certified valid configuration from validConfigs
  let bestCandidate: SolverResult | null = null
  let minCost = Infinity

  for (const cfg of validConfigs) {
    let cost = 0
    for (const ent of scene.entities) {
      if (ent.id.toLowerCase().includes('ground') || ent.id.toLowerCase().startsWith('g')) continue
      const curR = current.rods[ent.id]
      const cfgR = cfg.rods[ent.id]
      if (curR && cfgR) {
        cost += Math.hypot(curR.p1[0] - cfgR.p1[0], curR.p1[1] - cfgR.p1[1]) ** 2
        cost += Math.hypot(curR.p2[0] - cfgR.p2[0], curR.p2[1] - cfgR.p2[1]) ** 2
      }
    }
    for (const j of scene.joints) {
      const curJ = current.joints[j.id]
      const cfgJ = cfg.joints[j.id]
      if (curJ && cfgJ) {
        cost += Math.hypot(curJ[0] - cfgJ[0], curJ[1] - cfgJ[1]) ** 2
      }
    }
    if (cost < minCost) {
      minCost = cost
      bestCandidate = cfg
    }
  }

  // 3. Relax from the best candidate (or current) without any mouse pins to lock into the exact stable manifold
  const seed = bestCandidate || current
  const seedGraph = buildLinkageGraph(scene, seed)
  return solveLinkage(seedGraph, scene, new Map(), 90)
}

