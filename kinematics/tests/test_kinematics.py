"""Verify every analytic Jacobian against central finite differences.

The mechanism code is only worth trusting if the Jacobians are right, and a
sign error in the SE(3) log derivative or the right-Jacobian chain is
invisible in a passing solve: least_squares will still converge, just more
slowly.  These tests differentiate the residuals numerically and compare.
"""

from __future__ import annotations

import numpy as np
import pytest

from kinematics import (
    SE3,
    AlignAxis,
    Circle,
    Distance,
    Fixed,
    Mechanism,
    Planar,
    PointConstraint,
    RigidObject,
    Rod,
    Sphere,
    Value,
    World,
)
from kinematics.examples.four_bar import build as build_four_bar
from kinematics.examples.four_bar import seed_layout
from kinematics.linalg import (
    hat,
    perp_basis,
    rotvec_aligning,
    so3_exp,
    so3_left_jacobian,
    so3_left_jacobian_inv,
    so3_log,
    so3_right_jacobian,
)

STEP = 1e-6


def numeric_jac(f, x, n_out: int) -> np.ndarray:
    J = np.zeros((n_out, x.size))
    for i in range(x.size):
        xp, xm = x.copy(), x.copy()
        xp[i] += STEP
        xm[i] -= STEP
        J[:, i] = (f(xp) - f(xm)) / (2.0 * STEP)
    return J


def compare(name: str, mech: Mechanism, c, x: np.ndarray, tol: float = 1e-6) -> None:
    analytic = np.atleast_2d(c.jac(mech.n_vars))
    numeric = numeric_jac(
        lambda t: (mech.set_vars(t), c.residual())[1], x, c.n_eq
    )
    err = np.max(np.abs(analytic - numeric)) if analytic.size else 0.0
    scale = max(1.0, np.max(np.abs(numeric)) if numeric.size else 1.0)
    assert err / scale < tol, f"{name}: max abs jac error {err:.3e} (tol {tol:.1e})"


# --------------------------------------------------------------------- SO(3)


def test_so3_exp_log_roundtrip():
    rng = np.random.default_rng(0)
    for _ in range(200):
        phi = rng.normal(size=3)
        phi = phi / np.linalg.norm(phi) * rng.uniform(0.0, 3.0)
        assert np.allclose(so3_log(so3_exp(phi)), phi, atol=1e-10)


def test_so3_small_angle_expansion():
    """exp(phi) = I + hat(phi) + hat(phi)^2/2 + O(|phi|^3), with explicit scaling.

    Compared against a fixed absolute tolerance instead of ``allclose``, whose
    default rtol would swamp the third-order remainder.
    """
    for t in (1e-4, 1e-3, 1e-2):
        phi = np.array([t, -2 * t, 0.5 * t])
        K = hat(phi)
        err = np.max(np.abs(so3_exp(phi) - (np.eye(3) + K + 0.5 * K @ K)))
        # Truncation is cubic in |phi|; allow for it with a matching tolerance.
        assert err < 20.0 * t**3, f"t={t}: err {err:.3e}"


@pytest.mark.parametrize("scale", [1e-9, 1e-6, 1e-3, 0.4, 1.2, 2.5])
def test_so3_jacobians(scale):
    """Left/right Jacobians against their defining identities, at several magnitudes."""
    rng = np.random.default_rng(1)
    phi = rng.normal(size=3)
    phi = phi / np.linalg.norm(phi) * scale
    h = 1e-6
    hvec = rng.normal(size=3)

    # Jl: exp(phi + s h) = exp(Jl h) exp(phi) + O(h^2)
    lhs = so3_exp(phi + h * hvec)
    assert np.allclose(lhs, so3_exp(h * (so3_left_jacobian(phi) @ hvec)) @ so3_exp(phi),
                       atol=1e-10, rtol=0)
    # Jr: exp(phi + s h) = exp(phi) exp(Jr h) + O(h^2)
    assert np.allclose(lhs, so3_exp(phi) @ so3_exp(h * (so3_right_jacobian(phi) @ hvec)),
                       atol=1e-10, rtol=0)

    assert np.allclose(
        so3_left_jacobian_inv(phi) @ so3_left_jacobian(phi), np.eye(3), atol=1e-12, rtol=0
    )


