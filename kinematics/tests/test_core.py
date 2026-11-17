import numpy as np
import pytest
from kinematics.core.geometry import circle_circle, line_line, sphere_sphere

from kinematics import Engine, Scene, Session, build_scene

LOCK = """
r1=rod(left*2,origin,id="r1")
r2=rod(origin,right*2,id="r2")
pin(r1.start,left*2)
coincident(r1.end,r2.start)
pin(r2.end,right*2)
"""
TRIANGLE = """
r1=rod(Vec(-1.5,0),Vec(0,sqrt(7)/2),id="r1")
r2=rod(Vec(1.5,0),r1.end,id="r2")
pin(r1.start,Vec(-1.5,0))
pin(r2.start,Vec(1.5,0))
coincident(r1.end,r2.end)
"""
MIXED = """
r1=rod(Vec(1,1),origin,id="r1")
r2=rod(Vec(1,-1),origin,id="r2")
r3=rod(origin,up,id="r3")
r4=rod(origin,up,id="r4")
pin(r1.start,Vec(1,1))
pin(r2.start,Vec(1,-1))
pin(r3.start,origin)
coincident(r1.end,r2.end)
coincident(r2.end,r4.start)
coincident(r3.end,r4.end)
"""
FOURBAR = """
g=rod(origin,right*3,id="ground",fixed=True)
a=rod(origin,up*2,id="a")
b=rod(g.end,g.end+up*3,id="b")
c=rod(a.end,b.end,id="c")
coincident(g.start,a.start)
coincident(g.end,b.start)
coincident(a.end,c.start)
coincident(b.end,c.end)
"""


def test_lock_drag():
    session = Session()
    before = session.run(LOCK)
    assert before["mobility"]["first_order"] == 1
    assert before["mobility"]["second_order"] == "locked"
    for y in (0.001, 0.2, 2):
        result = session.drag(["r1:b"], [[0, y, 0]])
        assert result["configuration"] == before["configuration"]


@pytest.mark.parametrize(
    "source,count,dimensions",
    [(LOCK, 1, [0]), (TRIANGLE, 2, [0, 0]), (MIXED, 2, [0, 1])],
)
def test_topology(source, count, dimensions):
    data = Session().run(source, mode="topological")
    motion = data["motion"]
    assert motion["status"] == "certified"
    assert len(motion["cells"]) == count
    assert sorted(c["dimension"] for c in motion["cells"]) == dimensions
    engine = Engine(build_scene(source))
    for cell in motion["cells"]:
        for cfg in cell["configurations"]:
            x = np.array([cfg[k][:2] for k in engine.keys])
            assert engine.error(x) < 1e-9


def test_derivatives():
    engine = Engine(build_scene(MIXED))
    x = engine.initial.ravel() + np.random.default_rng(3).normal(
        0, 0.1, engine.initial.size
    )
    h = 1e-6
    eye = np.eye(len(x)) * h
    numeric = np.column_stack(
        [(engine.residual(x + e) - engine.residual(x - e)) / (2 * h) for e in eye]
    )
    np.testing.assert_allclose(engine.jac(x), numeric, atol=1e-8)


def test_free_spatial_rod():
    engine = Engine(build_scene("r=rod(origin,up)", 3))
    assert engine.mobility()["first_order"] == 5
    length = np.linalg.norm(engine.initial[1] - engine.initial[0])
    result = engine.drag(["r1:b"], [[1, 2, 1]])
    p = result["configuration"]
    assert np.linalg.norm(np.array(p["r1:a"]) - p["r1:b"]) == pytest.approx(
        length, abs=1e-8
    )


def test_fourbar():
    data = Session().run(FOURBAR, mode="topological")
    assert data["mobility"]["first_order"] == 1
    assert data["motion"]["status"] in ("certified", "partial")
    engine = Engine(build_scene(FOURBAR))
    for cell in data["motion"]["cells"]:
        for cfg in cell["configurations"]:
            assert engine.error(np.array([cfg[k][:2] for k in engine.keys])) < 1e-7


