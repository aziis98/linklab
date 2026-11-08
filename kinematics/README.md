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
`rod(a, b, id=..., fixed=False)` and `body({name: point, ...}, id=..., fixed=False)`.
Vectors support arithmetic; `origin`, `left`, `right`, `up`, `down`, `forward`,
`backward`, `Vec`, and exact `sqrt` are available. Use `sqrt(7)/2` for an exact
algebraic constant. Ordinary floats preserve their supplied decimal value, not an
inferred intended fraction. Use explicit `fixed=True`; names never ground objects.
Existing `constraint_point_point` calls remain aliases for `coincident`.

Constraints: `pin(point, position)`, `coincident(point, point)`,
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
targets remain ghosts in the UI. Numerical mode traces local curves only. Multi-start projection is reserved for
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

The existing editor and theme remain. Drag nodes or rods, drag the background to
pan, Alt-drag to rotate the orthographic view, and scroll to zoom. View presets
and camera-plane/XY/XZ/YZ drag planes are available. Rotating a planar scene never
changes its constraints. Orbits distinguish isolated points and separate branches;
changing disconnected configurations uses the certified component/chart selector
or, in numerical mode, **Shift-drag and release** to reassemble near the ghost.
A separate Python least-squares preview holds the clicked material point under
the pointer and fits the entire construction. It can rotate and distort preview
geometry while leaving the accepted feasible configuration untouched. Rod-length
errors and joint separations blend continuously from blue toward red; fixed ground
objects stay fixed. This is a local least-violation fit, not a global optimum
certificate. The grid follows the projected world origin while panning and zooming.
Dropdowns use themed, keyboard-accessible listboxes.

Saved scripts are never overwritten by bundled examples. New examples use `-v2`
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
