"""Check the optional Three.js renderer, picking, animation and plane fallback."""

import json
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

source = Path("kinematics/src/kinematics/examples/spatial_rotor.py").read_text()
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    )
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    entry = {"id": "three", "name": "rotor.py", "body": source, "editedAt": 0}
    page.add_init_script(
        "if(location.hostname==='localhost'){localStorage.setItem('cad-detect-free-motions.files.v2',JSON.stringify(["
        + json.dumps(entry)
        + "]));localStorage.setItem('cad-detect-free-motions.active.v1','three');localStorage.setItem('cad-detect-free-motions.split.v1','32');}"
    )
    page.goto("http://localhost:5173")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    target = page.locator('[data-point="rotor:y"]').bounding_box()
    x, y = target["x"] + target["width"] / 2, target["y"] + target["height"] / 2

    def choose(value):
        page.get_by_role("button", name="3D renderer", exact=True).click()
        page.get_by_role("listbox", name="3D renderer").get_by_role(
            "option", name=value, exact=True
        ).click()

    choose("Three.js")
    canvas = page.get_by_label("Three.js construction")
    page.locator("canvas[data-ready=true]").wait_for(timeout=60000)
    assert int(canvas.get_attribute("data-mesh-count")) == 27
    assert page.locator("[data-scene-element]").count() == 0
    assert page.locator(".three-label:visible").count() == 2
    assert page.locator("[data-grid-plane]").count() == 3
    assert canvas.evaluate("c=>Boolean(c.getContext('webgl2'))")
    Path("/tmp/cad-review").mkdir(exist_ok=True)
    page.screenshot(path="/tmp/cad-review/three-orthographic.png")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 25, y + 15, steps=8)
    page.locator("[data-grab-target]").wait_for(timeout=30000)
    page.wait_for_timeout(200)
    ghost = page.locator("[data-grab-target]").bounding_box()
    np.testing.assert_allclose(
        [ghost["x"] + ghost["width"] / 2, ghost["y"] + ghost["height"] / 2],
        [x + 25, y + 15],
        atol=1.5,
    )
    page.mouse.up()
    result = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert result["mobility"]["residual"] < 1e-9
    page.get_by_role("button", name="Perspective view", exact=True).click()
    page.wait_for_function(
        "document.querySelector('[data-projection]').dataset.projection==='perspective'"
    )
    page.screenshot(path="/tmp/cad-review/three-perspective.png")
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    page.get_by_role("button", name="Pause wander", exact=True).wait_for()
    label = page.locator('[data-object-label="rotor"]')
    transform = label.get_attribute("style")
    page.wait_for_function(
        "style=>document.querySelector('[data-object-label=rotor]').getAttribute('style')!==style",
        arg=transform,
    )
    choose("SVG")
    canvas.wait_for(state="hidden")
    assert page.get_by_role("button", name="Pause wander", exact=True).count() == 1
    choose("Three.js")
    page.locator("canvas[data-ready=true]").wait_for(timeout=30000)
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    page.get_by_role("button", name="Resume wander", exact=True).wait_for()
    for view in ("XY", "XZ", "YZ"):
        if (
            page.get_by_role(
                "button", name="Perspective view", exact=True
            ).get_attribute("aria-pressed")
            == "false"
        ):
            page.get_by_role("button", name="Perspective view", exact=True).click()
        page.get_by_role("button", name=view, exact=True).click()
        canvas.wait_for(state="hidden")
        page.wait_for_function(
            "document.querySelector('[data-projection]').dataset.projection==='orthographic'"
        )
        assert page.get_by_role("button", name="3D renderer", exact=True).count() == 0
        assert page.locator("[data-scene-element]").count() > 0
        assert page.locator(f'[data-grid-plane="{view}"]').count() == 1
        page.get_by_role("button", name="3D", exact=True).click()
        page.locator("canvas[data-ready=true]").wait_for(timeout=30000)
    page.emulate_media(color_scheme="dark")
    page.wait_for_timeout(300)
    assert (
        page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--cad-bg').trim()"
        )
        == "#090d16"
    )
    page.screenshot(path="/tmp/cad-review/three-dark.png")
    choose("SVG")
    assert not errors, errors
    print(
        "Three.js capsules, joints, labels, picking, Wander, projection matching and orthographic plane fallback passed"
    )
    browser.close()
