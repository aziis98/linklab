# Kinematics

Standalone Python scene construction, rigid constraint solving, and motion-space
exploration. The browser runs this same package inside a Pyodide worker; there is
no JavaScript constraint solver.

```sh
uv sync --extra render
uv run pytest
uv run python -m kinematics scene.py --solver topological --png scene.png --json result.json
```

## Construction and data

```python
from kinematics import build_scene, Engine, Session, Scene, render_png

source = '''
r1 = rod(left * 2, origin, id="r1")
r2 = rod(origin, right * 2, id="r2")
pin(r1.start, left * 2)
coincident(r1.end, r2.start)
pin(r2.end, right * 2)
'''
scene = build_scene(source, dimension=2)
plain_data = scene.to_dict()  # objects and constraints; exact scalars as strings
restored = Scene.from_dict(plain_data)
engine = Engine(restored)
engine.assemble()
result = engine.drag(["r1:b"], [[0, 0.2, 0]])
render_png(scene, result["configuration"], "scene.png")
```

DSL functions append records, without solving. Available constructors include
`rod(a, b, id=..., fixed=False)`, `ring(center, radius, id=..., fixed=False)`,
and `body({name: point, ...}, id=..., fixed=False)`. Rings are rigid circular
objects exposing `.center`, `.top`, and `.bottom` for hinge constraints and support dragging
at the clicked material point. The concentric-rings example fixes the outer ring
and joins the two top points with a hinged bar, giving two planar DOFs.
`.bottom` (also `.point("bottom")`) is the marked rim point opposite `.top`.
It is added only when referenced, and follows the affine relation
`bottom = 2 * center - top` in both the solver and drag preview. It adds no
independent motion to the ring. These names track material points, not world-space
highest/lowest positions after rotation; the general local-frame point API remains deferred.
Vectors support arithmetic; `origin`, `left`, `right`, `up`, `down`, `forward`,
`backward`, `Vec`, and exact `sqrt` are available. Use `sqrt(7)/2` for an exact
algebraic constant. Ordinary floats preserve their supplied decimal value, not an
inferred intended fraction. Use explicit `fixed=True`; names never ground objects.
Existing `constraint_point_point` calls remain aliases for `coincident`.

Constraints: `pin(point, position)` (or `pin(point)` to keep its initial position), `coincident(point, point)`,
`distance(point, point, length)`, `fixed(object)`,
`point_on_plane(point, origin, normal)`, `plane(target, origin, normal)`, and
`parallel(object.axis(), other.axis())`. `plane` accepts a point, a rod (both
endpoints), or a body (its material origin, X and Y points).
Bodies expose `.point(name)` and `.axis(name)`; rods expose `.start` and `.end`.
A body's named points are initial world coordinates; its material simplex initially
uses the world frame. A rigid body always retains a full material frame, while a
rod has no artificial axial-spin variable. Lengths and radii are fixed geometry.
The prior variable-shape/SE(3) package API is superseded.

Internally the solver embeds material points with immutable pairwise distances.
A rod needs two points, a planar body a noncollinear material triangle, and a
spatial body a tetrahedron. Analytic polynomial derivatives avoid rotation-chart
singularities. Redundant distance equations are allowed and handled by SVD.

## Solving and motion data

`Session.run(source, dimension=2, mode="numerical")` returns objects, constraints,
a configuration keyed by `object:point`, mobility diagnostics, and motion cells.
`Session.drag(keys, targets)` follows the current local branch.
`Session.select(index)` changes a certified assembly mode/chart. Numerical mode
has no component selector or component-discovery pass.
`Session.reassemble(keys, targets, weights=None)` explicitly searches for another
feasible assembly closer to the drag target. It never accepts an infeasible pose
and leaves unrelated components unchanged. Ordinary dragging remains continuous.
For object dragging, optional affine `weights` identify the clicked material
point; the objective follows that point rather than the object centre.
Every returned value is JSON-compatible; all displayed geometry uses 3D points.

