"""Check streamed wandering, pose handoff, and orbitable roadmap on :5173."""

import json
from math import dist
from pathlib import Path

from browser_editor import fill_editor
from playwright.sync_api import sync_playwright

source = Path("kinematics/src/kinematics/examples/concentric_rings.py").read_text()
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    data = {"id": "wander", "name": "rings.py", "body": source, "editedAt": 0}
    page.add_init_script(
        "if(location.hostname==='localhost'){localStorage.setItem('linklab.files.v2',JSON.stringify(["
        + json.dumps(data)
        + "]));localStorage.setItem('linklab.active.v1','wander');localStorage.setItem('linklab.split.v1','32');}"
    )
    page.goto("http://localhost:5173")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    panel = page.locator(".exploration-panel")
    assert (
        page.get_by_role("button", name="∂² Tangents", exact=True).get_attribute(
            "aria-pressed"
        )
        == "false"
    )
    inner = page.locator('[data-ring="inner"] path').first
    initial = inner.get_attribute("d")
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    panel.get_by_role("button", name="Pause wander", exact=True).wait_for(timeout=60000)
    page.wait_for_function(
        "initial=>document.querySelector('[data-ring=inner] path').getAttribute('d')!==initial",
        arg=initial,
    )
    assert panel.get_by_role("button", name="Explore", exact=True).is_disabled()
    page.wait_for_timeout(1500)
    panel.get_by_role("button", name="Pause wander", exact=True).click()
    page.wait_for_timeout(100)
    paused = inner.get_attribute("d")
    page.wait_for_timeout(400)
    assert inner.get_attribute("d") == paused
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    page.wait_for_function(
        "paused=>document.querySelector('[data-ring=inner] path').getAttribute('d')!==paused",
        arg=paused,
    )
    panel.get_by_role("button", name="Pause wander", exact=True).click()
    panel.get_by_role("button", name="Use wander pose", exact=True).click()
    panel.get_by_role("button", name="Use wander pose", exact=True).wait_for(
        state="hidden"
    )
    snapshot = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert snapshot["mobility"]["residual"] < 1e-9
    assert snapshot["configuration"]["inner:origin"] != [0, 0, 0]
    panel.get_by_role("button", name="Start wander", exact=True).click()
    panel.get_by_role("button", name="Pause wander", exact=True).wait_for(timeout=60000)
    page.wait_for_timeout(500)
    panel.get_by_role("button", name="Pause wander", exact=True).click()
    panel.locator("summary").first.click()
    point = inner.evaluate(
        "el=>{const p=el.getPointAtLength(el.getTotalLength()/8);const q=new DOMPoint(p.x,p.y).matrixTransform(el.getScreenCTM());return {x:q.x,y:q.y}}"
    )
    page.mouse.move(point["x"], point["y"])
    page.mouse.down()
    page.wait_for_timeout(200)
    page.mouse.move(point["x"] + 12, point["y"] + 5, steps=4)
    page.mouse.up()
    panel.locator("summary").first.click()
    assert panel.get_by_role("button", name="Resume wander", exact=True).count() == 0
    assert panel.get_by_role("button", name="Start wander", exact=True).is_enabled()
    Path("/tmp/cad-review").mkdir(exist_ok=True)
    page.screenshot(path="/tmp/cad-review/wander-rings.png")

    def run(source):
        fill_editor(page, source)
        page.get_by_role("button", name="Run", exact=True).click()
        page.locator(".viewer strong").filter(has_text="numerical").wait_for()
        page.locator(".exploration-panel summary").first.click()

    rotor_source = Path(
        "kinematics/src/kinematics/examples/spatial_rotor.py"
    ).read_text()
    run(rotor_source)
    assert "1st order: 3" in page.locator(".viewer").inner_text()
    line = page.locator('[data-object="rotor"] line').first
    initial_x = line.get_attribute("x2")
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    panel.get_by_role("button", name="Pause wander", exact=True).wait_for()
    page.wait_for_function(
        "x=>document.querySelector('[data-object=rotor] line').getAttribute('x2')!==x",
        arg=initial_x,
    )
    page.wait_for_timeout(1200)
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    panel.get_by_role("button", name="Resume wander", exact=True).wait_for()
    page.screenshot(path="/tmp/cad-review/spatial-rotor-wander.png")
    run(
        Path(
            "kinematics/src/kinematics/examples/spatial_linked_pendulum.py"
        ).read_text()
    )
    assert "1st order: 3" in page.locator(".viewer").inner_text()
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    panel.get_by_role("button", name="Pause wander", exact=True).wait_for()
    page.wait_for_timeout(1200)
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    panel.get_by_role("button", name="Resume wander", exact=True).wait_for()
    page.screenshot(path="/tmp/cad-review/spatial-pendulum-wander.png")
    panel.get_by_role("button", name="Use wander pose", exact=True).click()
    panel.get_by_role("button", name="Use wander pose", exact=True).wait_for(
        state="hidden"
    )
    snapshot = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert snapshot["mobility"]["residual"] < 1e-9
    assert snapshot["mobility"]["first_order"] == 3, snapshot["mobility"]
    assert dist(snapshot["configuration"]["a:a"], [-1, 0, 0]) < 1e-9
    assert dist(snapshot["configuration"]["b:a"], [1, 0, 0]) < 1e-9
    run('r=rod(origin,up,id="r",fixed=True)')
    panel.get_by_role("button", name="Start wander", exact=True).click()
    panel.get_by_text("No continuous motion", exact=False).wait_for(timeout=30000)
    run('r=rod(origin,up,id="r")\npin(r.start,origin)')
    panel.get_by_role("button", name="Explore", exact=True).click()
    page.wait_for_function(
        "document.querySelector('.exploration-panel').textContent.includes('frontier_exhausted')",
        timeout=90000,
    )
    panel.get_by_role("button", name="Roadmap (3D projection)").click()
    graph = panel.get_by_label("Explored configuration graph")
    graph.wait_for()
    graph.scroll_into_view_if_needed()
    camera = graph.get_attribute("data-camera")
    box = graph.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 50, y + 20, steps=8)
    page.mouse.up()
    page.wait_for_function(
        "camera=>document.querySelector('[data-camera]').getAttribute('data-camera')!==camera",
        arg=camera,
    )
    camera = graph.get_attribute("data-camera")
    graph.press("ArrowLeft")
    page.wait_for_function(
        "camera=>document.querySelector('[data-camera]').getAttribute('data-camera')!==camera",
        arg=camera,
    )
    graph.press("+")
    page.wait_for_function(
        "Number(document.querySelector('[data-camera]').getAttribute('data-camera').split(',')[2])>1"
    )
    assert graph.locator("circle").count() > 4
    assert "NaN" not in graph.inner_html()
    page.screenshot(path="/tmp/cad-review/roadmap-3d.png")
    assert not errors, errors
    print(
        "Wander streaming, pause/resume, adoption, drag handoff, isolation and 3D roadmap orbit passed"
    )
    browser.close()
