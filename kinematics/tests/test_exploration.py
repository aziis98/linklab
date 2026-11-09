import itertools
from pathlib import Path

import numpy as np
from kinematics.core.exploration import Exploration

from kinematics import Engine, build_scene


def test_frontier_prioritizes_uncovered_configuration_space():
    source = (
        Path(__file__).parents[1] / "src/kinematics/examples/concentric_rings.py"
    ).read_text()
    live = Engine(build_scene(source))
    job = Exploration(live, spacing=0.5, limit=100, seconds=20)
    while job.advance()["status"] == "running":
        pass
    # Breadth-first probes previously spent this budget in a small patch (< .4).
    assert max(job.distance(job.root, n["x"]) for n in job.nodes) > 0.8
    assert job.attempts < 200
    assert all(live.error(n["x"]) < 1e-9 for n in job.nodes)


def test_circle_closes_and_preserves_live_pose():
    live = Engine(build_scene('r=rod(origin,up,id="r")\npin(r.start,origin)'))
    before = live.configuration()
    job = Exploration(live, spacing=0.08, seconds=10)
    for _ in range(500):
        data = job.advance()
        if data["status"] != "running":
            break
    assert len(data["edges"]) >= len(data["nodes"])
    assert live.configuration() == before
    for e in job.edges:
        for cfg in e["path"]:
            x = np.array([cfg[k][:2] for k in live.keys])
            assert live.error(x) < 1e-9
    tour = job.tour(12)
    assert tour["route"][0] == tour["route"][-1]
    assert len(tour["frames"]) > 10


def test_isolated_and_bounds():
    live = Engine(build_scene('r=rod(origin,up,id="r",fixed=True)'))
    job = Exploration(live)
    assert job.advance()["status"] == "frontier_exhausted"
    live = Engine(build_scene('r=rod(origin,up,id="r")'))
    job = Exploration(live, radius=0.1, limit=20, seconds=1)
    for _ in range(100):
        data = job.advance()
        if data["status"] != "running":
            break
    assert len(job.nodes) <= 20
    assert all(job.distance(job.root, n["x"]) <= 0.1 for n in job.nodes)


def test_incremental_tour_frames_and_deltas():
    from kinematics.core.exploration import TourPreparation

    live = Engine(build_scene('r=rod(origin,up,id="r")\npin(r.start,origin)'))
    job = Exploration(live, spacing=0.08, seconds=10)
    for _ in range(100):
        result = job.advance()
        if result["status"] != "running":
            break
    first = job.snapshot(0, 0)
    empty = job.snapshot(first["node_cursor"], first["edge_cursor"])
    assert empty["nodes"] == [] and empty["edges"] == []
    tour = TourPreparation(job, 10)
    for _ in range(1000):
        batch = tour.advance()
        for cfg in batch["frames"]:
            assert live.error(np.array([cfg[k][:2] for k in live.keys])) < 1e-9
        if batch["done"]:
            break
    assert batch["done"]
    assert tour.frames[0] == tour.frames[-1]


def test_higher_dimensional_pause_resume_and_cancellation():
    live = Engine(
        build_scene('scene_dimension(3)\nr=rod(origin,up,id="r")\npin(r.start,origin)')
    )
    first = Exploration(live, spacing=0.08, radius=0.3, seconds=100, limit=25)
    first.advance(1)
    first.pause()
    partial = len(first.nodes)
    for _ in range(100):
        state = first.advance()
        if state["status"] != "running":
            break
    assert len(first.nodes) >= partial
    assert len(first.nodes) == 25
    assert all(n["dimension"] == 2 for n in first.nodes)
    assert all(first.distance(first.root, n["x"]) <= 0.3 for n in first.nodes)
    other = Exploration(live, spacing=0.08, radius=0.3, seconds=100, limit=25)
    while other.advance()["status"] == "running":
        pass
    assert [n["configuration"] for n in first.nodes] == [
        n["configuration"] for n in other.nodes
    ]
    first.cancel()
    import pytest

    with pytest.raises(ValueError, match="cancelled"):
        first.advance()