The solver requires normalized residual below `1e-9`, uses bounded local steps,
and keeps the last feasible configuration if correction fails. Unreachable drag
targets remain ghosts in the UI. Numerical mode returns initial diagnostics immediately; Explore builds local motion paths incrementally. Multi-start projection is reserved for
explicit reassembly requests, not interpreted as connected-component analysis.
It does not certify completeness.
Higher-dimensional sets are labelled with an estimated tangent dimension and are
returned as samples, not falsely connected curves.

Mobility reports first-order nullity and second-order quadratic compatibility
forms over the complete null space. A definite obstruction form proves a local
second-order lock. Semidefinite forms restrict compatible velocities to their
kernels, so a locked component remains locked beside a separately mobile object. Otherwise compatibility may be inconclusive; no blocked-basis
count is presented as a true dimension. General combinations of indefinite forms
are not exhaustively classified.

Topological mode supports small planar rod distance graphs built through exact
circle intersections, including coincident circles, tangent circles, and simple
four-bars with rational critical polynomials. It isolates real critical values,
checks signs on root-free parameter intervals, and supplies endpoint incidences
and connected components. The tangent-half-angle chart seam is handled explicitly.
Exact descriptions/certificates are separate from floating-point display samples.
The circle-plus-point mixed-dimensional example is a proved geometric construction.

Unsupported algebraic coefficients, coincident four-bar closure centres, arbitrary
spatial mechanisms, and more complex graphs explicitly fall back to numerical
exploration. A ten-second deadline is checked between decomposition stages and
there is a 10,000-cell limit. Individual symbolic operations are not preemptible;
the browser Stop action terminates the worker for those cases. Certification
establishes topology for supported exact inputs, not interval-enclosed feasibility
of every floating display coordinate.

## Intersections and rendering

Immutable `Line`, `Segment`, `Circle`, `Plane`, and `Sphere` primitives and
`intersect(a, b)` are exported at package level and available directly in the DSL:

```python
hits = intersect(Circle((-1, 0), 2), Circle((1, 0), 2))
r = rod(left, hits.points[0])
```

`kinematics.core.geometry` also supplies construction-time `circle_circle`,
`line_line`, `segment_segment`, `line_circle` (coplanar 2D), `line_plane`,
`plane_plane`, `line_sphere`, `sphere_sphere`, and `plane_sphere`.
Results distinguish empty intersections, points, coincident objects, segments,
lines, and circles. Circle-circle calculations use exact algebra; the remaining
helpers use floating-point tolerances and do not issue topology certificates.
These helpers do not create persistent constraints or perform solid/mesh booleans.

`render_png(scene, configuration, path, camera=(35,25), overlays=())` uses the
optional Matplotlib extra. It supports planar and orthographic spatial rendering.
PNG rendering is not loaded by the browser worker.

## Browser controls and compatibility

The editor uses CodeMirror 6 with Python syntax highlighting, line numbers,
four-space indentation, bracket matching, and undo/redo in the existing theme.
Ctrl/Cmd+Enter runs the scene. Ctrl+Space or right-click opens DSL completion;
Tab/Shift+Tab moves between snippet fields, including linked names and IDs.
Escape dismisses completion; Escape then Tab lets keyboard focus leave the editor.
The catalog in `src/dsl-completions.ts` contains 37 object, constraint, geometry,
and scene snippets, including seven complete mechanism recipes. The completion
provider inspects Python syntax for direct rod/ring/body declarations, material
point names, constructor keywords, and constraint arguments; it does not execute
Python. Saved source stays plain Python, and file switches isolate undo history.

