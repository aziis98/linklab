"""Check CodeMirror editing, contextual snippets, linked fields and scene execution."""

import json
import re
from pathlib import Path

from browser_editor import fill_editor
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1400, "height": 950})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    entry = {
        "id": "editor",
        "name": "snippets.py",
        "body": "scene_dimension(2)\nr=rod(origin,up)\npin(r.start)",
        "editedAt": 0,
    }
    page.add_init_script(
        "if(location.hostname==='localhost'){localStorage.setItem('linklab.files.v2',JSON.stringify(["
        + json.dumps(entry)
        + "]));localStorage.setItem('linklab.active.v1','editor');}"
    )
    page.goto("http://localhost:5173")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    editor = page.get_by_role("textbox", name="Scene DSL editor", exact=True)
    assert page.locator("textarea.editor").count() == 0
    assert page.locator(".cm-lineNumbers").count() == 1

    def option(label):
        return page.get_by_role("option").filter(
            has=page.locator(
                ".cm-completionLabel", has_text=re.compile("^" + re.escape(label) + "$")
            )
        )

    def complete():
        editor.press("Control+Space")
        page.locator(".cm-tooltip-autocomplete").wait_for()

    fill_editor(page, "beam=rod(left,up)\nbeam.")
    complete()
    option("start").wait_for()
    assert option("top").count() == 0
    option("start").click()
    assert editor.inner_text().endswith("beam.start")
    fill_editor(page, 'b=body({"tip": up*2})\nb.point("ti")')
    editor.press("ArrowLeft")
    editor.press("ArrowLeft")
    complete()
    option("tip").click()
    assert 'b.point("tip")' in editor.inner_text()
    fill_editor(page, "scene_dimension(2)\nr = ro")
    complete()
    option("rod").click()
    page.wait_for_function("getSelection().toString()==='origin'")
    editor.press("Tab")
    page.wait_for_function("getSelection().toString()==='up'")
    page.keyboard.insert_text("right * 2")
    editor.press("Tab")
    page.wait_for_function("getSelection().toString()==='r'")
    editor.press("Tab")
    editor.press("ControlOrMeta+Enter")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for()
    snapshot = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert snapshot["configuration"]["r:b"] == [2, 0, 0]
    fill_editor(page, "# comment")
    editor.press("End")
    page.wait_for_timeout(600)
    page.keyboard.insert_text("x")
    editor.press("ControlOrMeta+z")
    assert editor.inner_text() == "# comment", repr(editor.inner_text())
    editor.press("Control+Space")
    page.wait_for_timeout(200)
    assert page.locator(".cm-tooltip-autocomplete").count() == 0
    fill_editor(page, "")
    editor.click(button="right", position={"x": 20, "y": 12})
    page.locator(".cm-tooltip-autocomplete").wait_for()
    option("linked_pendulum_3d").click()
    editor.press("ControlOrMeta+Enter")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for()
    snapshot = page.evaluate(
        "async()=>{const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;return(await import(url)).request({op:'snapshot'})}"
    )
    assert snapshot["dimension"] == 3
    assert snapshot["mobility"]["first_order"] == 3
    assert {o["id"] for o in snapshot["objects"]} == {"a", "b", "c"}
    Path("/tmp/cad-review").mkdir(exist_ok=True)
    fill_editor(page, "arm = rod(origin, up)\narm.")
    complete()
    page.screenshot(path="/tmp/cad-review/codemirror-completion.png")
    editor.press("Escape")
    # File switches create a new editor history; undo cannot copy the last file into this one.
    page.get_by_role("button", name="Recent files", exact=True).click()
    page.get_by_role("option").filter(has_text="collinear-2-rod.py").click()
    page.get_by_role("textbox", name="Scene DSL editor").wait_for()
    text = editor.inner_text()
    editor.press("ControlOrMeta+z")
    assert editor.inner_text() == text
    assert "Dead-Center" in text
    assert not errors, errors
    print(
        "CodeMirror editing, contextual completion, right-click snippets, Tab fields, run shortcut, undo and file isolation passed"
    )
    browser.close()