def test_body_and_plane():
    engine = Engine(build_scene('b=body({"tip":Vec(2,0,0)},fixed=True)', 3))
    assert engine.mobility()["first_order"] == 0
    scene = build_scene("r=rod(origin,up)\npoint_on_plane(r.end,origin,Vec(0,0,1))", 3)
    engine = Engine(scene)
    engine.drag(["r1:b"], [[1, 1, 1]])
    assert abs(engine.configuration()["r1:b"][2]) < 1e-8


def test_intersections():
    assert len(circle_circle((0, 0), 1, (2, 0), 1).points) == 1
    assert circle_circle((0, 0), 1, (0, 0), 1).kind == "coincident"
    assert circle_circle((0, 0), 1, (3, 0), 1).kind == "empty"
    assert line_line((0, 0, 0), (1, 0, 0), (0, 1, 1), (0, 1, 0)).kind == "empty"
    assert sphere_sphere((0, 0, 0), 1, (1, 0, 0), 1).kind == "circle"


def test_conflicting_anchors():
    engine = Engine(build_scene("r=rod(origin,up,fixed=True)\npin(r.start,right)"))
    with pytest.raises(ValueError):
        engine.assemble()


def test_fallback_and_explicit_grounding():
    data = Session().run('g=rod(origin,up,id="g1")', 3, "topological")
    assert data["mobility"]["first_order"] == 5
    assert data["motion"]["status"] == "fallback"


def test_scene_round_trip():
    import json

    from kinematics import Scene

    scene = build_scene(MIXED)
    assert scene.objects[0].source_span is not None
    restored = Scene.from_dict(json.loads(json.dumps(scene.to_dict())))
    np.testing.assert_equal(Engine(restored).initial, Engine(scene).initial)
    assert restored.to_dict() == scene.to_dict()


@pytest.mark.parametrize("dimension", [2, 3])
def test_parallel_derivatives(dimension):
    scene = build_scene(
        "a=rod(origin,up)\nb=rod(right,right+up)\nparallel(a.axis(),b.axis())",
        dimension,
    )
    engine = Engine(scene)
    x = engine.initial.ravel() + np.random.default_rng(4).normal(
        0, 0.03, engine.initial.size
    )
    h = 1e-6
    eye = np.eye(len(x)) * h
    numeric = np.column_stack(
        [(engine.residual(x + v) - engine.residual(x - v)) / (2 * h) for v in eye]
    )
    np.testing.assert_allclose(engine.jac(x), numeric, atol=1e-8)


@pytest.mark.parametrize("factor", [0.001, 1, 1000])
def test_scaled_lock(factor):
    source = LOCK.replace("left*2", f"left*{2 * factor}").replace(
        "right*2", f"right*{2 * factor}"
    )
    e = Engine(build_scene(source))
    e.assemble()
    before = e.configuration()
    assert e.drag(["r1:b"], [[0, factor * 0.2, 0]])["configuration"] == before


def test_numerical_component_discovery_disabled():
    data = Session().run(TRIANGLE)
    assert len(data["motion"]["cells"]) == 1
    assert data["motion"]["complete"] is False
    assert "components" not in data["motion"]


def test_stale_revision():
    session = Session()
    data = session.run(LOCK)
    with pytest.raises(ValueError, match="stale"):
        session.dispatch(
            {
                "op": "drag",
                "revision": data["revision"] - 1,
                "keys": ["r1:b"],
                "targets": [[0, 1, 0]],
            }
        )


def test_partial_lock_with_mobile_component():
    engine = Engine(build_scene(LOCK + '\nfree=rod(Vec(5,0),Vec(5,1),id="free")'))
    before = engine.current.copy()
    m = engine.mobility()
    assert m["first_order"] == 4
    assert m["linear_compatible_dimension"] == 3
    engine.drag(["r1:b"], [[0, 0.2, 0]])
    np.testing.assert_allclose(engine.current[:4], before[:4], atol=1e-10)
    engine.drag(["free:b"], [[6, 1, 0]])
    assert np.linalg.norm(engine.current - before) > 0.01


def test_no_float_atoms_in_exact_scene():
    import sympy

    scene = build_scene("r=rod(origin,Vec(0,sqrt(1.75)))")
    assert not any(
        sympy.sympify(v).has(sympy.Float)
        for p in scene.objects[0].points.values()
        for v in p
    )


