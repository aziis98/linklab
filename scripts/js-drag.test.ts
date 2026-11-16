import { expect, test } from 'bun:test';
import { Engine, type Model } from '../src/solver/engine';
import { constrainedFit, multiply, nullspace, nullspaces, solve, transpose } from '../src/solver/linalg';
const generated = Bun.spawnSync(['kinematics/.venv/bin/python', 'scripts/js-drag-fixtures.py']);
if (generated.exitCode)
    throw Error(generated.stderr.toString());
const fixtures = JSON.parse(generated.stdout.toString()) as {
    name: string;
    jacobian:number[][];
    model: Model;
    key: string;
    targets: number[][];
    result: {
        configuration: Record<string, number[]>;
        mobility: {
            first_order: number;
            second_order: string;
            residual: number;
        };
    };
    preview: {
        grab: number[];
        objects: Record<string, number>;
    };
}[];
for (const f of fixtures)
    test(`Python drag/ghost parity: ${f.name}`, () => {
        const e = new Engine(f.model), ids = [f.model.keys.indexOf(f.key)], r = e.drag(ids, f.targets), before = e.x.slice(), ghost = e.preview(ids, f.targets);
        const accepted = e.x.slice();
        e.x = new Float64Array(f.model.keys.flatMap(key => f.result.configuration[key].slice(0, e.d)));
        const referenceMobility = e.mobility();
        expect(referenceMobility.first_order).toBe(f.result.mobility.first_order);
        expect(referenceMobility.second_order).toBe(f.result.mobility.second_order);
        e.x = accepted;
        expect(r.mobility.residual).toBeLessThanOrEqual(1e-9);
    const initialJac=e.jac(new Float64Array(f.model.initial));f.jacobian.flat().forEach((v,i)=>expect(Math.abs(v-initialJac[i])).toBeLessThan(1e-12));
        let difference = 0;
        for (const key of f.model.keys)
            for (let a = 0; a < e.d; a++)
                difference = Math.max(difference, Math.abs(r.configuration[key][a] - f.result.configuration[key][a]) / e.model.scale);
        // Different projectors may choose different unobserved motions in multi-DOF systems.
        if (f.result.mobility.first_order <= 1)
            expect(difference).toBeLessThan(2e-5);
        const targetError = (configuration: Record<string, number[]>) => Math.hypot(...f.targets[0].slice(0, e.d).map((v, i) => v - configuration[f.key][i]));
        expect(targetError(r.configuration)).toBeLessThanOrEqual(targetError(f.result.configuration) + 1e-5 * e.model.scale);
        expect(e.x).toEqual(before);
        ghost.grab.forEach((v, i) => expect(Math.abs(v - f.preview.grab[i]) / e.model.scale).toBeLessThan(1e-7));
        expect(Object.keys(ghost.objects)).toEqual(Object.keys(f.preview.objects));
        const j = e.jac(e.x), delta = Float64Array.from(e.x, (_, i) => Math.sin(i + 1)), h = 1e-6, plus = e.residual(Float64Array.from(e.x, (v, i) => v + h * delta[i])), minus = e.residual(Float64Array.from(e.x, (v, i) => v - h * delta[i]));
        for (let row = 0; row < e.m; row++) {
            let directional = 0;
            for (let i = 0; i < e.n; i++)
                directional += j[row * e.n + i] * delta[i];
            expect(Math.abs(directional - (plus[row] - minus[row]) / (2 * h))).toBeLessThan(1e-7);
        }
    });
test('Rank deficient wide matrices and empty constraints', () => { const a = new Float64Array([1, 2, 3, 2, 4, 6]), z = nullspace(a, 2, 3); expect(z.cols).toBe(2); expect(Math.max(...multiply(a, 2, 3, z.data, z.cols).map(Math.abs))).toBeLessThan(1e-10); const solution = solve(a, 2, 3, [1, 2]); expect(Math.abs(multiply(a, 2, 3, solution, 1)[0] - 1)).toBeLessThan(1e-12); expect(nullspace(new Float64Array(), 0, 3).cols).toBe(3); expect(transpose(a, 2, 3)).toEqual(new Float64Array([1, 2, 2, 4, 3, 6])); });

test('Weighted material grab follows a pinned rod and ghost remains independent',()=>{
 // Use the small rod exported from Python rather than assuming its point ordering.
 const generated=Bun.spawnSync(['kinematics/.venv/bin/python','-c',`import json;from kinematics import Session;from kinematics.core.numerical_model import export_model;s=Session();s.run('r=rod(origin,up*2,id="r")\\npin(r.start)');print(json.dumps(export_model(s)))`]);
 expect(generated.exitCode).toBe(0);
 const e=new Engine(JSON.parse(generated.stdout.toString())),ids=['r:a','r:b'].map(k=>e.model.keys.indexOf(k));
 const result=e.drag(ids,[[.1,0,0],[.1,2,0]],[.75,.25]),at=result.configuration['r:b'];
 expect(Math.abs(at[0]/4-.5*.1/Math.hypot(.1,.5))).toBeLessThan(1e-5);
 expect(result.mobility.residual).toBeLessThanOrEqual(1e-9);
 const accepted=e.x.slice(),ghost=e.preview(ids,[[.1,0,0],[.1,2,0]],[.75,.25]);
 expect(Math.abs(ghost.grab[0]-.1)).toBeLessThan(1e-10);expect(Math.abs(ghost.grab[1]-.5)).toBeLessThan(1e-10);expect(e.x).toEqual(accepted);
});

test('Certified isolated witnesses reject finite drag despite a tangent space',()=>{
 const model=structuredClone(fixtures.find(f=>f.name==='four_bar')!.model);
 model.isolated=[model.keys.map((_,i)=>model.current.slice(i*model.dimension,(i+1)*model.dimension))];
 const e=new Engine(model),before=e.x.slice();e.drag([model.keys.length-1],[[1,1,0]]);expect(e.x).toEqual(before);
});


test('Single-decomposition nullspaces retain left and right orthogonality',()=>{
 const a=new Float64Array([1,2,3,2,4,6]),spaces=nullspaces(a,2,3);
 expect(spaces.right.cols).toBe(2);expect(spaces.left.cols).toBe(1);
 expect(Math.max(...multiply(a,2,3,spaces.right.data,2).map(Math.abs))).toBeLessThan(1e-10);
 expect(Math.max(...multiply(transpose(a,2,3),3,2,spaces.left.data,1).map(Math.abs))).toBeLessThan(1e-10);
 expect(nullspaces(new Float64Array(6),2,3).left.cols).toBe(2);
});

test('Cable working set releases when the objective moves inward',()=>{
 const c=new Float64Array([1,0,0,1]),a=new Float64Array([1,0,0,1]),working:number[]=[];
 expect(Array.from(constrainedFit(c,2,2,[2,.2],a,2,[1,1],working))).toEqual([1,.2]);
 expect(working).toEqual([0]);
 const inward=constrainedFit(c,2,2,[.2,.2],a,2,[1,1],working);
 expect(inward[0]).toBeCloseTo(.2,10);expect(working).toEqual([]);
});
