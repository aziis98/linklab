# kinematics

Objects with reduced rigid motions, assembly constraints, and free-motion
(tangent space) analysis. Standalone `uv` + `scipy` module.

## Install and run

```bash
uv sync
uv run pytest -q
uv run four-bar
```

## Model

An **entity** is anything that owns a contiguous block of scalars. The
protocol is deliberately thin — `vars()` returns the numbers, everything
else derives from them:

```python
class Entity(Protocol):
    def vars(self) -> np.ndarray: ...
    def set_vars(self, v: np.ndarray) -> None: ...
```

Every entity lays its variables out as `[px, py, pz, rx, ry, rz, *shape]`,
where `(rx, ry, rz)` is a rotation vector applied by Rodrigues' formula.

| entity         | vars | dof | reduced motion                        |
| -------------- | ---- | --- | ------------------------------------- |
| `RigidObject`  | 6    | 6   | none, full SE(3)                      |
| `Rod`          | 7    | 5   | spin about its own axis               |
| `Circle`       | 7    | 5   | spin about its own normal             |
| `Sphere`       | 4    | 4   | full SO(3) orientation is a symmetry  |

The reduced-motion column is **not enforced**. A `Rod`'s position is its
centre of mass and its local x axis is the segment direction, so spinning
about that axis leaves the shape unchanged; that spin simply turns up as a
null direction of the assembly Jacobian. Nothing special is coded for it —
`dof` and `tangent_basis` pick it up because they work off a matrix rank
rather than a variable count.

A `World` is a fixed frame with zero variables, used as the partner of
ground features. Give it named points so joints read as
`PointConstraint(crank, "a", ground, "a")`.

## Constraints

| constraint          | eqs | meaning                                            |
| ------------------- | --- | -------------------------------------------------- |
| `Fixed`             | 6   | hold the relative pose of two entities              |
| `PointConstraint`   | 3   | two material points coincide                        |
| `Planar`            | 1   | material point lies in a plane (`+2` with `orientation=True`) |
| `AlignAxis`         | 2   | aim a body axis at a fixed direction                |
| `Distance`          | 1   | hold the distance between two material points       |
| `Value`             | 1   | pin one scalar variable (e.g. a rod length)         |

`Fixed`, `PointConstraint` and `Planar` are the three you asked for.
`AlignAxis` exists because the four-bar demo needs a driver, `Distance` and
`Value` because link lengths have to be held somewhere.

Every constraint exposes `residual()` and `jac(total)`. Jacobians are
analytic and are checked against central finite differences in
`tests/test_kinematics.py` — a sign error in the SE(3) log derivative would
otherwise hide behind a still-converging solve.

## Mobility

```python
m = seed_layout()
m.mobility()        # variables / equations / rank / dof / redundancy
m.dof()             # 1
m.tangent_basis()   # (n_vars, 1): the instantaneous free motion
```

`dof` is `n_vars - rank(J)` and redundancy is `n_eq - rank(J)`, both from a
single SVD. This matters: a planar loop is naturally over-specified, and a
row-count-based DOF would report `0` for a perfectly good one-DOF
mechanism. The four-bar demo deliberately keeps a redundant `Planar` row on
the rocker, where it duplicates the pin to a ground pivot, and the SVD
absorbs it.

`tangent_basis()` returns a basis of the null space of the constraint
Jacobian, so `x + eps * T` is a first-order feasible displacement. The
second-order error is what the null space does not capture — that is where
reach and curvature enter.

Pass `subset=` to search only part of the variable vector. Useful for
dropping the symmetry spins and shape variables, which are real null
directions of the constraint system but not interesting mechanisms.

## Demo: four-bar linkage

Ground 3, moving links 2, 4, 3, ground pivots 3 apart.

```
        A -------- 3 (ground) -------- B
        |                              |
        2 (crank)                 3 (rocker)
        |                              |
        C -------- 4 (coupler) -------- D
```

The moving links are spatial rods with ball joints, then constrained into
the ground plane, which is how a planar mechanism actually appears in a 3D
CAD kernel. `seed_layout` places the links geometrically so the assembly
starts at machine precision and the solver only has to track the sweep.

Those lengths are a **change point**: `2 + 4 = 3 + 3`. The crank is fully
rotatable (crank-rocker), but the linkage passes through a configuration
where coupler and rocker are collinear. The demo sweeps a full revolution
and reports the worst conditioning it sees, since that configuration is
exactly where a tangent-space analysis gets delicate.

Note also the crank angle `0` is itself dead: the two closure circles are
internally tangent there, so the assembly is singular. The demo seeds at
`pi/2` and works outward from there.

## Layout

```
src/kinematics/
  linalg.py       SO(3)/SE(3) exp, log, left/right Jacobians
  entity.py       Entity protocol, BaseEntity, World
  entities.py     RigidObject, Rod, Circle, Sphere
  constraints.py  Fixed, PointConstraint, Planar, AlignAxis, Distance, Value
  system.py       Mechanism: assembly, mobility, tangent_basis, solve
  examples/
    four_bar.py
tests/
```
