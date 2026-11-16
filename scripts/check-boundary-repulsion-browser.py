import json

from playwright.sync_api import expect, sync_playwright

source = "scene_dimension(3)\na=body({},fixed=True)\nb=body({},center=right)\ncable(a.origin,b.origin,length=1)"
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    page = b.new_page(viewport={"width": 1400, "height": 900})
    entry = {"id": "repulsion", "name": "cable.py", "body": source, "editedAt": 0}
    page.add_init_script(
        "localStorage.setItem('linklab.files.v2',JSON.stringify(["
        + json.dumps(entry)
        + "]));localStorage.setItem('linklab.active.v1','repulsion');window.repulsionMessages=[];const original=Worker.prototype.postMessage;Worker.prototype.postMessage=function(message,...args){if(message.request?.op==='wander_step')window.repulsionMessages.push(message.request.boundary_repulsion);return original.call(this,message,...args)}"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://localhost:5183")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    page.get_by_role("button", name="Wander settings", exact=True).click()
    slider = page.get_by_role("slider", name="Boundary repulsion")
    expect(slider).to_have_value("0.5")
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    expect(
        page.get_by_role("button", name="Toggle wander", exact=True)
    ).to_have_attribute("aria-pressed", "true", timeout=5000)
    page.get_by_role("button", name="Wander settings", exact=True).click()
    slider.focus()
    slider.press("End")
    expect(slider).to_have_value("4")
    page.wait_for_function("window.repulsionMessages.includes(4)", timeout=30000)
    slider.press("Home")
    expect(slider).to_have_value("0")
    page.wait_for_function("window.repulsionMessages.includes(0)", timeout=30000)
    page.get_by_role("button", name="Toggle wander", exact=True).click()
    assert not errors, errors
    print(
        "Slider default, live strength updates, Off setting, and active playback passed"
    )
    b.close()
