"""Check dimensional camera gestures and navigation during Wander on :5173."""

import json
from pathlib import Path

import numpy as np
from browser_editor import fill_editor
from playwright.sync_api import sync_playwright

source = Path("kinematics/src/kinematics/examples/spatial_rotor.py").read_text()
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    data = {"id": "nav", "name": "navigation.py", "body": source, "editedAt": 0}
    page.add_init_script(
        "if(location.hostname==='localhost'){localStorage.setItem('linklab.files.v2',JSON.stringify(["
        + json.dumps(data)
        + "]));localStorage.setItem('linklab.active.v1','nav');localStorage.setItem('linklab.split.v1','32');}"
    )
    page.goto("http://localhost:5173")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    canvas = page.locator("svg[data-cad-camera]")

    def check_depth_order():
        elements = canvas.locator("[data-scene-element]").evaluate_all(
            "nodes=>nodes.map(n=>({id:n.dataset.sceneElement,depth:Number(n.dataset.depth),kind:n.dataset.elementKind}))"
        )
        depths = [e["depth"] for e in elements]
        assert depths == sorted(depths)
        assert (
            sum(e["kind"] == "rod" and e["id"].startswith("rotor:") for e in elements)
            == 6
        )
        assert {e["kind"] for e in elements} == {"rod", "joint", "label"}

    check_depth_order()
    Path("/tmp/cad-review").mkdir(exist_ok=True)
    page.screenshot(path="/tmp/cad-review/rotor-upright.png")

    def values(attribute):
        return np.array([float(v) for v in canvas.get_attribute(attribute).split(",")])

    def drag(x, y, dx, dy, modifier=None):
        if modifier:
            page.keyboard.down(modifier)
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + dx, y + dy, steps=8)
        page.mouse.up()
        if modifier:
            page.keyboard.up(modifier)
        page.wait_for_timeout(100)

    camera = values("data-cad-camera")
    drag(500, 750, 40, 20)
    check_depth_order()
    np.testing.assert_allclose(values("data-cad-camera") - camera, [-0.32, 0.16])
    np.testing.assert_allclose(values("data-cad-pan"), [0, 0])
    camera = values("data-cad-camera")
    assert page.get_by_role("button", name="Drag plane", exact=True).count() == 0
    projection = page.get_by_role("button", name="Perspective view", exact=True)
    assert projection.get_attribute("aria-pressed") == "false"
    before = page.locator('[data-object="rotor"] line').first.get_attribute("x2")
    projection.click()
    page.wait_for_function(
        "document.querySelector('[data-projection]').dataset.projection==='perspective'"
    )
    assert projection.get_attribute("aria-pressed") == "true"
    assert (
        page.locator('[data-object="rotor"] line').first.get_attribute("x2") != before
    )
    joint = page.locator('[data-point="rotor:y"]').bounding_box()
    x, y = joint["x"] + joint["width"] / 2, joint["y"] + joint["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 25, y + 15, steps=8)
    page.locator("[data-grab-target]").wait_for()
    page.wait_for_timeout(200)
    target = page.locator("[data-grab-target]").bounding_box()
    np.testing.assert_allclose(
        [target["x"] + target["width"] / 2, target["y"] + target["height"] / 2],
        [x + 25, y + 15],
        atol=1,
    )
    page.screenshot(path="/tmp/cad-review/rotor-perspective-drag.png")
    page.mouse.up()
    assert "NaN" not in canvas.inner_html()
    joint = page.locator('[data-point="rotor:origin"]').bounding_box()
    drag(
        joint["x"] + joint["width"] / 2,
        joint["y"] + joint["height"] / 2,
        30,
        20,
        "Shift",
    )
    np.testing.assert_allclose(values("data-cad-camera"), camera)
    np.testing.assert_allclose(values("data-cad-pan"), [30, 20])
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    page.get_by_role("button", name="Pause wander", exact=True).wait_for(timeout=30000)
    page.wait_for_timeout(500)
    drag(500, 750, 30, 0)
    check_depth_order()
    assert page.get_by_role("button", name="Pause wander", exact=True).count() == 1
    assert (
        page.get_by_role("button", name="Toggle wander", exact=True).get_attribute(
            "aria-pressed"
        )
        == "true"
    )
    page.get_by_role("button", name="Stop wander", exact=True).click()
    fill_editor(page, 'r=rod(origin,up,id="r")\npin(r.start,origin)')
    page.get_by_role("button", name="Run", exact=True).click()
    page.locator(".viewer strong").filter(has_text="numerical").wait_for()
    assert page.get_by_role("button", name="Perspective view", exact=True).count() == 0
    assert canvas.get_attribute("data-projection") == "orthographic"
    drag(500, 750, 40, 20, "Shift")
    np.testing.assert_allclose(values("data-cad-camera"), [0, 0])
    np.testing.assert_allclose(values("data-cad-pan"), [0, 0])
    joint = page.locator('[data-point="r:b"]').bounding_box()
    before = page.locator('[data-point="r:b"]').inner_html()
    drag(
        joint["x"] + joint["width"] / 2,
        joint["y"] + joint["height"] / 2,
        30,
        20,
        "Shift",
    )
    assert page.locator('[data-point="r:b"]').inner_html() == before
    assert page.locator("[data-drag-ghost]").count() == 0
    drag(500, 750, 30, 20)
    np.testing.assert_allclose(values("data-cad-pan"), [30, 20])
    assert not errors, errors
    print(
        "3D orbit direction, Shift-pan over objects, animated navigation and 2D gestures passed"
    )
    browser.close()
