import json
from pathlib import Path

from playwright.sync_api import sync_playwright

source = Path("kinematics/src/kinematics/examples/spatial_rotor.py").read_text()
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
    )
    page = b.new_page()
    page.goto("http://localhost:5183")
    page.locator(".viewer strong").filter(has_text="numerical").wait_for(timeout=90000)
    result = page.evaluate(
        """async(source)=>{
 const resource=performance.getEntriesByType('resource').find(e=>new URL(e.name).pathname==='/src/pyodide.ts').name;
 const {request}=await import(resource),{setDragBackend}=await import('/src/solver/client.ts');
 const stats=a=>{a.sort((a,b)=>a-b);return {median:a[Math.floor(a.length*.5)],p95:a[Math.floor(a.length*.95)]}};
 const all={};let model;
 for(const weighted of [false,true])for(const backend of ['javascript','python']){
  setDragBackend(backend);const run=await request({op:'run',source});model=await request({op:'numerical_model'});
  const object=run.objects.find(o=>o.kind==='rod'&&!o.fixed),keys=weighted?object.points.map(p=>object.id+':'+p):[object.id+':b'];
  const initial=keys.map(k=>run.configuration[k]),samples=[];
  for(let i=0;i<25;i++){const delta=[Math.sin(i*.17)*.06*model.scale,Math.sin(i*.1)*.03*model.scale,0];const targets=initial.map(p=>p.map((v,a)=>v+delta[a]));const t=performance.now();await request({op:'drag',revision:run.revision,keys,targets,weights:weighted?[.5,.5]:[1],preview_tag:{revision:run.revision,generation:1,interaction:1}});if(i>=5)samples.push(performance.now()-t);}
  all[(weighted?'rod':'joint')+'_'+backend]=stats(samples);
 }
 // Isolate numerical stages in a separate JS worker, without UI/render work.
 const workerCode=`import {Engine} from '${location.origin}/src/solver/engine.ts';self.onmessage=({data:model})=>{const e=new Engine(model),o=model.objects.find(o=>!o.fixed),ids=o.indices.slice(0,2),initial=ids.map(i=>model.current.slice(i*e.d,(i+1)*e.d)),metrics={mobility:[],projection:[],drag:[],ghost:[]};let mobility=0,projection=0;const oldM=e.mobility.bind(e),oldP=e.project.bind(e);e.mobility=()=>{const t=performance.now();const r=oldM();mobility+=performance.now()-t;return r};e.project=(x)=>{const t=performance.now();const r=oldP(x);projection+=performance.now()-t;return r};for(let i=0;i<25;i++){mobility=0;projection=0;const delta=[Math.sin(i*.17)*.06*model.scale,Math.sin(i*.1)*.03*model.scale,0],targets=initial.map(p=>p.map((v,a)=>v+delta[a]));let t=performance.now();e.drag(ids,targets,[.5,.5]);const dt=performance.now()-t,mt=mobility,pt=projection;t=performance.now();e.preview(ids,targets,[.5,.5]);const gt=performance.now()-t;if(i>=5){metrics.drag.push(dt);metrics.ghost.push(gt);metrics.mobility.push(mt);metrics.projection.push(pt)}}self.postMessage(metrics)}`;
 const url=URL.createObjectURL(new Blob([workerCode],{type:'text/javascript'})),w=new Worker(url,{type:'module'});
 const breakdown=await new Promise((resolve,reject)=>{w.onmessage=e=>resolve(e.data);w.onerror=e=>reject(Error(e.message));w.postMessage(model)});w.terminate();URL.revokeObjectURL(url);
 all.js_numerical_breakdown=Object.fromEntries(Object.entries(breakdown).map(([k,v])=>[k,stats(v)]));all.points=model.keys.length;all.coordinates=model.current.length;all.constraints=model.rows.length;
 return all;
 }""",
        source,
    )
    Path("/tmp/rotor-profile.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    b.close()
