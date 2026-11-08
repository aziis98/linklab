"""Four-bar linkage demo: ground link 3, moving links 2, 4, 3, ground
pivots 3 apart.

Linkage layout in the plane::

        A -------- 3 (ground) -------- B
        |                              |
        2 (crank)                 3 (rocker)
        |                              |
        C -------- 4 (coupler) -------- D

The three moving links are modelled as spatial rods with ball joints, then
constrained into the ground plane, which is how a planar mechanism actually
appears in a 3D CAD kernel.

The chosen lengths are a *change point*: the shortest plus the longest equals
the sum of the other two (2 + 4 = 3 + 3), so the crank is fully rotatable
(crank-rocker) but the assembly passes through a configuration where the
coupler and rocker are collinear.  That is the worst-conditioned point of the
sweep and :func:`main` reports it explicitly, because it is exactly the
situation where a tangent-space / free-motion analysis gets delicate.
"""

from __future__ import annotations

import numpy as np

from ..constraints import AlignAxis, Fixed, Planar, PointConstraint
from ..entities import Rod
from ..entity import World
from ..linalg import SE3
from ..system import Mechanism

GROUND = 3.0
CRANK = 2.0
COUPLER = 4.0
ROCKER = 3.0
PIVOT_A = np.array([0.0, 0.0, 0.0])
PIVOT_B = np.array([GROUND, 0.0, 0.0])

__all__ = ["build", "seed_layout", "circle_intersection", "main"]


def circle_intersection(
    c0: np.ndarray, r0: float, c1: np.ndarray, r1: float, branch: int = 1
) -> np.ndarray:
    """Intersect two circles in the z=0 plane; ``branch`` picks the solution.

    Returns the single point when the circles are tangent, so a change-point
    linkage produces a degenerate (repeated) answer rather than raising.
    """
    c0 = np.asarray(c0, float)[:2]
    c1 = np.asarray(c1, float)[:2]
    d = c1 - c0
    dist = float(np.linalg.norm(d))
    if dist < 1e-12 or dist > r0 + r1 or dist < abs(r0 - r1):
        raise ValueError(f"circles do not intersect: d={dist:.4f}, r0+r1={r0 + r1:.4f}")
    a = (r0 * r0 - r1 * r1 + dist * dist) / (2.0 * dist)
    h2 = max(r0 * r0 - a * a, 0.0)  # clamped: tangent circles give h == 0
    base = c0 + a * d / dist
    perp = np.array([-d[1], d[0]]) / dist
    xy = base + branch * np.sqrt(h2) * perp
    return np.array([xy[0], xy[1], 0.0])


def seed_layout(crank_angle: float = np.pi / 2.0, branch: int = 1) -> Mechanism:
    """Assemble the linkage exactly at a given crank angle, without solving.

    Placing the links geometrically means the demo starts from a residual of
    machine precision and the solver only has to track the sweep, which is a
    much better-conditioned use of it.
    """
    m = build()
    crank = m.entity("crank")
    coupler = m.entity("coupler")
    rocker = m.entity("rocker")

    a = PIVOT_A
    b = PIVOT_B
    c = a + CRANK * np.array([np.cos(crank_angle), np.sin(crank_angle), 0.0])
    # C must be COUPLER from D, and D must be ROCKER from B.
    d = circle_intersection(c, COUPLER, b, ROCKER, branch=branch)

    crank.place_between(a, c)
    coupler.place_between(c, d)
    rocker.place_between(d, b)
    # The driver has to agree with the geometry, or the seed is not a solution.
    _driver(m).set_direction(c - a)
    return m


