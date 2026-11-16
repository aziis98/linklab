"""Check toolbar Wander, popover lifetime, locked-state feedback and point labels."""

import argparse
import json
from pathlib import Path

from browser_editor import fill_editor
from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://localhost:5183")
args = parser.parse_args()
source = Path("kinematics/src/kinematics/examples/hopf_link.py").read_text()
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    )
    page = browser.new_page(viewport={"width": 1400, "height": 920})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    entry = {"id": "hopf-test", "name": "hopf.py", "body": source, "editedAt": 0}
    page.add_init_script(
        "localStorage.setItem('linklab.files.v2', JSON.stringify(["
        + json.dumps(entry)
        + "]));localStorage.setItem('linklab.active.v1','hopf-test');"
    )
    page.goto(args.url)
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    expect(page.locator("[data-point-label]")).to_have_count(8)
    page.get_by_role("button", name="3D renderer", exact=True).click()
    page.get_by_role("option", name="Three.js", exact=True).click()
    page.locator("canvas[data-ready=true]").wait_for(timeout=60000)
    for label in ("a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4"):
        expect(page.locator(f'[data-point-label="{label}"]')).to_be_visible()
    page.get_by_role("button", name="3D renderer", exact=True).click()
    page.get_by_role("option", name="SVG", exact=True).click()
    expect(page.get_by_role("button", name="Stop", exact=True)).to_have_count(0)
    expect(
        page.locator("header").get_by_role("button", name="Toggle wander")
    ).to_be_visible()
    page.get_by_role("button", name="Toggle wander").click()
    dialog = page.get_by_role("dialog", name="Motion exploration")
    expect(dialog).to_be_visible(timeout=30000)
    expect(dialog.get_by_text("Wander unavailable", exact=True)).to_be_visible()
    assert "Traceback" not in dialog.inner_text()
    assert not page.locator(".viewer pre[role=alert]").count()
    slider = dialog.get_by_role("slider", name="Wander speed")
    expect(slider).to_have_value("1")
    dialog.get_by_text("Manifold exploration", exact=True).click()
    expect(page.get_by_role("button", name="Sample & build tour")).to_have_count(0)
    assert dialog.bounding_box()["y"] >= page.locator("header").bounding_box()["height"]
    Path("/tmp/cad-review").mkdir(exist_ok=True)
    page.screenshot(path="/tmp/cad-review/wander-locked-popover.png")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role("button", name="Wander settings")).to_be_focused()
    page.get_by_role("button", name="Wander settings").click()
    page.get_by_role("button", name="Wander steering").click()
    page.keyboard.press("Escape")
    expect(dialog).to_be_visible()
    page.get_by_role("button", name="Wander steering").click()
    page.get_by_role("option", name="Gentle turns", exact=True).click()
    expect(dialog).to_be_visible()
    page.mouse.click(450, 700)
    expect(dialog).not_to_be_visible()
    fill_editor(
        page, 'scene_dimension(3)\narm=rod(left,right,id="arm")\npin(arm.start)'
    )
    page.get_by_role("button", name="Run", exact=True).click()
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=30000)
    toggle = page.get_by_role("button", name="Toggle wander")
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "true", timeout=30000)
    page.get_by_role("button", name="Wander settings").click()
    slider = page.get_by_role("slider", name="Wander speed")
    expect(slider).to_have_value("1")
    slider.focus()
    slider.press("ArrowRight")
    expect(slider).to_have_value("1.25")
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-pressed", "true")
    page.wait_for_timeout(1200)
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    page.get_by_role("button", name="Wander settings").click()
    expect(dialog.get_by_text("Use wander pose", exact=True)).to_be_visible()
    page.screenshot(path="/tmp/cad-review/wander-toolbar.png")
    page.set_viewport_size({"width": 800, "height": 850})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path="/tmp/cad-review/wander-toolbar-narrow.png")
    assert not errors, errors
    print(
        "Toolbar, labels, locked feedback, popover keyboard/outside dismissal, slider and background playback passed"
    )
    browser.close()