def test_geometric_primitives():
    from kinematics.core.geometry import Circle, Line, Plane, Sphere, intersect

    assert len(intersect(Circle((0, 0), 1), Circle((2, 0), 1)).points) == 1
    assert intersect(Line((0, 0, 2), (0, 0, -1)), Circle((0, 0, 0), 1)).kind == "empty"
    assert intersect(Plane((0, 0, 0), (0, 0, 1)), Sphere((0, 0, 0), 2)).kind == "circle"


def test_fourbar_critical_incidence():
    source = """
g=rod(origin,right*3,id="g",fixed=True)
a=rod(origin,Vec(2,0),id="a")
b=rod(Vec(3,0),Vec(2,1),id="b")
c=rod(a.end,b.end,id="c")
coincident(g.start,a.start)
coincident(g.end,b.start)
coincident(a.end,c.start)
coincident(b.end,c.end)
"""
    data = Session().run(source, mode="topological")
    assert data["motion"]["status"] == "certified"
    assert len(data["motion"]["components"]) == 1
    assert len(data["motion"]["cells"]) == 2
    assert all(len(v) == 2 for v in data["motion"]["incidence"].values())


def test_fourbar_isolated_critical_point():
    source = """
g=rod(origin,right*4,id="g",fixed=True)
a=rod(origin,right*2,id="a")
b=rod(right*4,right*3,id="b")
c=rod(a.end,b.end,id="c")
coincident(g.start,a.start)
coincident(g.end,b.start)
coincident(a.end,c.start)
coincident(b.end,c.end)
"""
    data = Session().run(source, mode="topological")
    assert data["motion"]["status"] == "certified"
    assert [c["dimension"] for c in data["motion"]["cells"]] == [0]


def test_numerical_reassembly_and_local_lock():
    session = Session()
    data = session.run(TRIANGLE)
    before = data["configuration"]
    assert session.drag(["r1:b"], [[0, -2, 0]])["configuration"] == before
    after = session.reassemble(["r1:b"], [[0, -2, 0]])
    assert after["configuration"]["r1:b"][1] < -1.3
    assert after["mobility"]["residual"] < 1e-9
    with pytest.raises(ValueError, match="certified"):
        session.select(0)


def test_reassembly_does_not_create_motion_in_unique_lock():
    session = Session()
    before = session.run(LOCK)["configuration"]
    after = session.reassemble(["r1:b"], [[0, 0.5, 0]])
    assert after["configuration"] == before


def test_reassembly_leaves_other_components_unchanged():
    session = Session()
    before = session.run(TRIANGLE + '\nfree=rod(Vec(5,0),Vec(5,1),id="free")')[
        "configuration"
    ]
    after = session.reassemble(["r1:b"], [[0, -2, 0]])["configuration"]
    assert after["r1:b"][1] < -1.3
    assert after["free:a"] == before["free:a"]
    assert after["free:b"] == before["free:b"]


def test_dimension_directive_and_auto_detection():
    assert build_scene("r=rod(origin,up)").dimension == 2
    assert build_scene("r=rod(origin,Vec(1,0,1))").dimension == 3
    assert build_scene("scene_dimension(3)\nr=rod(origin,up)").dimension == 3
    assert (
        Engine(build_scene("scene_dimension(3)\nr=rod(origin,up)")).mobility()[
            "first_order"
        ]
        == 5
    )
    assert Engine(build_scene("r=rod(origin,up)")).mobility()["first_order"] == 3
    assert build_scene('b=body({"tip":Vec(2,1)})').dimension == 2
    assert build_scene('b=body({"tip":Vec(2,1,1)})').dimension == 3
    with pytest.raises(ValueError):
        build_scene("scene_dimension(2)\nr=rod(origin,Vec(1,0,1))")


def test_plane_constraint_for_rod_and_body():
    e = Engine(
        build_scene(
            "scene_dimension(3)\nr=rod(origin,Vec(1,0,1))\npin(r.start,origin)\nplane(r,origin,up)"
        )
    )
    e.assemble()
    assert e.mobility()["first_order"] == 1
    result = e.drag(["r1:b"], [[1, 1, 1]])
    assert abs(result["configuration"]["r1:b"][1]) < 1e-9
    e = Engine(build_scene('scene_dimension(3)\nb=body({"tip":Vec(2,0,0)})\nplane(b)'))
    assert e.mobility()["first_order"] == 3