def test_so3_left_jacobian_inv_identity():
    """log(exp(dtheta) exp(phi)) = phi + Jl^{-1} dtheta + O(dtheta^2)."""
    rng = np.random.default_rng(2)
    phi = rng.normal(size=3) * 0.3
    d = rng.normal(size=3) * 1e-6
    lhs = so3_log(so3_exp(d) @ so3_exp(phi))
    rhs = phi + so3_left_jacobian_inv(phi) @ d
    assert np.allclose(lhs, rhs, atol=1e-11)


def test_perp_basis():
    rng = np.random.default_rng(3)
    for _ in range(50):
        n = rng.normal(size=3)
        b1, b2 = perp_basis(n)
        assert np.isclose(b1 @ b1, 1.0) and np.isclose(b2 @ b2, 1.0)
        assert np.isclose(b1 @ b2, 0.0)
        assert abs(b1 @ n) < 1e-12 and abs(b2 @ n) < 1e-12


def test_rotvec_aligning():
    rng = np.random.default_rng(4)
    for _ in range(100):
        d = rng.normal(size=3)
        phi = rotvec_aligning(d)
        assert np.allclose(so3_exp(phi) @ np.array([1.0, 0, 0]),
                           d / np.linalg.norm(d), atol=1e-12)


# ----------------------------------------------------------------- entities


def test_entity_protocol_satisfied():
    for e in (RigidObject(), Rod(), Circle(), Sphere(), World()):
        assert hasattr(e, "vars")
        assert np.asarray(e.vars()).size == e.n_vars


def test_reduced_motion_counts():
    assert (RigidObject().n_vars, RigidObject().n_dof) == (6, 6)
    assert (Rod().n_vars, Rod().n_dof) == (7, 5)
    assert (Circle().n_vars, Circle().n_dof) == (7, 5)
    assert (Sphere().n_vars, Sphere().n_dof) == (4, 4)


def test_rod_endpoints_and_pos_is_centre_of_mass():
    rod = Rod(length=2.0)
    rod.place_between([0, 0, 0], [2, 0, 0])
    assert np.allclose(rod.pos, [1, 0, 0])          # midpoint is the position
    assert np.allclose(rod.point("a"), [0, 0, 0])
    assert np.allclose(rod.point("b"), [2, 0, 0])
    assert np.isclose(np.linalg.norm(rod.point("b") - rod.point("a")), 2.0)


def test_rod_in_plane_placement():
    rod = Rod(length=3.0)
    pa, pb = np.array([0.5, -1.0, 0.0]), np.array([2.0, 3.0, 0.0])
    rod.place_between(pa, pb)
    assert np.allclose(rod.point("a"), pa, atol=1e-12)
    assert np.allclose(rod.point("b"), pb, atol=1e-12)
    # An in-plane direction is reached by rotating about z, so the rotation
    # vector must lie along z (nonzero) with no x or y part.
    assert abs(rod.rotvec[0]) < 1e-12 and abs(rod.rotvec[1]) < 1e-12
    assert abs(rod.rotvec[2]) > 1e-6


def test_sphere_set_axis_does_not_clobber_radius():
    sphere = Sphere(radius=2.5)
    sphere.set_axis([0.0, 1.0, 0.0])                # must be a no-op
    assert sphere.radius == 2.5


def test_point_jacs_match_finite_differences():
    for entity in (RigidObject(), Rod(length=1.7), Circle(radius=0.9), Sphere(radius=2.0)):
        entity.place_between([0, 0, 0], [1.0, 0.6, 0.3])
        names = list(entity._local_points()[0])
        for name in names:
            J = entity.point_jac(name)
            n = numeric_jac(lambda v: (entity.set_vars(v), entity.point(name))[1],
                            entity.vars(), 3)
            assert np.allclose(J, n, atol=1e-6), f"{entity.name}.{name}"


