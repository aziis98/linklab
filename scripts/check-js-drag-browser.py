"""Exercise JS drag worker, stale requests, engine switching and Python handoffs."""

import json

from browser_editor import fill_editor
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
        args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    )
    page = b.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost:5183")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    fill_editor(page, 'scene_dimension(3)\nr=rod(origin,up,id="r")\npin(r.start)')
    page.get_by_role("button", name="Run", exact=True).click()
    page.locator(".viewer strong").filter(has_text="numerical").wait_for()
    page.wait_for_timeout(300)
    point = page.locator('[data-point="r:b"]').bounding_box()
    x, y = point["x"] + point["width"] / 2, point["y"] + point["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 20, y + 10, steps=5)
    page.screenshot(path="/tmp/js-drag-pointer.png")
    page.locator("[data-grab-target]").wait_for(timeout=30000)
    page.mouse.up()
    page.wait_for_timeout(500)
    point = page.locator('[data-point="r:b"]').bounding_box()
    x, y = point["x"] + point["width"] / 2, point["y"] + point["height"] / 2
    page.get_by_role("button", name="3D renderer", exact=True).click()
    page.get_by_role("option", name="Three.js", exact=True).click()
    page.locator("canvas[data-ready=true]").wait_for(timeout=60000)
    page.wait_for_timeout(150)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 15, y + 10, steps=5)
    page.locator("[data-grab-target]").wait_for(timeout=30000)
    page.mouse.up()
    page.get_by_role("button", name="Wander settings", exact=True).click()
    page.get_by_text("Advanced motion settings", exact=True).click()
    page.get_by_role("button", name="Drag engine", exact=True).click()
    page.get_by_role("option", name="Python", exact=True).click()
    page.keyboard.press("Escape")
    result = page.evaluate("""async()=>{
      const url=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;
      const {request}=await import(url),{setDragBackend,subscribePreview}=await import('/src/solver/client.ts');
      const run=await request({op:'run',source:'scene_dimension(3)\\nr=rod(origin,up,id="r")\\npin(r.start)'});
      const times={};
      for(const backend of ['javascript','python','javascript']){
        setDragBackend(backend);const start=performance.now();
        for(let i=0;i<4;i++)await request({op:'drag',revision:run.revision,keys:['r:b'],targets:[[.1+i*.01,1,.1]]});
        times[backend]=(performance.now()-start)/4;
      }
      const order=[];
      let ghostResolve;
      const ghostDone=new Promise(resolve=>ghostResolve=resolve);
      const unsubscribe=subscribePreview(({tag})=>{if(tag.interaction===123){order.push('ghost');ghostResolve();}});
      await request({op:'drag',revision:run.revision,keys:['r:b'],targets:[[.15,1,.1]],preview_tag:{revision:run.revision,generation:1,interaction:123}});
      order.push('accepted');
      await Promise.race([ghostDone,new Promise((_,reject)=>setTimeout(()=>reject(Error('Preview timed out')),10000))]);
      unsubscribe();if(order[0]!=='accepted')throw Error('Preview delayed accepted pose');
      const snapshot=await request({op:'snapshot'});
      if(snapshot.mobility.residual>1e-9)throw Error('infeasible snapshot');
      const wander=await request({op:'wander_start',revision:run.revision,settings:{seed:0}});
      await request({op:'wander_step',revision:run.revision,job_id:wander.job_id});
      await request({op:'wander_cancel',revision:run.revision,job_id:wander.job_id});
      await request({op:'reset',revision:run.revision});
      let stale=false;try{await request({op:'drag',revision:run.revision-1,keys:['r:b'],targets:[[0,1,0]]})}catch{stale=true}
      if(!stale)throw Error('stale request accepted');
      return {times,pose:snapshot.configuration['r:b']};
    }""")
    print(json.dumps(result))
    assert not errors, errors
    b.close()
