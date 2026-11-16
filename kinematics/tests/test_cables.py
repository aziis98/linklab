import numpy as np
import pytest
from kinematics.core.exploration import Exploration
from kinematics.core.wander import Wander

from kinematics import Engine, Scene, build_scene

SOURCE = """r=body({})
a=body({},fixed=True,id="anchor")
cable(a.origin,r.origin,length=2,id="tether")
"""


def test_slack_motion_and_maximum_length():
    e = Engine(build_scene(SOURCE))
    for _ in range(10):
        e.drag(["body1:origin"], [[3, 0, 0]])
    assert np.linalg.norm(e.current[e.index["body1:origin"]]) <= 2 + 1e-9 * e.scale
    for _ in range(10):
        e.drag(["body1:origin"], [[1, 0, 0]])
    assert e.current[e.index["body1:origin"], 0] < 1.1
    assert e.error(e.current) < 1e-9
    assert len(Scene.from_dict(e.scene.to_dict()).constraints) == 1


def test_stretched_chain_is_locked():
    e = Engine(
        build_scene("""a=body({},fixed=True)
b=body({},fixed=True,center=right*2)
r=body({},center=right)
cable(a.origin,r.origin,length=1)
cable(r.origin,b.origin,length=1)
""")
    )
    assert e.mobility()["linear_compatible_dimension"] == 1
    # The body still rotates, but its center cannot move transversely.
    before = e.current[e.index["body3:origin"]].copy()
    e.drag(["body3:origin"], [[1, 0.2, 0]])
    assert np.linalg.norm(e.current[e.index["body3:origin"]] - before) < 1e-8


def test_negative_zero_and_inferred_limits():
    with pytest.raises(ValueError):
        build_scene(SOURCE.replace("length=2", "length=-1"))
    e = Engine(build_scene(SOURCE.replace("length=2", "length=0")))
    assert e.cables == []
    assert len(e.equal) == 1


def test_wander_and_exploration_accept_cable_scenes():
    e = Engine(build_scene(SOURCE))
    walk = Wander(e)
    for _ in range(5):
        walk.step()
    assert e.error(walk.x) <= 1e-9
    chart = Exploration(e, limit=20, seconds=1)
    chart.advance(budget_ms=20)
    assert all(chart.engine.error(node["x"]) <= 1e-9 for node in chart.nodes)


def test_warm_start_releases_inward_and_recovers_from_stale_set():
    from kinematics.core.inequalities import constrained_fit

    c = np.eye(2)
    a = np.array([[1.0, 0.0], [0.0, 1.0]])
    working = []
    assert np.allclose(
        constrained_fit(c, np.array([2.0, 0.2]), a, np.ones(2), working), [1, 0.2]
    )
    assert working == [0]
    assert np.allclose(
        constrained_fit(c, np.array([0.2, 0.2]), a, np.ones(2), working), [0.2, 0.2]
    )
    assert working == []
    working[:] = [99]
    assert np.allclose(
        constrained_fit(c, np.array([2.0, 0.2]), a, np.ones(2), working), [1, 0.2]
    )


def test_pose_cache_detects_mutated_positions_and_pins():
    e = Engine(build_scene(SOURCE))
    first = e.mobility()
    assert e.mobility(e.current.copy()) is first
    e.current[0, 0] += 0.01
    assert e.mobility() is not first
    second = e.mobility()
    e.pins[0] = np.array([0.0, 0.0])
    assert e.mobility() is not second


def test_boundary_repulsion_turns_tangent_heading_inward_and_scales():
    e = Engine(
        build_scene(
            "scene_dimension(3)\na=body({},fixed=True)\nb=body({},center=right)\ncable(a.origin,b.origin,length=1)"
        )
    )
    walk = Wander(e, boundary_repulsion=1, turning=0)
    desired = np.zeros_like(walk.x)
    for name in e.scene.objects[1].points:
        desired[e.index[f"body2:{name}"], 1] = 1
    heading = walk.metric * desired.ravel()
    heading = walk.basis @ (walk.basis.T @ heading)
    heading /= np.linalg.norm(heading)
    bias = walk.boundary_bias(heading, walk.basis)
    _, normals = walk.engine.cable_rows(walk.x)
    assert bias @ (normals[0] * walk.inverse_metric) < 0
    assert abs(bias @ heading) < 1e-12
    walk.set_boundary_repulsion(2)
    assert np.allclose(walk.boundary_bias(heading, walk.basis), 2 * bias)
    walk.set_boundary_repulsion(0)
    assert np.array_equal(
        walk.boundary_bias(heading, walk.basis), np.zeros_like(heading)
    )
    with pytest.raises(ValueError):
        walk.set_boundary_repulsion(float("nan"))
    with pytest.raises(ValueError):
        walk.set_boundary_repulsion(-1)


def test_repulsion_leaves_slack_cables_and_ordinary_scenes_unchanged():
    for source in (SOURCE, "r=rod(origin,up)\npin(r.start)"):
        e = Engine(build_scene(source))
        zero = Wander(e, seed=19, boundary_repulsion=0)
        strong = Wander(e, seed=19, boundary_repulsion=4)
        for _ in range(5):
            zero.step()
            strong.step()
            assert np.allclose(zero.x, strong.x, atol=1e-12)


def test_boundary_repulsion_shortens_a_cable_instead_of_sticking():
    source = "scene_dimension(3)\na=body({},fixed=True)\nb=body({},center=right)\ncable(a.origin,b.origin,length=1)"
    radii = []
    for strength in (0, 1):
        walk = Wander(
            Engine(build_scene(source)), turning=0, boundary_repulsion=strength
        )
        velocity = np.zeros_like(walk.x)
        for name in walk.engine.scene.objects[1].points:
            velocity[walk.engine.index[f"body2:{name}"], 1] = 1
        walk.direction = walk.metric * velocity.ravel()
        walk.direction /= np.linalg.norm(walk.direction)
        for _ in range(15):
            walk.step()
        assert walk.engine.error(walk.x) <= 1e-9
        radii.append(np.linalg.norm(walk.x[walk.engine.index["body2:origin"]]))
    assert radii[0] - radii[1] > 0.01


def test_wander_from_integer_json_pose_preserves_float_jacobians():
    from kinematics import Session

    session = Session()
    state = session.run(
        "scene_dimension(3)\na=body({},fixed=True)\nb=body({},center=right)\ncable(a.origin,b.origin,length=1)"
    )
    configuration = {
        k: [int(v) for v in point] for k, point in state["configuration"].items()
    }
    result = session.dispatch(
        {
            "op": "wander_start",
            "configuration": configuration,
            "settings": {"boundary_repulsion": 1},
        }
    )
    assert result["status"] == "running"
    assert np.issubdtype(session.wander_job.x.dtype, np.floating)
    frames = session.dispatch(
        {"op": "wander_step", "job_id": result["job_id"], "boundary_repulsion": 0}
    )
    assert frames["frames"]
    assert session.wander_job.boundary_repulsion == 0
