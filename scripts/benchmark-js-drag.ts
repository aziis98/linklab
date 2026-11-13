/** Run from the repository root with Bun; reports warmed drag + ghost kernel time. */
import {Engine,type Model} from '../src/solver/engine';
const generated=Bun.spawnSync(['kinematics/.venv/bin/python','scripts/js-drag-fixtures.py']);
if(generated.exitCode)throw Error(generated.stderr.toString());
const fixtures=JSON.parse(generated.stdout.toString()) as {name:string;model:Model;key:string;targets:number[][];python_ms:number}[];
const results=fixtures.map(f=>{
 const engine=new Engine(f.model),index=f.model.keys.indexOf(f.key),samples:number[]=[];
 for(let i=0;i<13;i++){engine.x=new Float64Array(f.model.current);const start=performance.now();engine.drag([index],f.targets);engine.preview([index],f.targets);if(i>=3)samples.push(performance.now()-start);}
 samples.sort((a,b)=>a-b);
 return {scene:f.name,js_median_ms:samples[5],js_p95_ms:samples[9],native_python_single_ms:f.python_ms};
});
console.log(JSON.stringify(results,null,2));