Drag nodes or objects to move the mechanism.
In 3D, left-drag the background to orbit and Shift-drag anywhere to pan. In 2D,
left-drag the background to pan; Shift-drag does nothing. Scroll zooms in either
dimension. Navigation preserves ongoing animation. Object drags use the view plane
through the grabbed point in 3D, or the XY plane in 2D. View presets are available.
In 3D the Orthographic/Perspective toolbar button toggles camera projection;
orthographic is the default and 2D always stays orthographic. Perspective picking
uses cursor rays intersecting the drag plane and accounts for depth when grabbing
a point along a rod. Grid lines, ghosts, orbit paths, and rods share near-plane
clipping. Camera changes do not call Python or alter the live configuration.
Selecting XY/XZ/YZ also restores orthographic projection. Spatial 3D views offer a
3D Renderer selector beside the Wander/Orbits controls: SVG (default) or Three.js.
Plane views always use SVG; returning to the spatial view restores the selected
renderer. Switching renderers preserves the camera, live pose, and animation.

Three.js is loaded on demand. It renders rods as shaded capsules, joints as
spheres, and rigid rings as toruses, with a hardware depth buffer for construction
geometry. HTML labels follow the shared projection and remain overlay text.
World grids, axes, ghost previews, orbits, and tangent guides reuse the SVG
background layer to preserve their existing style. Raycasting the visible meshes
feeds the same dragging, reassembly, and Python solver bridge as SVG picking.
Materials follow the light/dark theme. GPU resources are released on renderer or
scene changes; an unavailable or lost WebGL context falls back to SVG with an error.
Orbits distinguish isolated points and separate branches;
changing disconnected configurations uses the certified component/chart selector
or, in numerical mode, **Alt-drag an object and release** to reassemble near the ghost.
A separate Python least-squares preview holds the clicked material point under
the pointer and fits the entire construction. It can rotate and distort preview
geometry while leaving the accepted feasible configuration untouched. Rod-length
errors and joint separations blend continuously from blue toward red; fixed ground
objects stay fixed. This is a local least-violation fit, not a global optimum
certificate. The grid follows the projected world origin while panning and zooming.
Dropdowns use themed, keyboard-accessible listboxes.

The SVG renderer uses painter ordering in both projections, not a per-pixel depth buffer.
Individual rod edges, rings, joints, and labels are sorted back-to-front along the
camera ray, including edges belonging to the same rigid body. Rods use midpoint
depth, rings use center depth, joints use their positions, and labels use their
anchors. Stroke and fill passes remain grouped per element. There is no splitting
at intersections or per-pixel depth comparison.
Grid, ghost construction, and orbit paths are background layers; tangents are
foreground overlays. Intersections and interleaving objects can therefore have
incorrect occlusion. The separate roadmap preview also uses SVG: edges precede
depth-sorted vertex markers.

Edited saved scripts are never overwritten by bundled examples. The original
unmodified spatial-rotor example migrates to the upright version without its base
ring when files are loaded. New examples use `-v2`
filenames where their meaning changed. Old scripts with a `g1` ground rod must add
`fixed=True`; the original automatic name-based grounding has been removed.


For browser/native parity and interaction checks, with Vite already running:

```sh
uv sync --extra render --extra browser
uv run python ../scripts/check-browser.py --url http://localhost:5173
```

The browser check uses an installed Chromium executable (`--chromium` overrides
its path), exercises dragging and Stop, and saves screenshots under `/tmp/cad-review`.


## Scene dimension and spatial example

DSL scripts infer dimension from the initial configuration: geometry in the XY
plane uses two dimensions; nonzero Z coordinates use three. Use a directive for
an initially flat scene that should move spatially:

```python
scene_dimension(3)  # or scene_dimension(2)
base = rod(left, right, id="base", fixed=True)
arm = rod(origin, Vec(1, 0, 1), id="arm")
pin(arm.start, origin)
plane(arm, origin, up)  # constrain the arm to the XZ plane
```

`spatial-arm.py` is bundled in the editor. The corresponding standalone fixture
is `src/kinematics/examples/spatial.py`. Rotate the camera or select XZ view and
XZ drag plane. A camera view never changes simulation dimension.

The dimension dropdown defaults to Auto. An explicit UI/CLI/library dimension
is an override; without one, a script directive takes precedence over inference.
A forced 2D scene rejects nonplanar geometry rather than discarding Z coordinates.