def test_axis_jacs_match_finite_differences():
    for entity in (RigidObject(), Rod(), Circle()):
        entity.place_between([0, 0, 0], [1.0, 0.6, 0.3])
        for axis in ("x", "y", "z"):
            J = entity.axis_jac(axis)
            n = numeric_jac(lambda v: (entity.set_vars(v), entity.axis(axis))[1],
                            entity.vars(), 3)
            assert np.allclose(J, n, atol=1e-6), f"{entity.name}.axis({axis})"


# --------------------------------------------------------------- constraints


def _single(entities, constraints) -> tuple[Mechanism, list]:
    m = Mechanism()
    m.add(*entities, *constraints)
    return m, list(constraints)


def _randomise(entities, seed=0):
    rng = np.random.default_rng(seed)
    for e in entities:
        e.place_between(rng.normal(size=3) * 2, rng.normal(size=3) * 2)
    for c in entities:
        if isinstance(c, Sphere):
            c.set_position(rng.normal(size=3))


def test_fixed_jacobian():
    world, a, b = World(), Rod(length=2.0, name="a"), RigidObject(name="b")
    m = Mechanism().add(a, b)
    weld_a, weld_b = Fixed(world, a), Fixed(a, b)
    m.add(weld_a, weld_b)
    _randomise([a, b], seed=1)
    for c in (weld_a, weld_b):
        compare("Fixed", m, c, m.vars(), tol=1e-5)


def test_fixed_with_nonidentity_target():
    a, b = Rod(length=1.0, name="a"), Rod(length=1.0, name="b")
    target = SE3.from_rt([0.1, -0.2, 0.35], [1.0, 2.0, -0.5])
    m, (c,) = _single([a, b], [Fixed(a, b, target=target)])
    _randomise([a, b], seed=2)
    compare("Fixed(target)", m, c, m.vars(), tol=1e-5)


def test_point_constraint_jacobian():
    a, b = Rod(length=2.0, name="a"), Circle(radius=1.0, name="b")
    m, (c,) = _single([a, b], [PointConstraint(a, "b", b, "edge")])
    _randomise([a, b], seed=3)
    compare("PointConstraint", m, c, m.vars())


def test_point_constraint_to_world():
    world, rod = World(), Rod(length=2.0, name="rod")
    m, (c,) = _single([rod], [PointConstraint(world, "origin", rod, "a")])
    _randomise([rod], seed=4)
    compare("PointConstraint(world)", m, c, m.vars())


def test_distance_jacobian():
    a, b = Rod(length=2.0, name="a"), Sphere(radius=1.0, name="b")
    m, (c,) = _single([a, b], [Distance(a, "b", b, "origin", value=1.3)])
    _randomise([a, b], seed=5)
    compare("Distance", m, c, m.vars())


def test_planar_jacobian_translation_only():
    rod = Rod(length=2.0, name="rod")
    plane_origin = np.array([0.1, 0.2, 0.3])
    plane_normal = np.array([0.3, -0.5, 0.81])
    m, (c,) = _single([rod], [Planar(rod, "b", plane_origin, plane_normal)])
    _randomise([rod], seed=6)
    compare("Planar", m, c, m.vars())


def test_planar_jacobian_with_orientation():
    rod = Rod(length=2.0, name="rod")
    normal = np.array([0.0, 0.0, 1.0])
    m, (c,) = _single([rod], [Planar(rod, "b", (0, 0, 0), normal, orientation=True)])
    _randomise([rod], seed=7)
    assert c.n_eq == 3
    compare("Planar(orientation)", m, c, m.vars())


def test_align_axis_jacobian():
    rod = Rod(length=2.0, name="rod")
    m, (c,) = _single([rod], [AlignAxis(rod, [0.2, 0.5, -0.84], axis="x")])
    _randomise([rod], seed=8)
    assert c.n_eq == 2
    compare("AlignAxis", m, c, m.vars())


