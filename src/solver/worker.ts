import { Engine, type Model } from './engine';
let engine: Engine | null = null;
let recycled = new Float64Array(0);
self.onmessage = ({ data }) => {
    try {
        if (data.recycle) recycled = new Float64Array(data.recycle);
        if (data.op === 'init') {
            engine = new Engine(data.model as Model);
            self.postMessage({ id:data.id, result:true }); return;
        }
        if (!engine) throw Error('Drag engine is not initialized');
        if (data.revision !== undefined && data.revision !== engine.model.revision) throw Error('Stale drag request');
        const ids = data.keys.map((key:string) => {
            const index = engine!.model.keys.indexOf(key);
            if (index < 0) throw Error(`Unknown point ${key}`);
            return index;
        });
        if (!Array.isArray(data.targets) || data.targets.length !== ids.length || data.targets.some((target:number[]) => target.length < engine!.d || target.slice(0,engine!.d).some(v=>!Number.isFinite(v))) || (data.weights && (data.weights.length !== ids.length || data.weights.some((v:number)=>!Number.isFinite(v))))) throw Error('Invalid drag target or weights');
        const before = engine.x;
        try {
            let response: object;
            const poses = recycled.length === engine.n ? recycled : new Float64Array(engine.n);
            if (data.op === 'preview') {
                if (!(data.pose instanceof Float64Array) || data.pose.length !== engine.n || !data.pose.every(Number.isFinite)) throw Error('Invalid preview pose');
                engine.x = data.pose;
                const preview = engine.preview(ids,data.targets,data.weights);
                engine.model.keys.forEach((key,i) => { for(let axis=0;axis<engine!.d;axis++) poses[i*engine!.d+axis]=preview.configuration[key][axis]; });
                response = { ...preview, configuration:undefined, poses };
            } else {
                const result = engine.drag(ids,data.targets,data.weights);
                poses.set(engine.x);
                response = { ...result, configuration:undefined, mobility:{ ...result.mobility, basis:undefined }, poses };
            }
            self.postMessage({ id:data.id, result:response }, { transfer:[poses.buffer] });
            recycled = new Float64Array(0);
        } catch(error) { engine.x = before; throw error; }
    } catch(error) { self.postMessage({ id:data.id, error:String(error) }); }
};