def test_meeting_inside_existing_edge_splits_it():
    live = Engine(build_scene('r=rod(origin,up,id="r")\npin(r.start,origin)'))
    job = Exploration(live, spacing=0.2, seconds=10)

    def pose(angle):
        x = live.current.copy()
        x[1] = [np.sin(angle), np.cos(angle)]
        return x

    left = job.add(pose(-0.4))
    right = job.add(pose(0.6))
    path = [pose(a) for a in np.linspace(-0.4, 0.6, 6)]
    job.edge(
        left, right, path, sum(job.distance(a, b) for a, b in itertools.pairwise(path))
    )
    old = job.edges[0]["id"]
    tangent = np.array(live.mobility()["linear_compatible_tangents"])[0].ravel()
    if tangent[2] < 0:
        tangent = -tangent
    job.frontier.clear()
    job.frontier.append((0, tangent))
    job.advance(0.001)
    assert old in job.removed
    assert len(job.edges) == 3
    for edge in job.edges:
        assert edge["path"][0] == job.nodes[edge["a"]]["configuration"]
        assert edge["path"][-1] == job.nodes[edge["b"]]["configuration"]


def test_scene_and_job_revisions_reject_old_exploration():
    import pytest

    from kinematics import Session

    session = Session()
    session.run("r=rod(origin,up)")
    old = session.dispatch({"op": "explore_start"})
    session.dispatch({"op": "explore_start"})
    with pytest.raises(ValueError, match="stale exploration"):
        session.dispatch({"op": "explore_step", "job_id": old["job_id"]})


def test_tour_revisits_junctions_without_splitting():
    live = Engine(build_scene('r=rod(origin,up,id="r")'))
    job = Exploration(live, spacing=0.08, seconds=10)
    for delta in ([1, 0], [-1, 0], [0, 1]):
        x = job.root + np.array(delta)
        i = job.add(x)
        job.edge(0, i, [job.root, x], job.distance(job.root, x))
    result = job.tour(10)
    assert len(result["targets"]) == 4
    assert sum(a == 0 for a, b in result["walk"]) >= 3
    assert all(a[1] == b[0] for a, b in zip(result["walk"], result["walk"][1:]))
    assert result["walk"][0][0] == result["walk"][-1][1]


def test_refinement_preserves_graph_and_adds_coverage():
    live = Engine(build_scene('r=rod(origin,up,id="r")\npin(r.start,origin)'))
    job = Exploration(live, spacing=0.08, seconds=10)
    while job.advance()["status"] == "running":
        pass
    before = [n["configuration"] for n in job.nodes]
    job.refine(0.04)
    assert job.frontier
    while job.advance()["status"] == "running":
        pass
    assert [n["configuration"] for n in job.nodes[: len(before)]] == before
    assert len(job.nodes) > len(before)


def test_fourbar_frames_use_a_local_chart_without_tangential_drift():
    from kinematics import TourPreparation

    live = Engine(
        build_scene("""
g=rod(origin,right*3,id="g",fixed=True)
a=rod(origin,up*2,id="a")
b=rod(g.end,g.end+up*3,id="b")
c=rod(a.end,b.end,id="c")
coincident(g.start,a.start)
coincident(g.end,b.start)
coincident(a.end,c.start)
coincident(b.end,c.end)
""")
    )
    job = Exploration(live, spacing=0.04, seconds=20, limit=600)
    while job.advance()["status"] == "running":
        pass
    assert job.status == "frontier_exhausted"
    assert len(job.edges) == len(job.nodes)
    preparation = TourPreparation(job)
    while not preparation.advance()["done"]:
        pass
    assert preparation.frames[0] == preparation.frames[-1]
    previous = None
    for cfg in preparation.frames:
        x = np.array([cfg[k][: live.d] for k in live.keys])
        assert live.error(x) < 1e-9
        if previous is not None:
            assert job.distance(previous, x) < job.spacing / 8
        previous = x


def test_crossing_fourbar_junction_probes_multiple_feasible_branches():
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
    job = Exploration(live, spacing=0.04, seconds=30, limit=80)
    assert job.nodes[0]["singular"]
    for _ in range(100):
        if sum(e["a"] == 0 or e["b"] == 0 for e in job.edges) >= 4:
            break
        job.advance()
    assert sum(e["a"] == 0 or e["b"] == 0 for e in job.edges) >= 4
    assert (
        job.unresolved_nodes
    )  # Numerical branch finding is explicitly not a certificate.
    assert all(live.error(n["x"]) < 1e-9 for n in job.nodes)