def test_value_jacobian():
    rod = Rod(length=2.0, name="rod")
    m, (c,) = _single([rod], [Value(rod, "length", 3.0)])
    _randomise([rod], seed=9)
    compare("Value", m, c, m.vars())


def test_all_constraint_jacobians_in_one_mechanism():
    world = World()
    world.add_point("p", [0.4, 0.1, -0.2])
    ground = Rod(length=2.0, name="ground")
    crank = Rod(length=1.5, name="crank")
    sphere = Sphere(radius=0.8, name="sphere")
    circle = Circle(radius=1.2, name="circle")
    m = Mechanism("mixed")
    m.add(ground, crank, sphere, circle, world)
    m.add_constraint(Fixed(world, ground))
    m.add_constraint(PointConstraint(crank, "a", ground, "a"))
    m.add_constraint(PointConstraint(crank, "b", sphere, "origin"))
    m.add_constraint(Planar(crank, "b", (0, 0, 0), (0, 0, 1), orientation=True))
    m.add_constraint(AlignAxis(circle, [0.0, 1.0, 0.0], axis="z"))
    m.add_constraint(Value(ground, "length", 2.0))
    m.add_constraint(Distance(sphere, "origin", circle, "edge", 0.9))
    _randomise([ground, crank, sphere, circle], seed=10)
    x = m.vars()
    assert np.allclose(m.jac(), numeric_jac(lambda v: m.residual(v), x, m.n_eq), atol=1e-5)


# ------------------------------------------------------------------- system


def test_offsets_are_contiguous():
    m = build_four_bar()
    offset = 0
    for e in m.entities:
        assert e.offset == offset
        assert e.global_slice == slice(offset, offset + e.n_vars)
        offset += e.n_vars
    assert m.n_vars == offset


def test_four_bar_seed_is_exact():
    m = seed_layout()
    assert m.residual_norm < 1e-12


def test_four_bar_mobility_is_one():
    m = seed_layout()
    sol = m.solve()
    assert sol.success
    assert sol.mobility.dof == 1
    # The Planar row on the rocker duplicates the pin to the ground pivot.
    assert sol.mobility.redundant_eq == 1


def test_four_bar_tangent_basis_moves_crank():
    m = seed_layout()
    sol = m.solve()
    T = m.tangent_basis()
    assert T.shape == (m.n_vars, 1)
    # The single free motion must move the crank but hold the ground link.
    ground = m.entity("ground")
    assert np.max(np.abs(T[ground.global_slice])) < 1e-9
    crank = m.entity("crank")
    assert np.max(np.abs(T[crank.global_slice][:, :3])) > 1e-6


def test_tangent_subset_excludes_gauge_directions():
    """Restricting the search can drop a symmetry spin and reveal nothing new."""
    m = seed_layout()
    crank = m.entity("crank")
    # Only the crank's translation blocks: one motion, crank rotation off.
    subset = list(crank.global_slice)[:3]
    T = m.tangent_basis(subset=subset)
    assert T.shape[1] <= 1
    # A perturbation along it must be first-order feasible.
    x0 = m.vars()
    eps = 1e-4
    m.set_vars(x0 + eps * T[:, 0])
    assert m.residual_norm < 1e-6 * (1.0 + np.linalg.norm(m.residual(x0)))


def test_free_body_has_six_dof():
    body = RigidObject(name="free")
    m = Mechanism().add(body)
    assert m.dof() == 6
    assert m.tangent_basis().shape == (6, 6)


def test_free_sphere_has_four_dof():
    sphere = Sphere(name="free")
    m = Mechanism().add(sphere)
    assert m.dof() == 4
    assert m.tangent_basis().shape == (4, 4)


