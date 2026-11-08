"""Check the live UI and native/Pyodide parity on an already-running Vite server.

uv run --project kinematics --extra browser python scripts/check-browser.py
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kinematics" / "src"))
from kinematics import Session

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://localhost:5173")
parser.add_argument("--chromium", default="/usr/bin/chromium")
parser.add_argument("--output", default="/tmp/cad-review")
args = parser.parse_args()
Path(args.output).mkdir(parents=True, exist_ok=True)
examples = Path(__file__).resolve().parents[1] / "kinematics/src/kinematics/examples"
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=args.chromium, headless=True, args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def choose(label, option):
        page.get_by_role("button", name=label, exact=True).click()
        page.get_by_role("listbox", name=label, exact=True).get_by_role(
            "option", name=option, exact=True
        ).click()

    page.goto(args.url)
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    choose("Solver mode", "Topological")
    page.locator(".viewer strong").filter(has_text="certified").wait_for(timeout=60000)
    for name in ["collinear", "triangle", "mixed", "four_bar", "spatial"]:
        dimension = 3 if name == "spatial" else 2
        if name == "spatial":
            choose("Scene dimension", "Spatial (3D)")
            page.get_by_role("button", name="Run", exact=True).wait_for(state="visible")
            page.wait_for_function(
                "!document.querySelector('button.btn--primary').disabled", timeout=60000
            )
        source = (examples / f"{name}.py").read_text()
        page.locator("textarea").fill(source)
        page.get_by_role("button", name="Run", exact=True).click()
        status = "fallback" if name == "spatial" else "certified"
        page.locator(".viewer strong").filter(has_text=status).wait_for(timeout=60000)
        result = page.evaluate(
            "async () => (await import(performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name)).request({op:'snapshot'})"
        )
        native = Session().run(source, dimension, "topological")
        assert result["motion"]["status"] == native["motion"]["status"]
        assert [c["dimension"] for c in result["motion"]["cells"]] == [
            c["dimension"] for c in native["motion"]["cells"]
        ]
        for key, point in native["configuration"].items():
            np.testing.assert_allclose(result["configuration"][key], point, atol=1e-8)
        if name == "collinear":
            joint = page.locator('[data-point="r1:b"]')
            box = joint.bounding_box()
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x, y - 60, steps=8)
            page.wait_for_timeout(750)
            page.mouse.up()
            after = page.evaluate(
                "async () => (await import(performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name)).request({op:'snapshot'})"
            )
            assert after["configuration"] == result["configuration"]
        if name == "triangle":
            page.get_by_role("button", name="⌖ Orbits", exact=True).click()
            assert page.locator(".viewer svg > path").count() == 0
        if name == "mixed":
            choose("Component or chart", "1: 0D isolated")
            page.wait_for_timeout(250)
        if name == "spatial":
            assert page.locator('[data-grid-view="spatial"]').count() == 1
            assert page.locator("[data-grid-plane]").count() == 3
            assert page.locator("[data-grid-axis]").count() == 3
            page.screenshot(path=str(Path(args.output) / "browser-spatial-grids.png"))
            for view in ("XY", "YZ", "XZ"):
                page.get_by_role("button", name=view, exact=True).click()
                assert page.locator("[data-grid-plane]").count() == 1
                assert page.locator(f'[data-grid-plane="{view}"]').count() == 1
                assert page.locator('[data-grid-view="spatial"]').count() == 0
            choose("Drag plane", "XZ")
        page.screenshot(path=str(Path(args.output) / f"browser-{name}.png"))
        print(name, status, "native/Pyodide parity OK")
    choose("Scene dimension", "Auto dimension")
    page.wait_for_function(
        "!document.querySelector('button.btn--primary').disabled", timeout=60000
    )
    choose("Solver mode", "Numerical")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=60000)
    source = (examples / "triangle.py").read_text()
    page.locator("textarea").fill(source)
    page.get_by_role("button", name="Run", exact=True).click()
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=60000)
    assert (
        page.get_by_role("button", name="Component or chart", exact=True).count() == 0
    )
    assert page.locator("select").count() == 0
    # Grab near one end of the rod; the ghost must retain that point under the pointer.
    segment = page.locator('[data-object="r1"]').first
    endpoints = segment.evaluate(
        "e => { const l=e.querySelector('line'),r=e.ownerSVGElement.getBoundingClientRect(); return [l.x1.baseVal.value+r.x,l.y1.baseVal.value+r.y,l.x2.baseVal.value+r.x,l.y2.baseVal.value+r.y] }"
    )
    x = 0.7 * endpoints[0] + 0.3 * endpoints[2]
    y = 0.7 * endpoints[1] + 0.3 * endpoints[3]
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 70, y + 35, steps=5)
    ghost = page.locator('[data-drag-ghost="construction"]')
    assert ghost.locator("[data-ghost-object]").count() == 2
    page.wait_for_function(
        "Array.from(document.querySelectorAll('[data-ghost-edge]')).some(e => Number(e.dataset.severity) > .01)",
        timeout=30000,
    )
    grab = ghost.locator("[data-grab-target]").bounding_box()
    np.testing.assert_allclose(
        [grab["x"] + grab["width"] / 2, grab["y"] + grab["height"] / 2],
        [x + 70, y + 35],
        atol=1,
    )
    page.screenshot(path=str(Path(args.output) / "browser-object-ghost.png"))
    page.mouse.up()
    # Shift-drag explicitly changes assembly mode; ordinary dragging above stays feasible.
    joint = page.locator('[data-point="r1:b"]')
    box = joint.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.keyboard.down("Shift")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + 380, steps=10)
    page.mouse.up()
    page.keyboard.up("Shift")
    page.wait_for_function(
        "!document.body.textContent.includes('Reassembling near the ghost')",
        timeout=60000,
    )
    result = page.evaluate(
        "async () => (await import(performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name)).request({op:'snapshot'})"
    )
    assert result["configuration"]["r1:b"][1] < 0
    assert result["mobility"]["residual"] < 1e-9
    # The grid remains anchored to world space during viewport panning.
    grid = page.locator(".viewer pattern")
    origin = [float(grid.get_attribute("x")), float(grid.get_attribute("y"))]
    page.mouse.move(1210, 760)
    page.mouse.down()
    page.mouse.move(1245, 780, steps=3)
    page.mouse.up()
    shifted = [float(grid.get_attribute("x")), float(grid.get_attribute("y"))]
    np.testing.assert_allclose(np.array(shifted) - origin, [35, 20], atol=0.01)
    # Keyboard operation and Escape dismissal of custom menus.
    trigger = page.get_by_role("button", name="Scene dimension", exact=True)
    trigger.focus()
    page.keyboard.press("ArrowDown")
    page.get_by_role("listbox", name="Scene dimension").wait_for()
    page.keyboard.press("Escape")
    assert trigger.get_attribute("aria-expanded") == "false"
    page.get_by_role("button", name="Solver mode", exact=True).click()
    page.screenshot(path=str(Path(args.output) / "browser-dropdown.png"))
    page.keyboard.press("Escape")
    print(
        "Object ghost, grabbed point, numerical reassembly, auto dimension, and custom dropdown checks passed"
    )
    assert not errors, errors
    page.locator("textarea").fill("while True: pass")
    page.get_by_role("button", name="Run", exact=True).click()
    page.wait_for_timeout(400)
    page.get_by_role("button", name="Stop", exact=True).click()
    page.wait_for_function("!document.querySelector('button.btn--primary').disabled")
    browser.close()
    print("UI drag, orbits, camera, plane selection, and Stop checks passed")