## Incremental motion exploration

**Explore** in the viewport inspector starts a bounded numerical roadmap search
from the current feasible configuration. It does not seed disconnected assembly
modes or certify that the full manifold has been found. Scene execution no longer
waits for a synchronous numerical orbit sweep.

Nodes carry feasible full configurations and estimated local mobility; edges
carry corrected motion paths and accumulated configuration-space lengths. Circle
fronts close by tracing a connector to an existing node or by inserting a meeting
node inside an existing edge and splitting that edge. Proximity alone is never a
connection. Suspected singular regions and failed continuation attempts remain
visible as unresolved work. Higher-dimensional regions receive basis-direction
and seeded random-direction probes rather than a triangulation.

In regions with multiple DOFs, frontier selection prioritizes tangent predictors
farthest from existing samples in the normalized object-balanced configuration
metric. Each decision compares up to 48 recent and seeded random pending probes.
Singular junction exits receive priority, and one in eight regular decisions
services old pending work to avoid starving closures. Predicted novelty only
orders work: candidate configurations still require numerical correction and
connections still require continuation checks. One-dimensional tracing retains
its two-sided queue. This improves coverage but does not yet produce a mesh.

Deferred limitation: corrected edge samples and playback frames satisfy the
constraints numerically, but the continuous path between them is not certified.
Projection can potentially switch nearby branches, especially at coarse spacing
or singularities. Future work should address branch continuity and adaptive edge
validation; rigorous guarantees would require validated continuation. Mesh cleanup
or triangulation must not be described as solving this certification problem.

Distances use RMS material-point displacement divided by scene scale, weighting
moving objects equally. Coarse/Medium/Fine spacing is 1/0.5/0.25 (default Medium). Feasibility
still requires normalized residual below `1e-9`; the spacing is a coverage setting,
not a constraint tolerance. Advanced controls expose the bounded region radius,
active computation budget, node limit, maximum tangent turn, and allowed
correction/step ratio. Defaults are radius 2, 30 seconds, 2,000 nodes, 15 degrees,
and correction ratio 0.25. Step sizes shrink down to spacing/1000 when needed.
Individual projection calls are not preemptible; batches target 25 ms and yield
between attempts so live requests can interleave.

The progress bar measures **search budget used**, never percentage of the manifold
covered. Pause/Resume keeps the frontier. Extend Budget adds 30 seconds and 2,000
nodes. Selecting a finer spacing and Refine preserves the graph while adding
coverage. Orbits displays the streamed roadmap paths. The optional graph view is
an orbitable orthographic 3D PCA projection of full configuration coordinates.
Drag or use arrow keys to orbit, scroll or use +/- to zoom, and Home to reset.
Python freezes the three projection axes after 16 nodes; centering and scale
continue to update. Visual crossings do not imply graph junctions.

Sample & Build Tour chooses up to 10–20 well-spaced targets, default 16, using
randomized farthest-point sampling with graph shortest-path distances. A short
closed tour is constructed and improved by 2-opt, then expanded into actual graph
paths. Junctions and edges may be revisited as often as needed, with one incoming
and one outgoing path per visit. This is a TSP heuristic, not an optimum proof.
The current live pose must be connected to the graph before a tour can start.

Python prepares corrected animation frames in incremental batches with separate
progress. JS plays cached feasible poses without interpolating geometry, in a
45-second base loop with pause, scrub, and speed controls (0.75×, 1.5×, 3×,
and 6×; default 3×). Fit Motion frames all explored configurations. Use This Pose adopts a
paused frame; beginning a manual drag adopts it automatically. Reassembly, reset,
scene reruns, and assembly-mode changes invalidate old exploration work.

