import numpy as np
import pytest
from kinematics.core.exploration import Exploration
from kinematics.core.preview import preview

from kinematics import Engine, FrameKind, RigidBody, Ring, Rod, Scene, Vec, build_scene


def test_centered_rod_points_and_aliases():
    scene = Scene()
    rod = scene.rod(Vec(2, 1), Vec(2, 5))
    assert isinstance(rod, RigidBody) and isinstance(rod, Rod)
    assert rod.length == 4
    assert tuple(rod.center) == (2, 3, 0)
    assert rod.start == rod.rel(-2)
    assert rod.end == rod.relative(Vec(2))
    assert tuple(rod.rel(0, 1)) == (1, 3, 0)
    engine = Engine(scene)
    assert engine.mobility()["first_order"] == 3
    assert np.max(np.abs(engine.residual(engine.initial.ravel()))) < 1e-12


@pytest.mark.parametrize("dimension,dofs", [(2, 3), (3, 6)])
def test_ring_affine_points_roundtrip_and_preview(dimension, dofs):
    scene = Scene(dimension=dimension)
    ring = scene.ring(Vec(2, 3), 2)
    assert isinstance(ring, Ring)
    point = ring.rel(1, -3)
    assert tuple(point) == (3, 0, 0)
    assert ring.top == ring.rel(0, 2)
    assert ring.bottom == ring.rel(0, -2)
    restored = Scene.from_dict(scene.to_dict())
    assert isinstance(restored.objects[0], Ring)
    engine = Engine(restored)
    assert engine.mobility()["first_order"] == dofs
    result = preview(engine, [point.key], [[4, 1, 0]])
    assert result
    x = engine.initial.copy()
    # Affine attachments follow a rotated, translated frame exactly.
    rotation = np.eye(dimension)
    rotation[:2, :2] = [[0, -1], [1, 0]]
    x = x @ rotation.T + 1
    assert np.max(np.abs(engine.residual(x.ravel()))) < 1e-10


def test_axial_and_full_rod_mobility():
    scene = Scene(dimension=3)
    rod = scene.rod(Vec(-2), Vec(2))
    assert rod.frame_kind == FrameKind.AXIAL_X
    rod.rel(0)
    with pytest.raises(ValueError, match="off-axis"):
        rod.rel(0, 1)
    assert Engine(scene).mobility()["first_order"] == 5
    scene = Scene(dimension=3)
    rod = scene.rod(Vec(-2), Vec(2), frame="full", normal=Vec(0, 0, 1))
    assert tuple(rod.rel(0, 1)) == (0, 1, 0)
    assert tuple(rod.rel(0, 0, 1)) == (0, 0, 1)
    assert Engine(scene).mobility()["first_order"] == 6


def test_spatial_ring_off_plane_point():
    scene = Scene(dimension=3)
    ring = scene.ring(Vec(), 2)
    assert tuple(ring.rel(0, 0, 3)) == (0, 0, 3)
    assert Engine(scene).mobility()["first_order"] == 6


def test_exploration_metric_ignores_requested_points():
    scene = build_scene("r=rod(left, right)")
    before = Exploration(Engine(scene))
    scene.objects[0].rel(100, 20)
    after = Exploration(Engine(scene))
    assert before.engine.scale == after.engine.scale
    assert np.count_nonzero(before.weights) == np.count_nonzero(after.weights)
    assert np.allclose(
        before.weights[before.weights > 0], after.weights[after.weights > 0]
    )


def test_default_dimension_and_planar_validation():
    scene = build_scene("r=rod(left,right)\npin(r.rel(0,1))")
    assert scene.dimension == 2
    with pytest.raises(ValueError, match="local XY"):
        Scene().rod(Vec(), Vec(1)).rel(0, 0, 1)


def test_generic_declared_center_and_legacy_scene():
    scene = Scene(dimension=3)
    body = scene.body({"tip": Vec(5, 2, 1)}, center=Vec(4, 2, 1))
    assert tuple(body.rel(1)) == tuple(body.point("tip"))
    assert tuple(body.origin) == (4, 2, 1)
    data = scene.to_dict()
    for obj in data["objects"]:
        for key in ("frame_kind", "relative_points", "affine_points"):
            obj.pop(key)
    restored = Scene.from_dict(data)
    assert Engine(restored).mobility()["first_order"] == 6


def test_planar_relative_jacobian_and_serialized_drag():
    scene = Scene()
    rod = scene.rod(Vec(2, 1), Vec(2, 5))
    point = rod.rel(1, 2)
    engine = Engine(Scene.from_dict(scene.to_dict()))
    flat = engine.initial.ravel()
    delta = np.random.default_rng(17).normal(size=flat.shape)
    numerical = (
        engine.residual(flat + 1e-6 * delta) - engine.residual(flat - 1e-6 * delta)
    ) / 2e-6
    assert np.allclose(engine.jac(flat) @ delta, numerical, atol=1e-8)
    result = engine.drag([point.key], [[0.1, 4.1, 0]])
    assert result["reachable"]
    assert np.max(np.abs(engine.residual(engine.current.ravel()))) < 1e-9


def test_inferred_spatial_scene_rejects_earlier_planar_off_axis_reference():
    with pytest.raises(ValueError, match="off-axis"):
        build_scene("a=rod(left,right)\npin(a.rel(0,1))\nb=rod(origin,forward)")


def test_ring_normal_defines_orthonormal_local_frame():
    scene = Scene(dimension=3)
    ring = scene.ring(Vec(1), 2, normal=Vec(0, -1))
    assert tuple(ring.rel(0, 2)) == (1, 0, 2)
    assert tuple(ring.rel(0, 0, 1)) == (1, -1, 0)
    assert Engine(scene).mobility()["first_order"] == 6
    with pytest.raises(ValueError, match="nonzero"):
        scene.ring(Vec(), 1, normal=Vec())


def test_hopf_link_attachments_match_the_specified_circles():
    from pathlib import Path

    import sympy as sp

    scene = build_scene(
        (Path(__file__).parents[1] / "src/kinematics/examples/hopf_link.py").read_text()
    )
    assert len(scene.objects) == 2
    assert len(scene.constraints) == 4
    restored = Scene.from_dict(scene.to_dict())
    assert set(restored.objects[0].point_labels.values()) == {"a1", "a2", "a3", "a4"}
    assert set(restored.objects[1].point_labels.values()) == {"b1", "b2", "b3", "b4"}
    points = {
        f"{o.id}:{n}": Vec(*p) for o in scene.objects for n, p in o.points.items()
    }
    for cable in scene.constraints:
        a, b = points[cable.a], points[cable.b]
        assert a.z == 0 and sp.simplify(a.x**2 + a.y**2) == 1
        assert b.y == 0 and sp.simplify((b.x - 1) ** 2 + b.z**2) == 1
        assert sp.simplify(cable.value - sp.Rational(11, 8)) == 0
    engine = Engine(scene)
    assert engine.error(engine.assemble()) < 1e-9
