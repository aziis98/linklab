from pathlib import Path

import numpy as np
import pytest
from kinematics.core.preview import preview
from kinematics.core.taut import taut_chain_pins

from kinematics import Engine, Scene, Session, Wander, build_scene

PAIRED_RINGS = """scene_dimension(3)
outer = ring(origin, 3, id="outer", fixed=True)
inner = ring(origin, 1.5, id="inner")
bar_top = rod(outer.top, inner.top)
bar_bottom = rod(outer.bottom, inner.bottom)

coincident(outer.top, bar_top.start)
coincident(bar_top.end, inner.top)

coincident(outer.bottom, bar_bottom.start)
coincident(bar_bottom.end, inner.bottom)
"""


@pytest.mark.parametrize("dimension, expected", [(2, 3), (3, 6)])
def test_bottom_is_an_antipodal_marker_without_extra_degrees_of_freedom(
    dimension, expected
):
    scene = build_scene(f'scene_dimension({dimension})\nr=ring(Vec(2,3,0),2,id="r")')
    ring = scene.objects[0]
    assert set(ring.points) == {"origin", "x", "y"}
    assert tuple(ring.bottom) == (2, 1, 0)
    assert ring.bottom == ring.point("bottom")
    engine = Engine(scene)
    mobility = engine.mobility()
    assert (
        mobility["first_order"] == mobility["linear_compatible_dimension"] == expected
    )
    assert mobility["second_order"] == "compatible"
    restored = Engine(Scene.from_dict(scene.to_dict()))
    assert restored.ring_bottoms == engine.ring_bottoms
    assert restored.configuration() == engine.configuration()


def test_user_scene_assembles_and_bottom_stays_opposite_top_while_dragging():
    engine = Engine(build_scene(PAIRED_RINGS))
    engine.assemble()
    assert engine.configuration()["outer:bottom"] == [0, -3, 0]
    assert engine.configuration()["inner:bottom"] == [0, -1.5, 0]
    assert engine.mobility()["linear_compatible_dimension"] == 1
    result = engine.drag(["inner:x"], [[1.1, 0, 0.9]])
    assert result["mobility"]["residual"] < 1e-9
    assert result["configuration"]["inner:x"][2] > 0.1
    for ident in ("outer", "inner"):
        c = np.array(result["configuration"][f"{ident}:origin"])
        top = np.array(result["configuration"][f"{ident}:y"])
        np.testing.assert_allclose(
            result["configuration"][f"{ident}:bottom"], 2 * c - top, atol=1e-8
        )


def test_preview_keeps_the_bottom_marker_affine_even_when_constraints_are_violated():
    engine = Engine(build_scene(PAIRED_RINGS))
    result = preview(engine, ["inner:bottom"], [[0.4, -1.5, 0.2]])
    cfg = result["configuration"]
    np.testing.assert_allclose(
        cfg["inner:bottom"],
        2 * np.array(cfg["inner:origin"]) - np.array(cfg["inner:y"]),
        atol=1e-9,
    )
    assert result["target_error"] < 1e-9


def test_bottom_binding_has_the_correct_analytic_jacobian():
    engine = Engine(build_scene(PAIRED_RINGS))
    x = (
        engine.current.ravel()
        + np.random.default_rng(0).normal(size=engine.current.size) * 0.01
    )
    delta = np.eye(x.size) * 1e-6
    finite = np.column_stack(
        [(engine.residual(x + d) - engine.residual(x - d)) / 2e-6 for d in delta]
    )
    np.testing.assert_allclose(engine.jac(x), finite, atol=1e-8)


def test_wander_follows_the_remaining_rotation_of_the_braced_rings():
    source = (
        Path(__file__).parents[1] / "src/kinematics/examples/concentric_rings_3d.py"
    ).read_text()
    live = Engine(build_scene(source))
    before, scene = live.configuration(), live.scene.to_dict()
    assert live.mobility()["second_order"] == "inconclusive"
    walk = Wander(live, seed=7)
    assert walk.engine.mobility()["first_order"] == 1
    trajectory = []
    for _ in range(360):
        frame = walk.step()
        pose = frame["configuration"]
        assert live.error(walk.x) < 1e-9
        for key, point in before.items():
            if key != "inner:x":
                np.testing.assert_allclose(pose[key], point, atol=1e-8)
        trajectory.append(pose["inner:x"])
    trajectory = np.array(trajectory)
    assert trajectory[:, 0].min() < -1.4 and trajectory[:, 0].max() > 1.4
    assert trajectory[:, 2].min() < -1.4 and trajectory[:, 2].max() > 1.4
    assert walk.time > 10
    assert live.configuration() == before
    assert live.scene.to_dict() == scene


def test_nearly_stretched_chains_are_not_locked_by_numerical_tolerance():
    scene = build_scene("""scene_dimension(3)
a=rod(left,Vec(0,0.000001,0),id="a")
b=rod(right,a.end,id="b")
pin(a.start)
pin(b.start)
coincident(a.end,b.end)
""")
    assert taut_chain_pins(scene) == {}


def test_stretched_chain_consequences_use_exact_algebraic_lengths():
    scene = build_scene("""scene_dimension(3)
a=rod(origin,right*sqrt(2),id="a")
b=rod(a.end,right*sqrt(2)*2,id="b")
pin(a.start)
pin(b.end)
coincident(a.end,b.start)
""")
    pins = taut_chain_pins(scene)
    assert pins["a:b"] == scene.objects[0].points["b"]
    assert pins["b:a"] == pins["a:b"]


def test_adopting_a_feasible_singular_animation_pose_preserves_it_exactly():
    session = Session()
    session.run(PAIRED_RINGS)
    start = session.dispatch({"op": "wander_start"})
    frames = session.dispatch({"op": "wander_step", "job_id": start["job_id"]})[
        "frames"
    ]
    assert frames
    pose = frames[-1]["configuration"]
    result = session.dispatch({"op": "adopt", "configuration": pose})
    assert result["configuration"] == pose
    assert result["mobility"]["residual"] < 1e-9


def test_adopting_integer_json_coordinates_keeps_floating_solver_coordinates():
    session = Session()
    session.run('r=rod(origin,up,id="r")\npin(r.start)')
    result = session.dispatch(
        {"op": "adopt", "configuration": {"r:a": [0, 0, 0], "r:b": [0, 1, 0]}}
    )
    assert result["mobility"]["first_order"] == 1
    assert session.engine.current.dtype == np.float64