def test_drag_uses_clicked_material_point():
    e = Engine(build_scene("r=rod(origin,up*2)\npin(r.start,origin)"))
    # Grab a quarter of the way along the rod and move that material point.
    targets = [[0.3, -0.1, 0], [0.3, 1.9, 0]]
    for _ in range(4):
        e.drag(["r1:a", "r1:b"], targets, weights=[0.75, 0.25])
    actual = 0.75 * e.current[0] + 0.25 * e.current[1]
    np.testing.assert_allclose(actual, [0.3, 0.4], atol=1e-7)
    assert e.error(e.current) < 1e-9


def test_reassembly_can_escape_mixed_isolated_component():
    source = """
r1=rod(Vec(1,1),Vec(2,0),id="r1")
r2=rod(Vec(1,-1),Vec(2,0),id="r2")
r3=rod(origin,right,id="r3")
r4=rod(Vec(2,0),right,id="r4")
pin(r1.start,Vec(1,1))
pin(r2.start,Vec(1,-1))
pin(r3.start,origin)
coincident(r1.end,r2.end)
coincident(r2.end,r4.start)
coincident(r3.end,r4.end)
"""
    session = Session()
    before = session.run(source)
    assert before["mobility"]["second_order"] == "locked"
    after = session.reassemble(["r3:b"], [[0, 1, 0]])
    np.testing.assert_allclose(after["configuration"]["r1:b"], [0, 0, 0], atol=1e-7)
    assert after["mobility"]["first_order"] == 1
    assert after["mobility"]["residual"] < 1e-9


def test_construction_preview_rotates_about_grab_and_preserves_live_state():
    from kinematics.core.preview import preview

    e = Engine(build_scene('r=rod(origin,up*2,id="r")\npin(r.start,origin)'))
    before = e.configuration()
    p = preview(e, ["r:a", "r:b"], [[0.3, -0.1, 0], [0.3, 1.9, 0]], [0.75, 0.25])
    np.testing.assert_allclose(p["grab"], [0.3, 0.4, 0], atol=1e-12)
    assert p["configuration"]["r:b"][0] > 1
    assert max(p["objects"].values()) < 1e-5
    assert e.configuration() == before


def test_construction_preview_severity_grows_and_includes_all_objects():
    from kinematics.core.preview import preview

    e = Engine(build_scene(LOCK))
    small = preview(e, ["r1:b"], [[0, 0.05, 0]], [1])
    large = preview(e, ["r1:b"], [[0, 1, 0]], [1])
    assert set(large["configuration"]) == set(e.configuration())
    assert set(large["objects"]) == {"r1", "r2"}
    np.testing.assert_allclose(large["grab"], [0, 1, 0], atol=1e-12)
    assert max(large["objects"].values()) > max(small["objects"].values())
    assert max(j["severity"] for j in large["joints"]) > max(
        j["severity"] for j in small["joints"]
    )
    assert e.error(e.current) < 1e-12


def test_construction_preview_keeps_ground_rigid():
    from kinematics.core.preview import preview

    e = Engine(
        build_scene(
            'g=rod(left,right,id="g",fixed=True)\nr=rod(origin,up,id="r")\npin(r.start,origin)'
        )
    )
    p = preview(e, ["r:b"], [[2, 3, 0]], [1])
    assert p["configuration"]["g:a"] == e.configuration()["g:a"]
    assert p["configuration"]["g:b"] == e.configuration()["g:b"]
    np.testing.assert_allclose(p["grab"], [2, 3, 0], atol=1e-12)


