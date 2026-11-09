"""Verify the rings example and material-point dragging on the existing server."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

source = Path("kinematics/src/kinematics/examples/concentric_rings.py").read_text()
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    )
    page = b.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    data = {"id": "rings", "name": "concentric-rings.py", "body": source, "editedAt": 0}
    page.add_init_script(
        "if(location.hostname==='localhost'){localStorage.setItem('cad-detect-free-motions.files.v2',JSON.stringify(["
        + json.dumps(data)
        + "]));localStorage.setItem('cad-detect-free-motions.active.v1','rings');localStorage.setItem('cad-detect-free-motions.split.v1','32');}"
    )
    page.goto("http://localhost:5173")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    assert "1st order: 2" in page.locator(".viewer").inner_text()
    assert page.locator('[data-ring="outer"]').count() == 1
    assert page.locator('[data-ring="inner"]').count() == 1
    point = page.locator('[data-ring="inner"] path').first.evaluate(
        "el=>{const p=el.getPointAtLength(el.getTotalLength()/8);const q=new DOMPoint(p.x,p.y).matrixTransform(el.getScreenCTM());return {x:q.x,y:q.y}}"
    )
    x, y = point["x"], point["y"]
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 25, y + 15, steps=8)
    page.locator('[data-ghost-ring="inner"]').wait_for(timeout=30000)
    assert page.locator("[data-ghost-ring]").count() == 2
    page.wait_for_timeout(200)
    page.mouse.up()
    result = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert result["mobility"]["residual"] < 1e-9
    assert result["mobility"]["first_order"] == 2
    page.get_by_role("button", name="Recent files", exact=True).click()
    page.get_by_role("listbox", name="Recent files").get_by_role("option").filter(
        has_text="concentric-rings-3d.py"
    ).click()
    page.locator('[data-point="inner:bottom"]').wait_for(timeout=30000)
    result = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert result["configuration"]["inner:bottom"] == [0, -1.5, 0]
    assert result["configuration"]["outer:bottom"] == [0, -3, 0]
    assert result["mobility"]["residual"] < 1e-9
    assert result["mobility"]["linear_compatible_dimension"] == 1
    Path("/tmp/cad-review").mkdir(exist_ok=True)
    page.screenshot(path="/tmp/cad-review/rings-top-bottom-svg.png")
    page.get_by_role("button", name="3D renderer", exact=True).click()
    page.get_by_role("listbox", name="3D renderer").get_by_role(
        "option", name="Three.js", exact=True
    ).click()
    page.locator("canvas[data-ready=true]").wait_for(timeout=30000)
    assert (
        int(page.get_by_label("Three.js construction").get_attribute("data-mesh-count"))
        == 16
    )
    page.screenshot(path="/tmp/cad-review/rings-top-bottom-three.png")
    before = page.locator('[data-object-label="inner"]').get_attribute("style")
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    page.get_by_role("button", name="Pause wander", exact=True).wait_for(timeout=90000)
    page.wait_for_function(
        "style=>document.querySelector('[data-object-label=inner]').getAttribute('style')!==style",
        arg=before,
    )
    page.wait_for_timeout(1500)
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    page.get_by_role("button", name="Resume wander", exact=True).wait_for()
    page.get_by_role("button", name="Use wander pose", exact=True).click()
    page.get_by_role("button", name="Use wander pose", exact=True).wait_for(
        state="hidden"
    )
    result = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert result["mobility"]["residual"] < 1e-9
    assert abs(result["configuration"]["inner:origin"][0]) < 1e-8
    assert abs(result["configuration"]["inner:bottom"][1] + 1.5) < 1e-8
    assert "Traceback" not in page.locator(".viewer").inner_text()
    page.screenshot(path="/tmp/cad-review/rings-braced-wander.png")
    assert not errors, errors
    print(
        "Ring dragging, 3D preset, antipodal markers, SVG/Three.js and singular-linkage Wander passed"
    )
    b.close()
