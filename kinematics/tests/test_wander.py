from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from kinematics import Engine, Session, Wander, build_scene


@pytest.mark.parametrize(
    "source",
    [
        'r=rod(origin,up,id="r")\npin(r.start,origin)',
        'scene_dimension(3)\nr=rod(origin,up,id="r")\npin(r.start,origin)',
        'scene_dimension(3)\nr=rod(origin,up,id="r")',
        (
            Path(__file__).parents[1] / "src/kinematics/examples/concentric_rings.py"
        ).read_text(),
    ],
)
def test_wander_preserves_constraints_speed_and_heading(source):
    live = Engine(build_scene(source))
    before = live.configuration()
    wander = Wander(live, seed=7)
    previous = live.current.copy()
    previous_time = 0.0
    velocities = []
    for _ in range(180):
        frame = wander.step()
        assert live.error(wander.x) < 1e-9
        dt = frame["time"] - previous_time
        assert dt == pytest.approx(1 / 30, rel=0.02)
        speed = wander.chart.distance(previous, wander.x) / dt
        assert speed == pytest.approx(wander.speed, rel=1e-8)
        velocity = wander.metric * (wander.x - previous).ravel()
        velocities.append(velocity / np.linalg.norm(velocity))
        previous = wander.x.copy()
        previous_time = frame["time"]
    assert min(a @ b for a, b in pairwise(velocities)) > 0.98
    assert wander.chart.distance(live.current, wander.x) > 0.05
    assert live.configuration() == before


def test_seeded_wander_is_repeatable_and_steering_changes_the_path():
    live = Engine(
        build_scene('scene_dimension(3)\nr=rod(origin,up,id="r")\npin(r.start,origin)')
    )
    walks = [Wander(live, seed=3), Wander(live, seed=3), Wander(live, seed=4)]
    for _ in range(60):
        for walk in walks:
            walk.step()
    np.testing.assert_allclose(walks[0].x, walks[1].x)
    assert np.linalg.norm(walks[0].x - walks[2].x) > 0.01
    straight = Wander(live, seed=3, turning=0)
    for _ in range(60):
        straight.step()
    assert np.linalg.norm(walks[0].x - straight.x) > 0.01


def test_isolated_wander_is_rejected_and_batches_are_bounded():
    live = Engine(build_scene('r=rod(origin,up,id="r",fixed=True)'))
    with pytest.raises(ValueError, match="No continuous motion"):
        Wander(live)
    collinear = Engine(
        build_scene(
            "a=rod(left,origin)\nb=rod(origin,right)\npin(a.start,left)\npin(b.end,right)\ncoincident(a.end,b.start)"
        )
    )
    with pytest.raises(ValueError, match="No continuous motion"):
        Wander(collinear)
    mobile = Engine(build_scene("r=rod(origin,up)\npin(r.start,origin)"))
    walk = Wander(mobile)
    batch = walk.advance(budget_ms=1000, max_frames=5)
    assert len(batch["frames"]) == 5
    assert batch["status"] == "running"


def test_session_wander_starts_from_displayed_pose_and_rejects_stale_jobs():
    session = Session()
    scene = session.run('r=rod(origin,up,id="r")\npin(r.start,origin)')
    original = scene["configuration"]
    pose = {**original, "r:b": [1.0, 0.0, 0.0]}
    first = session.dispatch({"op": "wander_start", "configuration": pose})
    assert first["frames"][0]["configuration"]["r:b"] == pose["r:b"]
    assert session.engine.configuration() == original
    second = session.dispatch({"op": "wander_start"})
    with pytest.raises(ValueError, match="stale wander"):
        session.dispatch({"op": "wander_step", "job_id": first["job_id"]})
    assert session.dispatch({"op": "wander_step", "job_id": second["job_id"]})["frames"]
    session.dispatch({"op": "reset"})
    with pytest.raises(ValueError, match="invalidated"):
        session.dispatch({"op": "wander_step", "job_id": second["job_id"]})


def test_spatial_rotor_has_three_rotational_dofs_and_a_fixed_pivot():
    source = (
        Path(__file__).parents[1] / "src/kinematics/examples/spatial_rotor.py"
    ).read_text()
    live = Engine(build_scene(source))
    mobility = live.mobility()
    assert {obj.id for obj in live.scene.objects} == {"stand", "rotor"}
    np.testing.assert_allclose(live.configuration()["stand:a"], [0, -0.6, 0])
    assert mobility["first_order"] == mobility["linear_compatible_dimension"] == 3
    wander = Wander(live, seed=4)
    for _ in range(240):
        pose = wander.step()["configuration"]
        np.testing.assert_allclose(pose["rotor:origin"], [0, 0, 0], atol=1e-9)
        assert live.error(wander.x) < 1e-9
    assert wander.chart.distance(live.current, wander.x) > 0.1


def test_wander_still_rejects_an_unresolved_branch_crossing():
    live = Engine(
        build_scene("""
g=rod(origin,right*3,id="g",fixed=True)
a=rod(origin,right*2,id="a")
b=rod(right*3,right*6,id="b")
c=rod(a.end,b.end,id="c")
coincident(g.start,a.start)
coincident(g.end,b.start)
coincident(a.end,c.start)
coincident(b.end,c.end)
""")
    )
    with pytest.raises(ValueError, match="unresolved singular"):
        Wander(live)


def test_spatial_linked_pendulum_preserves_anchors_and_its_shared_joint():
    source = (
        Path(__file__).parents[1] / "src/kinematics/examples/spatial_linked_pendulum.py"
    ).read_text()
    live = Engine(build_scene(source))
    assert live.mobility()["first_order"] == 3
    assert live.mobility()["linear_compatible_dimension"] == 3
    walk = Wander(live, seed=2)
    for _ in range(240):
        pose = walk.step()["configuration"]
        assert live.error(walk.x) < 1e-9
        np.testing.assert_allclose(pose["a:a"], [-1, 0, 0], atol=1e-9)
        np.testing.assert_allclose(pose["b:a"], [1, 0, 0], atol=1e-9)
        np.testing.assert_allclose(pose["a:b"], pose["b:b"], atol=1e-9)
        np.testing.assert_allclose(pose["a:b"], pose["c:a"], atol=1e-9)
    assert walk.chart.distance(live.current, walk.x) > 0.1
