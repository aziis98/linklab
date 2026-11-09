"""Exercise the incremental explorer and tour UI on the existing :5173 server.

Run with the optional browser extra and an installed /usr/bin/chromium.
"""

from browser_editor import fill_editor
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    page = b.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://localhost:5173")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    fill_editor(page, 'r=rod(origin,up,id="r")\npin(r.start,origin)')
    page.get_by_role("button", name="Run", exact=True).click()
    page.locator(".viewer strong").filter(has_text="numerical").wait_for()
    panel = page.locator(".exploration-panel")
    panel.locator("summary").first.click()
    panel.get_by_role("button", name="Explore", exact=True).click()
    page.wait_for_function(
        "document.querySelector('.exploration-panel').textContent.includes('frontier_exhausted')",
        timeout=90000,
    )
    panel.get_by_role("button", name="Roadmap (3D projection)").click()
    panel.get_by_label("Explored configuration graph").wait_for()
    panel.get_by_role("button", name="Sample & build tour").click()
    panel.get_by_role("button", name="Play tour", exact=True).wait_for(timeout=90000)
    panel.get_by_role("button", name="Play tour", exact=True).click()
    page.wait_for_timeout(1000)
    panel.get_by_role("button", name="Pause tour", exact=True).click()
    page.screenshot(path="/tmp/cad-review/exploration.png")
    # Adopt the currently displayed pose by beginning a manual drag.
    panel.locator("summary").first.click()
    joint = page.locator('[data-point="r:b"]')
    box = joint.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.wait_for_timeout(200)
    page.mouse.move(x + 15, y + 5, steps=3)
    page.mouse.up()
    panel.locator("summary").first.click()
    assert panel.get_by_role("button", name="Play tour", exact=True).count() == 0
    assert (
        panel.get_by_role("button", name="Sample & build tour", exact=True).count() == 1
    )
    # A spatial sphere of motions exercises pause/resume and budget controls.
    fill_editor(
        page, 'scene_dimension(3)\nr=rod(origin,up,id="r")\npin(r.start,origin)'
    )
    page.get_by_role("button", name="Run", exact=True).click()
    page.locator(".viewer strong").filter(has_text="numerical").wait_for()
    panel = page.locator(".exploration-panel")
    panel.locator("summary").first.click()
    panel.get_by_role("button", name="Explore", exact=True).click()
    page.wait_for_function(
        "document.querySelector('.exploration-panel').textContent.includes(' nodes')",
        timeout=30000,
    )
    panel.get_by_role("button", name="Pause", exact=True).click()
    panel.get_by_role("button", name="Resume", exact=True).wait_for()
    panel.get_by_role("button", name="Resume", exact=True).click()
    panel.get_by_role("button", name="Pause", exact=True).wait_for()
    panel.get_by_role("button", name="Cancel", exact=True).click()
    page.wait_for_function("!document.querySelector('.exploration-panel progress')")
    assert not errors, errors
    print(
        "Incremental exploration, roadmap, frame preparation, playback handoff, pause/resume and cancellation passed"
    )
    b.close()