Start Wander generates a smooth random walk directly from the displayed pose,
without requiring an explored graph. Python transports the heading through local
tangent spaces and applies correlated random angular steering, with configurable
gentle/natural/frequent turns and a repeatable seed. Normalized object-balanced
speed is approximately constant; the same playback speed multipliers apply.
The viewport Wander button starts, pauses, or resumes the walk; detailed controls
remain in the inspector. Tangent overlays are off by default.
At one DOF there is no transverse steering direction, so motion continues forward
around the curve. Isolated poses are rejected; unresolved singularities or failed
continuation stop the walk rather than deliberately jumping to another branch.

Corrected, timestamped poses stream from Python in short batches into a bounded
JS buffer. Playback pauses time while buffering instead of interpolating infeasible
geometry or skipping ahead. Pause/Resume preserves the walk and its random state;
Stop keeps the displayed pose. Use Wander Pose adopts it into the live solver,
and beginning a manual drag does this automatically. Scene changes cancel old jobs.
The deferred continuous-edge certification limitation also applies to Wander.

The bundled `spatial-rotor.py` example is a tetrahedral rigid body pinned at one
corner above an upright fixed stand along the Y axis. It has three rotational DOFs
(orientation space SO(3)) and provides a bounded spatial Wander demonstration.
The `spatial-linked-pendulum.py` example joins two anchored rods at a shared joint
and attaches a third freely swinging rod there. It has three DOFs, with
configuration space S¹ × S².
The `concentric-rings-3d.py` preset joins concentric rings with top and bottom
braces. Its extended diameter linkage is singular in the unreduced equations,
while the inner ring retains one rotation about that diameter. Wander derives
fixed joint positions using exact equality in the triangle inequality for
stretched chains between fixed anchors, then continues on its private reduced
solver. Numerical proximity alone never authorizes these derived pins, so nearly
stretched chains are not frozen. The live scene and its constraint tolerances are
unchanged, and genuinely unresolved branch crossings remain rejected. This does
not address the deferred continuous-edge certification problem.

Standalone generation: `walk = Wander(engine, seed=0)` then call `walk.advance()`
for timed pose batches, or `walk.step()` for one pose. The supplied live engine
is unchanged.

Standalone use:

```python
from kinematics import Engine, Exploration, TourPreparation, build_scene

engine = Engine(build_scene(source))
engine.assemble()
job = Exploration(engine, spacing=0.5, radius=2, seconds=30, limit=2000)
while job.advance(budget_ms=25)["status"] == "running":
    pass  # native callers can yield to their own event loop here
snapshot = job.snapshot()  # JSON-compatible graph and diagnostics
job.pause()
# job.refine(0.25) or extend job.seconds/job.limit before further advance calls
preparation = TourPreparation(job, count=16, seed=0)
while not preparation.advance()["done"]:
    pass
frames = preparation.frames
```

The worker protocol additionally supplies scene/job revision checks and graph
deltas (new nodes, new edges, removed split edges, and stable IDs). Library jobs
hold a separate engine and never change the live mechanism while exploring or
preparing frames.

Browser regression, with the browser extra installed and Vite already on :5173:

```sh
uv run --project kinematics --extra browser python scripts/check-exploration-browser.py
```


To record all bundled examples in an isolated headless-browser context (no changes
to the user's browser storage), export their DSL sources and run:

```sh
bun -e 'import {BENCHMARK_EXAMPLES} from "./src/files.ts"; await Bun.write("/tmp/cad-scenes.json", JSON.stringify(BENCHMARK_EXAMPLES))'
PLAYWRIGHT_BROWSERS_PATH=/tmp/cad-playwright-browsers uv run --project kinematics --extra browser python -m playwright install ffmpeg
PLAYWRIGHT_BROWSERS_PATH=/tmp/cad-playwright-browsers uv run --project kinematics --extra browser python scripts/record-exploration.py --scenes /tmp/cad-scenes.json
```

The recorder uses installed Chromium plus FFmpeg and writes MP4s under
`/tmp/cad-videos`. Isolated configurations are labelled as having no continuous
motion; the recorder does not invent a tour for them. The local chart corrector
fixes tangent coordinates during normal correction, preventing residual minimizers
from drifting along the manifold during exploration and frame preparation.