def build() -> Mechanism:
    """The bare mechanism, with a geometrically sensible starting assembly."""
    world = World("world")
    world.add_point("a", PIVOT_A)
    world.add_point("b", PIVOT_B)

    ground = Rod(length=GROUND, name="ground")
    crank = Rod(length=CRANK, name="crank")
    coupler = Rod(length=COUPLER, name="coupler")
    rocker = Rod(length=ROCKER, name="rocker")

    m = Mechanism("four_bar")
    m.add(ground, crank, coupler, rocker)

    # Place the ground link, then weld it to the world frame.  The target
    # welds the ground's *centre of mass* to the midpoint of the two pivots
    # with identity rotation, which is exactly where place_between put it.
    ground.place_between(PIVOT_A, PIVOT_B)
    m.add_constraint(
        Fixed(world, ground, target=SE3(pos=0.5 * (PIVOT_A + PIVOT_B), rot=np.eye(3)))
    )

    # An open, non-degenerate starting assembly for the moving links.  It is
    # deliberately not a solution, so the solve has something to do.
    crank.place_between(PIVOT_A, PIVOT_A + CRANK * np.array([1.0, 0.0, 0.0]))
    c0 = crank.point("b")
    coupler.place_between(c0, c0 + COUPLER * np.array([0.0, 1.0, 0.0]))
    d0 = coupler.point("b")
    rocker.place_between(d0, PIVOT_B)

    # Four ball joints: ground-crank, crank-coupler, coupler-rocker, rocker-ground.
    m.add_constraint(PointConstraint(crank, "a", ground, "a"))
    m.add_constraint(PointConstraint(crank, "b", coupler, "a"))
    m.add_constraint(PointConstraint(coupler, "b", rocker, "a"))
    m.add_constraint(PointConstraint(rocker, "b", ground, "b"))

    # Keep the moving links in the ground plane.  The rocker's own end is
    # already pinned to a ground pivot at z=0, so its Planar row is exactly
    # redundant; the SVD rank in Mobility absorbs that, and the mobility
    # still comes out at 1.
    for rod in (crank, coupler, rocker):
        m.add_constraint(Planar(rod, "b"))

    # A driving constraint: aim the crank along a chosen in-plane direction.
    m.add_constraint(AlignAxis(crank, np.array([1.0, 0.0, 0.0]), axis="x"))

    m.add(world)
    return m


def _driver(mech: Mechanism) -> AlignAxis:
    for c in mech.constraints:
        if isinstance(c, AlignAxis):
            return c
    raise KeyError("no AlignAxis driver on this mechanism")


def main(n: int = 49) -> None:
    """Assemble, report mobility, then trace one crank revolution."""
    m = seed_layout()
    driver = _driver(m)

    print(f"=== {m.name} ===")
    for e in m.entities:
        print(f"  {e.name:<8} {type(e).__name__:<12} "
              f"{e.n_vars} vars, {e.n_dof} dof before constraints")

    r0 = m.residual()
    print(f"\nseed residual ||r|| = {np.linalg.norm(r0):.3e}")

    sol = m.solve()
    print(f"\n{sol.mobility}")
    print(f"residual after solve: {sol.residual_norm:.3e}  (success={sol.success})")

    if sol.mobility.dof != 1:
        print(f"\n!! expected 1 dof, got {sol.mobility.dof}; "
              f"the driver is over-specifying the crank")

    # --- trace a full crank revolution by continuation ------------------
    angles = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    guess = sol.x.copy()
    history: list[np.ndarray] = []
    conditioning: list[float] = []
    failed: list[float] = []

    print(f"\nsweeping the crank over 2*pi in {n} steps:")
    for th in angles:
        driver.set_direction([np.cos(th), np.sin(th), 0.0])
        step = m.solve(guess)
        guess = step.x
        if not step.success:
            failed.append(float(th))
            continue
        history.append(m.entity("coupler").point("b").copy())
        conditioning.append(float(np.linalg.svd(m.jac(), compute_uv=False)[-1]))

    print(f"  converged at {len(history)}/{n} steps")
    if failed:
        print(f"  FAILED at crank angles (rad): "
              f"{', '.join(f'{a:.3f}' for a in failed)}")
    if history:
        lo = float(np.min(conditioning))
        worst = angles[int(np.argmin(conditioning))]
        print(f"  worst conditioning {lo:.3e} at crank angle {worst:.4f} rad")
        print("  (the change point: coupler and rocker collinear)")

        # --- ASCII plot of the coupler tip -----------------------------
        _ascii_plot(history, PIVOT_A, PIVOT_B)
    return None


def _ascii_plot(points: list[np.ndarray], a: np.ndarray, b: np.ndarray, w: int = 61) -> None:
    """Crude top view of the traced path, with the ground pivots marked."""
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    x0, x1 = min(xs.min(), a[0], b[0]) - 0.5, max(xs.max(), a[0], b[0]) + 0.5
    y0, y1 = ys.min() - 0.5, ys.max() + 0.5

    def to_cell(p: np.ndarray) -> tuple[int, int]:
        cx = int(round((p[0] - x0) / (x1 - x0) * (w - 1)))
        cy = int(round((1.0 - (p[1] - y0) / (y1 - y0)) * (w // 2 - 1)))
        return cx, max(0, min(w // 2 - 1, cy))

    grid = [[" "] * w for _ in range(w // 2)]
    for p in points:
        cx, cy = to_cell(p)
        grid[cy][cx] = "*"
    for pivot, ch in ((a, "A"), (b, "B")):
        cx, cy = to_cell(pivot)
        grid[cy][cx] = ch
    print(f"\n  coupler tip path (top view, x ->, y up), {w}x{w // 2}:")
    for row in grid:
        print("    " + "".join(row))


if __name__ == "__main__":
    main()