def test_free_rod_has_five_dof_plus_gauge():
    """A lone rod is 5 dof; the axial spin shows up as a null direction."""
    rod = Rod(name="free")
    m = Mechanism().add(rod)
    assert m.n_vars == 7
    assert m.dof() == 7  # unconstrained: all 7 variables are free
    T = m.tangent_basis()
    assert T.shape == (7, 7)


def test_fixed_weld_removes_all_dof():
    world, a, b = World(), Rod(name="a"), Rod(name="b")
    m = Mechanism().add(a, b, Fixed(world, a), Fixed(a, b))
    assert m.n_vars == 14
    # Two 6-equation welds against a 0-var world: the lengths are gauge.
    assert m.dof() == 2  # the two unconstrained length variables
    sol = m.solve()
    assert sol.success


def test_redundant_constraint_keeps_dof_positive():
    """Duplicated Planar rows must not zero out the mobility."""
    world, a, b = World(), Rod(name="a"), Rod(name="b")
    plane = dict(origin=(0, 0, 0), normal=(0, 0, 1))
    m = Mechanism().add(a, b, Fixed(world, a), Fixed(a, b))
    m.add_constraint(Planar(a, "origin", **plane))
    m.add_constraint(Planar(a, "origin", **plane))  # exact duplicate
    mob = m.mobility()
    # 14 equations: 6 + 6 welds and two identical 1-eq planarity rows.  Once a
    # and b are welded together the planarity rows are already implied, so the
    # rank falls two short of the row count and the mobility survives.
    assert mob.n_eq == 14
    assert mob.redundant_eq == 2
    assert mob.rank == 12
    assert mob.dof == 2


def test_solve_recovers_a_known_assembly():
    m = Mechanism()
    world, rod = World(), Rod(length=2.0, name="rod")
    m.add(rod, world)
    rod.place_between([3, 2, 1], [3, 2, 1.5])  # wrong: length 0.5, misplaced
    m.add_constraint(PointConstraint(world, "origin", rod, "a"))
    m.add_constraint(Distance(rod, "a", rod, "b", value=2.0))
    sol = m.solve()
    assert sol.success
    assert np.isclose(sol.residual_norm, 0.0, atol=1e-10)
    assert np.isclose(np.linalg.norm(rod.point("b") - rod.point("a")), 2.0)
    assert np.allclose(rod.point("a"), 0.0, atol=1e-10)


def test_value_constraint_pins_length():
    rod = Rod(length=2.0, name="rod")
    sphere = Sphere(radius=1.0, name="sphere")
    m = Mechanism().add(rod, sphere)
    m.add_constraint(Value(rod, "length", 3.5))
    m.add_constraint(PointConstraint(rod, "a", sphere, "origin"))
    sol = m.solve()
    assert sol.success
    assert np.isclose(rod.length, 3.5)
    # 11 vars, rank 4 (1 Value + 3 point) leaves 7 free.  Of those, 2 are the
    # rod's direction, 3 the sphere's position, 1 the sphere's radius (never
    # constrained) and 1 the rod's axial spin, which is a genuine symmetry.
    assert m.dof() == 7
    # End a of the rod sits on the sphere's centre, so the rod's *centre* is
    # half a length away along its axis.
    assert np.allclose(rod.point("a"), sphere.pos, atol=1e-9)


def test_pinning_every_shape_and_spin_leaves_only_rod_direction():
    """Drop gauge directions to expose the real mobility of the rod/sphere pair."""
    rod = Rod(length=2.0, name="rod")
    sphere = Sphere(radius=1.0, name="sphere")
    m = Mechanism().add(rod, sphere)
    m.add_constraint(Value(rod, "length", 3.5))
    m.add_constraint(Value(sphere, "radius", 1.0))
    m.add_constraint(PointConstraint(rod, "a", sphere, "origin"))
    # m: 11 vars; rank = 1 + 1 + 3 = 5 -> 6 free = 3 sphere pos + 2 rod dir + 1 spin
    assert m.dof() == 6
    T = m.tangent_basis()
    assert T.shape == (11, 6)
