import { dot, norm, solve, nullspace, nullspaces, multiply, eigenvalues, constrainedFit } from './linalg';
export type Config = Record<string, number[]>;
type Row = {
    constant: number;
    linear: [
        number,
        number
    ][];
    quadratic: [
        number,
        number,
        number
    ][];
};
export interface Model {
    version: number;
    revision: number;
    dimension: number;
    keys: string[];
    initial: number[];
    current: number[];
    scale: number;
    rows: Row[];
    cables: [number,number,number][];
    lengths: [
        number,
        number,
        number
    ][];
    affine: [
        number,
        [
            number,
            number[][]
        ][]
    ][];
    objects: {
        id: string;
        fixed: boolean;
        indices: number[];
    }[];
    constraints: {
        id: string;
        kind: string;
        a: number;
        b: number | null;
        value: number | number[] | number[][];
    }[];
    equal:[number,number][];
    pins:[number,number[]][];
    planes:[number,number[],number[]][];
    parallels:[number,number,number,number][];
    isolated: number[][][];
}
interface MobilityState {
 first_order:number;second_order:string;linear_compatible_dimension:number;
 linear_compatible_tangents:number[][][];tangents:number[][][];quadratic_forms:number[][][];
 rank:number;residual:number;basis:{data:Float64Array;cols:number};
}
export class Engine {
    x: Float64Array;
    initial: Float64Array;
    n: number;
    m: number;
    d: number;
    model: Model;
    private coefficients: {constant:number; linear:Float64Array; quadratic:Float64Array}[];
    constructor(model: Model) { this.model = model;model.cables ??= []; this.coefficients = model.rows.map(row=>({constant:row.constant,linear:new Float64Array(row.linear.flat()),quadratic:new Float64Array(row.quadratic.flat())})); if (model.version !== 1 && model.version !== 2)
        throw Error('Unsupported numerical model'); this.x = new Float64Array(model.current); this.initial = new Float64Array(model.initial); this.n = this.x.length; this.m = model.rows.length; this.d = model.dimension; }
    residual(x: Float64Array, out = new Float64Array(this.m)) {
        for(let r=0;r<this.m;r++){const row=this.coefficients[r];let v=row.constant;
            for(let p=0;p<row.linear.length;p+=2)v+=row.linear[p+1]*x[row.linear[p]];
            for(let p=0;p<row.quadratic.length;p+=3)v+=row.quadratic[p+2]*x[row.quadratic[p]]*x[row.quadratic[p+1]];
            out[r]=v;
        }
        // Preserve subtraction before scaling; expanded polynomials lose precision
        // for small mechanisms translated far from the world origin.
        let row=0;const s=this.model.scale,d=this.d;
        for(const[i,j,length]of this.model.lengths){let squared=0;for(let a=0;a<d;a++)squared+=(x[i*d+a]-x[j*d+a])**2;out[row++]=(squared-length)/(2*s*s);}
        for(const[p,terms]of this.model.affine)for(let a=0;a<d;a++){let value=x[p*d+a];for(const[i,w]of terms)for(let b=0;b<d;b++)value-=w[a][b]*x[i*d+b];out[row++]=value/s;}
        for(const[i,j]of this.model.equal)for(let a=0;a<d;a++)out[row++]=(x[i*d+a]-x[j*d+a])/s;
        for(const[i,p]of this.model.pins)for(let a=0;a<d;a++)out[row++]=(x[i*d+a]-p[a])/s;
        for(const[i,p,n]of this.model.planes){let value=0;for(let a=0;a<d;a++)value+=(x[i*d+a]-p[a])*n[a];out[row++]=value/(s*norm(n));}
        for(const[i,j,k,l]of this.model.parallels)for(const[a,b]of(d===3?[[1,2],[2,0],[0,1]]:[[0,1]]))out[row++]=((x[j*d+a]-x[i*d+a])*(x[l*d+b]-x[k*d+b])-(x[j*d+b]-x[i*d+b])*(x[l*d+a]-x[k*d+a]))/(s*s);
        return out;
    }
    jac(x: Float64Array, out = new Float64Array(this.m*this.n)) {
        out.fill(0);
        for(let r=0;r<this.m;r++){const row=this.coefficients[r],offset=r*this.n;
            for(let p=0;p<row.linear.length;p+=2)out[offset+row.linear[p]]+=row.linear[p+1];
            for(let p=0;p<row.quadratic.length;p+=3){const i=row.quadratic[p],j=row.quadratic[p+1],w=row.quadratic[p+2];out[offset+i]+=w*x[j];out[offset+j]+=w*x[i];}
        }
        const s=this.model.scale,d=this.d;
        this.model.lengths.forEach(([i,j],row)=>{out.fill(0,row*this.n,(row+1)*this.n);for(let a=0;a<d;a++){const value=(x[i*d+a]-x[j*d+a])/(s*s);out[row*this.n+i*d+a]=value;out[row*this.n+j*d+a]=-value;}});
        let row=this.m-this.model.parallels.length*(d===3?3:1);
        for(const[i,j,k,l]of this.model.parallels)for(const[a,b]of(d===3?[[1,2],[2,0],[0,1]]:[[0,1]])){
            const offset=row++*this.n;out.fill(0,offset,offset+this.n);
            const terms:[[number,number,number],... [number,number,number][]]=[[j,a,(x[l*d+b]-x[k*d+b])],[j,b,-(x[l*d+a]-x[k*d+a])],[i,a,-(x[l*d+b]-x[k*d+b])],[i,b,(x[l*d+a]-x[k*d+a])],[l,b,(x[j*d+a]-x[i*d+a])],[l,a,-(x[j*d+b]-x[i*d+b])],[k,b,-(x[j*d+a]-x[i*d+a])],[k,a,(x[j*d+b]-x[i*d+b])]];
            for(const[p,axis,value]of terms)out[offset+p*d+axis]+=value/(s*s);
        }
        return out;
    }
    distance(x: Float64Array, i: number, j: number) { let v = 0; for (let k = 0; k < this.d; k++)
        v += (x[i * this.d + k] - x[j * this.d + k]) ** 2; return Math.sqrt(v); }
    error(x: Float64Array) { let e = 0; for (const v of this.residual(x))
        e = Math.max(e, Math.abs(v)); for (const [i, j, l] of this.model.lengths)
        e = Math.max(e, Math.abs(this.distance(x, i, j) - Math.sqrt(l)) / this.model.scale); for(const[i,j,l]of this.model.cables)e=Math.max(e,Math.max(0,this.distance(x,i,j)-Math.sqrt(l))/this.model.scale); return e; }
    fit(initial: Float64Array, residual: (x: Float64Array) => Float64Array, jac: (x: Float64Array) => Float64Array, budget = 300) { let x = initial.slice(), lambda = 1e-8; for (let it = 0; it < budget; it++) {
        const r = residual(x), a = jac(x), cost = dot(r, r);
        if (cost < 1e-27)
            break;
        const step = solve(a, r.length, x.length, Float64Array.from(r, v => -v), 1e-13, lambda);
        if (norm(step) < 1e-13 * Math.max(1, norm(x)))
            break;
        const candidate = Float64Array.from(x, (v, i) => v + step[i]), next = residual(candidate);
        if (dot(next, next) < cost) {
            x = candidate;
            lambda = Math.max(1e-16, lambda * .25);
        }
        else
            lambda = Math.min(1e16, lambda * 10);
    } return x; }
    cableRows(x:Float64Array){const values=new Float64Array(this.model.cables.length),rows=new Float64Array(this.model.cables.length*this.n);this.model.cables.forEach(([i,j,l],r)=>{let squared=0;for(let a=0;a<this.d;a++){const delta=x[i*this.d+a]-x[j*this.d+a];squared+=delta*delta;rows[r*this.n+i*this.d+a]=delta/this.model.scale**2;rows[r*this.n+j*this.d+a]=-delta/this.model.scale**2;}values[r]=(squared-l)/(2*this.model.scale**2);});return {values,rows};}
    project(guess: Float64Array) {
        if(this.model.cables.length){let x=guess.slice();for(let iteration=0;iteration<100;iteration++){if(this.error(x)<=1e-10)return x;const r=this.residual(x),j=this.jac(x),p=solve(j,this.m,this.n,Float64Array.from(r,v=>-v),1e-10),z=nullspace(j,this.m,this.n,1e-10),g=this.cableRows(x),ap=multiply(g.rows,g.values.length,this.n,p,1),az=multiply(g.rows,g.values.length,this.n,z.data,z.cols),q=constrainedFit(z.data,this.n,z.cols,Float64Array.from(p,v=>-v),az,g.values.length,Float64Array.from(g.values,(v,i)=>-v-ap[i]),this.workingSets.project),step=multiply(z.data,this.n,z.cols,q,1);x=Float64Array.from(x,(v,i)=>v+p[i]+step[i]);}if(this.error(x)>1e-9)throw Error('Cable assembly did not converge');return x;}
 const residualBuffer=new Float64Array(this.m),jacobianBuffer=new Float64Array(this.m*this.n);const x = this.fit(guess, x => this.residual(x,residualBuffer), x => this.jac(x,jacobianBuffer)); if (!Number.isFinite(this.error(x)) || this.error(x) > 1e-9)
        throw Error('Projection did not converge'); return x; }
    private workingSets={drag:[] as number[],project:[] as number[]};
    private analysisCache: {pose: Float64Array; value: ReturnType<Engine['computeMobility']>} | null = null;
    private previewBasisCache: {key: string; basis: ReturnType<typeof nullspace>} | null = null;
    mobility() {
        if (this.analysisCache?.pose === this.x) return this.analysisCache.value;
        const value = this.computeMobility(); this.analysisCache = {pose:this.x,value}; return value;
    }
    private computeMobility() {
        const a = this.jac(this.x), spaces = nullspaces(a,this.m,this.n), t = spaces.right, u = spaces.left, k = t.cols, forms: Float64Array[] = [], restrictions: Float64Array[] = [];
        for (let h = 0; h < u.cols; h++) {
            const H = new Float64Array(k * k);
            for (let row = 0; row < this.m; row++) {
                const stress = u.data[row * u.cols + h];
                for (const [i, j, w] of this.model.rows[row].quadratic)
                    for (let p = 0; p < k; p++)
                        for (let q = 0; q < k; q++)
                            H[p * k + q] += stress * w * (t.data[i * k + p] * t.data[j * k + q] + t.data[j * k + p] * t.data[i * k + q]);
            }
            forms.push(H);
            if (k) {
                const ev = eigenvalues(H, k), min = Math.min(...ev), max = Math.max(...ev);
                if ((min >= -1e-8 && max > 1e-8) || (max <= 1e-8 && min < -1e-8))
                    restrictions.push(H);
            }
        }
        let compatible = t;
        if (restrictions.length) {
            const stacked = new Float64Array(restrictions.length * k * k);
            restrictions.forEach((v, i) => stacked.set(v, i * k * k));
            const z = nullspace(stacked, restrictions.length * k, k);
            compatible = { cols: z.cols, data: multiply(t.data, this.n, k, z.data, z.cols) };
        }
        const vectors = (data: Float64Array, cols: number) => Array.from({ length: cols }, (_, j) => Array.from({ length: this.n / this.d }, (_, i) => Array.from({ length: this.d }, (_, axis) => data[(i * this.d + axis) * cols + j])));
        const result = { first_order: k, second_order: k && compatible.cols === 0 ? 'locked' : forms.some(h => norm(h) > 1e-8) && k ? 'inconclusive' : 'compatible', linear_compatible_dimension: compatible.cols, linear_compatible_tangents: vectors(compatible.data, compatible.cols), tangents: vectors(t.data, k), quadratic_forms: forms.map(h => Array.from({ length: k }, (_, i) => Array.from(h.slice(i * k, (i + 1) * k)))), rank: this.n - k, residual: this.error(this.x), basis: compatible };
        if(this.model.cables.length) return this.cableMobility(result,a,t);
        return result;
    }
    private cableMobility(result:MobilityState,j:Float64Array,rawTangent:{data:Float64Array;cols:number}){
        const g=this.cableRows(this.x),ids=Array.from(g.values.keys()).filter(index=>{const[i,j,l]=this.model.cables[index];return(Math.sqrt(l)-this.distance(this.x,i,j))/this.model.scale<=1e-8;}),m=this.m,k=ids.length,t=result.basis;
        if(!k||!t.cols)return {...result,motion_kind:'cone',active_cables:ids};
        const aa=Float64Array.from(ids.flatMap(i=>Array.from(g.rows.slice(i*this.n,(i+1)*this.n)))),reduced=multiply(aa,k,this.n,rawTangent.data,rawTangent.cols),matrix=new Float64Array((rawTangent.cols+1)*k);
        for(let i=0;i<rawTangent.cols;i++)for(let r=0;r<k;r++)matrix[i*k+r]=reduced[r*rawTangent.cols+i];matrix.fill(1,rawTangent.cols*k);
        const rhs=new Float64Array(rawTangent.cols+1);rhs[rawTangent.cols]=1;const p=solve(matrix,rawTangent.cols+1,k,rhs,1e-10);
        if(norm(Float64Array.from(multiply(matrix,rhs.length,k,p,1),(v,i)=>v-rhs[i]))>1e-8)return {...result,motion_kind:'cone',active_cables:ids};
        try{const z=nullspace(matrix,rhs.length,k,1e-10),q=constrainedFit(z.data,k,z.cols,Float64Array.from(p,v=>-v),Float64Array.from(z.data,v=>-v),k,p),mu=Float64Array.from(p,(v,i)=>v+dot(z.data.subarray(i*z.cols,(i+1)*z.cols),q));
        if(Math.min(...mu)<-1e-8||norm(Float64Array.from(multiply(matrix,rhs.length,k,mu,1),(v,i)=>v-rhs[i]))>1e-8)return result;
        const force=new Float64Array(this.n);for(let i=0;i<this.n;i++)for(let r=0;r<k;r++)force[i]-=aa[r*this.n+i]*mu[r];
        const jt=new Float64Array(this.n*m);for(let i=0;i<this.n;i++)for(let r=0;r<m;r++)jt[i*m+r]=j[r*this.n+i];
        const lam=solve(jt,this.n,m,force,1e-10);if(norm(Float64Array.from(multiply(jt,this.n,m,lam,1),(v,i)=>v-force[i]))>1e-8)return result;
        const forced=ids.map((_,i)=>i).filter(i=>mu[i]>1e-8),f=Float64Array.from(forced.flatMap(i=>Array.from(aa.slice(i*this.n,(i+1)*this.n)))),ker=nullspace(multiply(f,forced.length,this.n,t.data,t.cols),forced.length,t.cols,1e-8);let basis=multiply(t.data,this.n,t.cols,ker.data,ker.cols),cols=ker.cols;
        const h=new Float64Array(cols*cols);
        for(let row=0;row<m;row++)for(const[i,j,w]of this.model.rows[row].quadratic)for(let p=0;p<cols;p++)for(let q=0;q<cols;q++)h[p*cols+q]+=lam[row]*w*(basis[i*cols+p]*basis[j*cols+q]+basis[j*cols+p]*basis[i*cols+q]);
        ids.forEach((index,r)=>{const[i,j]=this.model.cables[index];for(let axis=0;axis<this.d;axis++)for(let p=0;p<cols;p++)for(let q=0;q<cols;q++)h[p*cols+q]+=mu[r]*(basis[(i*this.d+axis)*cols+p]-basis[(j*this.d+axis)*cols+p])*(basis[(i*this.d+axis)*cols+q]-basis[(j*this.d+axis)*cols+q])/this.model.scale**2;});
        if(cols){const ev=eigenvalues(h,cols);if(Math.min(...ev)>=-1e-8&&Math.max(...ev)>1e-8){const z=nullspace(h,cols,cols);basis=multiply(basis,this.n,cols,z.data,z.cols);cols=z.cols;}}
        return {...result,basis:{data:basis,cols},linear_compatible_dimension:cols,linear_compatible_tangents:Array.from({length:cols},(_,q)=>Array.from({length:this.n/this.d},(_,i)=>Array.from({length:this.d},(_,a)=>basis[(i*this.d+a)*cols+q]))),second_order:cols?result.second_order:'locked',motion_kind:cols?'cone':'locked',active_cables:ids};
        }catch{return {...result,motion_kind:'cone',active_cables:ids};}
    }

