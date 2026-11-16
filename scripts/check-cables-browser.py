import json
from pathlib import Path

from browser_editor import fill_editor
from playwright.sync_api import sync_playwright

source = Path("kinematics/src/kinematics/examples/hopf_link.py").read_text()
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    )
    page = b.new_page(viewport={"width": 1400, "height": 900})
    page.add_init_script(
        "localStorage.setItem('cad-detect-free-motions.files.v2',JSON.stringify(["
        + json.dumps({"id": "cables", "name": "hopf.py", "body": source, "editedAt": 0})
        + "]));localStorage.setItem('cad-detect-free-motions.active.v1','cables')"
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://localhost:5183")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    assert page.locator("[data-cable]").count() == 4
    assert "locked" in page.locator(".viewer").inner_text()
    page.screenshot(path="/tmp/cable-svg.png")
    page.get_by_role("button", name="3D renderer", exact=True).click()
    page.get_by_role("option", name="Three.js", exact=True).click()
    page.locator("canvas[data-ready=true]").wait_for(timeout=60000)
    page.wait_for_timeout(200)
    page.screenshot(path="/tmp/cable-three.png")
    fill_editor(
        page,
        'scene_dimension(3)\na=body({},fixed=True)\nb=body({},center=right*.5)\ncable(a.origin,b.origin,length=1,id="tether")',
    )
    page.get_by_role("button", name="Run", exact=True).click()
    page.locator(".viewer strong").filter(has_text="numerical").wait_for()
    result = page.evaluate("""async()=>{
 const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;
 const{request}=await import(url),{setDragBackend}=await import('/src/solver/client.ts');
 const metrics={};for(const backend of ['javascript','python']){
 setDragBackend(backend);const s=await request({op:'reset'});let result;
 for(let i=0;i<8;i++)result=await request({op:'drag',revision:s.revision,keys:['body2:origin'],targets:[[2,0,0]]});
 metrics[backend]=result.mobility.residual;if(Math.hypot(...result.configuration['body2:origin'])>1.00000001)throw Error('Cable overstretched');
 }
 const s=await request({op:'snapshot'});const w=await request({op:'wander_start',revision:s.revision});const frames=await request({op:'wander_step',revision:s.revision,job_id:w.job_id});await request({op:'wander_cancel',revision:s.revision,job_id:w.job_id});
 return {metrics,frames:frames.frames.length};}""")
    assert not errors, errors
    print(result)
    b.close()