def test_concentric_rings_have_two_planar_dofs():
    from pathlib import Path

    source = (
        Path(__file__).parents[1] / "src/kinematics/examples/concentric_rings.py"
    ).read_text()
    scene = build_scene(source)
    e = Engine(scene)
    assert scene.dimension == 2
    assert e.mobility()["first_order"] == 2
    assert e.mobility()["linear_compatible_dimension"] == 2
    before = e.configuration()
    keys = ["inner:origin", "inner:x", "inner:y"]
    targets = [(np.array(before[k]) + [0.2, 0.15, 0]).tolist() for k in keys]
    e.drag(keys, targets, weights=[0.3, 0.4, 0.3])
    assert e.error(e.current) < 1e-9
    assert np.linalg.norm(e.current - e.initial) > 0.01
    for name in ("origin", "x", "y"):
        np.testing.assert_allclose(
            e.configuration()[f"outer:{name}"], before[f"outer:{name}"], atol=1e-10
        )
    p = e.configuration()
    c = np.array(p["inner:origin"])
    assert np.linalg.norm(np.array(p["inner:x"]) - c) == pytest.approx(1.5, abs=1e-8)
    assert np.linalg.norm(np.array(p["inner:y"]) - c) == pytest.approx(1.5, abs=1e-8)


def test_rod_rest_length_assembly_frames_topology_and_roundtrip():
    # Planar rod with explicit length and relative points
    scene = build_scene(
        'r=rod(origin,right,id="r",length=2.5)\nmid_off=r.rel(0.5,0.25)\npin(r.start,origin)'
    )
    assert float(scene.objects[0].rest_length) == 2.5
    restored = Scene.from_dict(scene.to_dict())
    assert restored.objects[0].rest_length == scene.objects[0].rest_length
    e = Engine(restored)
    e.assemble()
    cfg = e.configuration()
    a, b = np.array(cfg["r:a"]), np.array(cfg["r:b"])
    assert np.linalg.norm(b - a) == pytest.approx(2.5, abs=1e-9)
    # Relative point stays at exact world offset (0.5, 0.25) from midpoint
    center = (a + b) / 2
    axis = (b - a) / 2.5
    perp = np.array([-axis[1], axis[0], 0.0])
    rel_pt = np.array(cfg[f"r:{scene.objects[0].relative_points and next(iter(scene.objects[0].relative_points))}"])
    np.testing.assert_allclose(rel_pt, center + 0.5 * axis + 0.25 * perp, atol=1e-9)

    # 3D rod with frame="full" and explicit length
    e3 = Engine(
        build_scene(
            'scene_dimension(3)\nr=rod(origin,right,id="r",frame="full",length=3)\npin(r.start,origin)'
        )
    )
    e3.assemble()
    c3 = e3.configuration()
    assert np.linalg.norm(np.array(c3["r:b"]) - np.array(c3["r:a"])) == pytest.approx(
        3.0, abs=1e-9
    )
    assert e3.error(e3.current) < 1e-9

    # Topological solver respects rod rest_length (3-4-5 triangle)
    session = Session()
    snap = session.run(
        'g=rod(origin,right*3,id="g",fixed=True)\n'
        'a=rod(origin,up,id="a",length=4)\n'
        'b=rod(g.end,up,id="b",length=5)\n'
        'pin(a.start,origin)\n'
        'coincident(a.end,b.end)\n'
        'coincident(b.start,g.end)',
        dimension=2,
        mode="topological",
    )
    assert snap["motion"]["status"] == "certified"
    assert snap["motion"]["cells"][0]["dimension"] == 0
    assert np.linalg.norm(
        np.array(snap["configuration"]["a:b"]) - np.array(snap["configuration"]["a:a"])
    ) == pytest.approx(4.0, abs=1e-9)

    # Validation errors
    with pytest.raises(ValueError):
        build_scene("rod(origin,right,length=0)")
    with pytest.raises(ValueError):
        build_scene("rod(origin,right,length=-2)")
    with pytest.raises(ValueError):
        build_scene("rod(origin,right,fixed=True,length=2)")
    with pytest.raises(ValueError):
        build_scene("r=rod(origin,right,length=2)\nfixed(r)")

    # Cable with shorter rest length assembles within limit
    ec = Engine(
        build_scene(
            'a=body({},fixed=True)\nb=body({},center=right*3)\ncable(a.origin,b.origin,length=1.5)'
        )
    )
    ec.assemble()
    cc = ec.configuration()
    assert np.linalg.norm(
        np.array(cc["body2:origin"]) - np.array(cc["body1:origin"])
    ) <= 1.5 + 1e-9