    configuration(x = this.x): Config { return Object.fromEntries(this.model.keys.map((key, i) => [key, [...x.slice(i * this.d, (i + 1) * this.d), ...(this.d === 2 ? [0] : [])]])); }
    drag(ids: number[], targets: number[][], weights?: number[]) {
        const objective = (x: Float64Array) => { if (weights) {
            const out = new Float64Array(this.d);
            ids.forEach((id, j) => { for (let a = 0; a < this.d; a++)
                out[a] += weights[j] * (targets[j][a] - x[id * this.d + a]); });
            return out;
        } return Float64Array.from(ids.flatMap((id, j) => Array.from({ length: this.d }, (_, a) => targets[j][a] - x[id * this.d + a]))); };
        const isolated = this.model.isolated.some(p => p.every((v, i) => Math.hypot(...v.map((c, a) => c - this.x[i * this.d + a])) < 1e-7 * this.model.scale));
        if (!isolated)
            for (let it = 0; it < 16; it++) {
                const mobility = this.mobility(), t = mobility.basis;
                if (mobility.second_order === 'locked' || !t.cols)
                    break;
                const r = objective(this.x), a = new Float64Array(r.length * t.cols);
                ids.forEach((id, j) => { for (let axis = 0; axis < this.d; axis++)
                    for (let c = 0; c < t.cols; c++)
                        a[(weights ? axis : j * this.d + axis) * t.cols + c] += (weights ? weights[j] : 1) * t.data[(id * this.d + axis) * t.cols + c]; });
                if (norm(a) < 1e-12)
                    break;
                const cable=this.cableRows(this.x);const delta = this.model.cables.length?constrainedFit(a,r.length,t.cols,r,multiply(cable.rows,cable.values.length,this.n,t.data,t.cols),cable.values.length,Float64Array.from(cable.values,v=>Math.max(-v,0)),this.workingSets.drag):solve(a, r.length, t.cols, r), step = multiply(t.data, this.n, t.cols, delta, 1), length = norm(step);
                if (length < 1e-9 * this.model.scale)
                    break;
                const cap = Math.min(1, .03 * this.model.scale / length);
                for (let i = 0; i < this.n; i++)
                    step[i] *= cap;
                let accepted = false;
                for (const f of [1, .5, .25, .125]) {
                    try {
                        const candidate = this.project(Float64Array.from(this.x, (v, i) => v + f * step[i]));
                        if (norm(Float64Array.from(candidate, (v, i) => v - this.x[i])) > 2 * norm(step) || norm(objective(candidate)) >= norm(r))
                            continue;
                        this.x = candidate;
                        accepted = true;
                        break;
                    }
                    catch { /* keep last feasible pose */ }
                }
                if (!accepted)
                    break;
            }
        const mobility = this.mobility();
        return { configuration: this.configuration(), mobility, reachable: !isolated && norm(objective(this.x)) < 1e-5 * this.model.scale };
    }
    preview(ids: number[], targets: number[][], weights = ids.map(() => 1 / ids.length)) {
        const fixed = new Set(this.model.objects.filter(o => o.fixed).flatMap(o => o.indices)), free = Array.from({ length: this.n }, (_, i) => i).filter(i => !fixed.has(Math.floor(i / this.d))), rows: number[][] = [], rhs: number[] = [];
        const grab = new Float64Array(this.d * this.n), target = new Float64Array(this.d);
        for (let a = 0; a < this.d; a++) {
            ids.forEach((id, j) => { grab[a * this.n + id * this.d + a] += weights[j]; target[a] += weights[j] * targets[j][a]; });
            rows.push(Array.from(grab.slice(a * this.n, (a + 1) * this.n)));
            rhs.push(target[a]);
        }
        for (const [p, terms] of this.model.affine)
            for (let a = 0; a < this.d; a++) {
                const row = Array(this.n).fill(0);
                row[p * this.d + a] = 1;
                for (const [i, w] of terms)
                    for (let b = 0; b < this.d; b++)
                        row[i * this.d + b] -= w[a][b];
                rows.push(row);
                rhs.push(0);
            }
        const A = Float64Array.from(rows.flatMap(row => free.map(i => row[i]))), b = Float64Array.from(rows, (row, k) => rhs[k] - dot(row, this.x)), correction = solve(A, rows.length, free.length, b, 1e-12), base = this.x.slice();
        free.forEach((i, j) => base[i] += correction[j]);
        const cacheKey = JSON.stringify([ids,weights]);
        if (this.previewBasisCache?.key !== cacheKey) this.previewBasisCache = {key:cacheKey,basis:nullspace(A,rows.length,free.length,1e-12)};
        const z = this.previewBasisCache!.basis, reg = 1e-4 / this.model.scale;
        const embed = (q: Float64Array) => { const x = base.slice(), delta = multiply(z.data, free.length, z.cols, q, 1); free.forEach((i, j) => x[i] += delta[j]); return x; };
        const fit = this.fit(new Float64Array(z.cols), q => { const x = embed(q); return new Float64Array([...this.residual(x), ...Array.from(this.cableRows(x).values,v=>Math.max(v,0)), ...free.map(i => reg * (x[i] - this.x[i]))]); }, q => { const j = this.jac(embed(q)), reduced = Float64Array.from(Array.from({ length: this.m }, (_, r) => free.map(i => j[r * this.n + i])).flat()), a = multiply(reduced, this.m, free.length, z.data, z.cols); const cable=this.cableRows(embed(q)),reducedCable=Float64Array.from(Array.from({length:cable.values.length},(_,r)=>free.map(i=>cable.values[r]>0?cable.rows[r*this.n+i]:0)).flat()),cj=multiply(reducedCable,cable.values.length,free.length,z.data,z.cols);return new Float64Array([...a,...cj, ...Array.from(z.data, v => reg * v)]); }, 100), x = embed(fit);
        const point = (i: number) => [...x.slice(i * this.d, (i + 1) * this.d), ...(this.d === 2 ? [0] : [])], severity = (v: number) => v / (.03 + v), points: Record<string, number> = Object.fromEntries(this.model.keys.map(k => [k, 0])), objects: Record<string, number> = {}, edges: Record<string, number> = {};
        for (const o of this.model.objects) {
            let worst = 0;
            for (let p = 0; p < o.indices.length; p++)
                for (let q = p + 1; q < o.indices.length; q++) {
                    const i = o.indices[p], j = o.indices[q], l = this.distance(this.initial, i, j), v = severity(Math.abs(this.distance(x, i, j) - l) / Math.max(l, .05 * this.model.scale));
                    edges[`${this.model.keys[i]}|${this.model.keys[j]}`] = v;
                    worst = Math.max(worst, v);
                    points[this.model.keys[i]] = Math.max(points[this.model.keys[i]], v);
                    points[this.model.keys[j]] = Math.max(points[this.model.keys[j]], v);
                }
            objects[o.id] = worst;
        }
        const joints = this.model.constraints.map(c => {
            const a = point(c.a);
            let b: number[] | null = c.b === null ? null : point(c.b), error = 0;
            const values = c.value as number[];
            if (c.kind === 'pin') {
                b = values;
                error = Math.hypot(...a.map((v, i) => v - b![i])) / this.model.scale;
            }
            else if (c.kind === 'coincident')
                error = this.distance(x, c.a, c.b!) / this.model.scale;
            else if ((c.kind === 'distance' || c.kind === 'cable')) {
                const l = Math.sqrt(c.value as unknown as number);
                error = (c.kind==='cable'?Math.max(0,this.distance(x,c.a,c.b!)-l):Math.abs(this.distance(x,c.a,c.b!)-l)) / Math.max(l, .05 * this.model.scale);
            }
            else if (c.kind === 'plane') {
                const [p, n] = c.value as number[][], nn = norm(n), off = dot(a.map((v, i) => v - p[i]), n) / nn;
                b = a.map((v, i) => v - off * n[i] / nn);
                error = Math.abs(off) / this.model.scale;
            }
            else if (c.kind === 'parallel') {
                const [k, l] = values, u = a.map((v, i) => point(c.b!)[i] - v), v = point(k).map((v, i) => point(l)[i] - v), cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
                error = norm(cross) / Math.max(norm(u) * norm(v), 1e-20);
            }
            const value = severity(error);
            points[this.model.keys[c.a]] = Math.max(points[this.model.keys[c.a]], value);
            if (c.b !== null)
                points[this.model.keys[c.b]] = Math.max(points[this.model.keys[c.b]], value);
            return { id: c.id, kind: c.kind, a, b, error, severity: value };
        });
        const at = Array.from(multiply(grab, this.d, this.n, x, 1));
        return { configuration: this.configuration(x), grab: [...at, ...(this.d === 2 ? [0] : [])], target_error: norm(Float64Array.from(target, (v, i) => v - at[i])), objects, edges, points, joints };
    }
}
