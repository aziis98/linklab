/** Dense Float64 kernels. SVD works directly on A, never on AᵀA. */
export function dot(a: ArrayLike<number>, b: ArrayLike<number>) { let s = 0; for (let i = 0; i < a.length; i++)
    s += a[i] * b[i]; return s; }
export function norm(a: ArrayLike<number>) { return Math.sqrt(dot(a, a)); }
export function identity(n: number) { const a = new Float64Array(n * n); for (let i = 0; i < n; i++)
    a[i * n + i] = 1; return a; }
// Borrowed scratch storage: only solve/nullspace consume it synchronously.
let scratchB = new Float64Array(0), scratchV = new Float64Array(0), scratchS = new Float64Array(0);
function svd(a: Float64Array, m: number, n: number) {
    if (scratchB.length < m*n) scratchB = new Float64Array(m*n);
    if (scratchV.length < n*n) scratchV = new Float64Array(n*n);
    if (scratchS.length < n) scratchS = new Float64Array(n);
    const b = scratchB.subarray(0,m*n), v = scratchV.subarray(0,n*n), floor = dot(a,a)*1e-28;
    b.set(a); v.fill(0); for(let i=0;i<n;i++)v[i*n+i]=1;
    for (let sweep = 0; sweep < Math.max(40, n * 4); sweep++) {
        let changed = false;
        for (let p = 0; p < n; p++)
            for (let q = p + 1; q < n; q++) {
                let aa = 0, bb = 0, ab = 0;
                for (let i = 0; i < m; i++) {
                    const x = b[i * n + p], y = b[i * n + q];
                    aa += x * x;
                    bb += y * y;
                    ab += x * y;
                }
                if (Math.abs(ab) <= 1e-14 * Math.sqrt(aa * bb) || aa <= floor || bb <= floor)
                    continue;
                const tau = (bb - aa) / (2 * ab), t = (tau >= 0 ? 1 : -1) / (Math.abs(tau) + Math.hypot(1, tau)), c = 1 / Math.hypot(1, t), s = c * t;
                for (let i = 0; i < m; i++) {
                    const x = b[i * n + p], y = b[i * n + q];
                    b[i * n + p] = c * x - s * y;
                    b[i * n + q] = s * x + c * y;
                }
                for (let i = 0; i < n; i++) {
                    const x = v[i * n + p], y = v[i * n + q];
                    v[i * n + p] = c * x - s * y;
                    v[i * n + q] = s * x + c * y;
                }
                changed = true;
            }
        if (!changed)
            break;
    }
    const sigma = scratchS.subarray(0,n);
    for (let j = 0; j < n; j++) {
        let s = 0;
        for (let i = 0; i < m; i++)
            s += b[i * n + j] ** 2;
        sigma[j] = Math.sqrt(s);
    }
    return { b, v, sigma, m, n };
}
export function solve(a: Float64Array, m: number, n: number, r: ArrayLike<number>, rcond = 1e-8, damping = 0) {
    const d = svd(a, m, n), x = new Float64Array(n), cut = Math.max(...d.sigma, 0) * rcond;
    for (let j = 0; j < n; j++) {
        const s = d.sigma[j];
        if (s <= cut)
            continue;
        let c = 0;
        for (let i = 0; i < m; i++)
            c += d.b[i * n + j] * r[i];
        c /= s * s + damping;
        for (let i = 0; i < n; i++)
            x[i] += d.v[i * n + j] * c;
    }
    return x;
}
export function nullspace(a: Float64Array, m: number, n: number, rcond = 1e-8) {
    const d = svd(a, m, n), cut = Math.max(...d.sigma, 0) * rcond, ids = [];
    for (let j = 0; j < n; j++)
        if (d.sigma[j] <= cut)
            ids.push(j);
    const out = new Float64Array(n * ids.length);
    for (let i = 0; i < n; i++)
        for (let j = 0; j < ids.length; j++)
            out[i * ids.length + j] = d.v[i * n + ids[j]];
    return { data: out, cols: ids.length };
}
export function transpose(a: Float64Array, m: number, n: number) { const out = new Float64Array(a.length); for (let i = 0; i < m; i++)
    for (let j = 0; j < n; j++)
        out[j * m + i] = a[i * n + j]; return out; }
export function multiply(a: Float64Array, m: number, k: number, b: Float64Array, n: number) { const out = new Float64Array(m * n); for (let i = 0; i < m; i++)
    for (let p = 0; p < k; p++)
        for (let j = 0; j < n; j++)
            out[i * n + j] += a[i * k + p] * b[p * n + j]; return out; }
export function eigenvalues(a: Float64Array, n: number) { const b = a.slice(); for (let it = 0; it < Math.max(1, 50 * n * n); it++) {
    let p = 0, q = 0, max = 0;
    for (let i = 0; i < n; i++)
        for (let j = i + 1; j < n; j++)
            if (Math.abs(b[i * n + j]) > max) {
                max = Math.abs(b[i * n + j]);
                p = i;
                q = j;
            }
    if (max < 1e-14)
        break;
    const angle = .5 * Math.atan2(2 * b[p * n + q], b[q * n + q] - b[p * n + p]), c = Math.cos(angle), s = Math.sin(angle);
    for (let i = 0; i < n; i++) {
        const x = b[i * n + p], y = b[i * n + q];
        b[i * n + p] = c * x - s * y;
        b[i * n + q] = s * x + c * y;
    }
    for (let j = 0; j < n; j++) {
        const x = b[p * n + j], y = b[q * n + j];
        b[p * n + j] = c * x - s * y;
        b[q * n + j] = s * x + c * y;
    }
} return Array.from({ length: n }, (_, i) => b[i * n + i]); }

/** Both nullspaces from one SVD. Complete the left orthogonal complement. */
export function nullspaces(a:Float64Array,m:number,n:number,rcond=1e-8) {
 const d=svd(a,m,n),cut=Math.max(...d.sigma,0)*rcond,zero:number[]=[],nonzero:number[]=[];
 for(let j=0;j<n;j++)(d.sigma[j]<=cut?zero:nonzero).push(j);
 const right=new Float64Array(n*zero.length);
 for(let i=0;i<n;i++)for(let j=0;j<zero.length;j++)right[i*zero.length+j]=d.v[i*n+zero[j]];
 const count=m-nonzero.length,projection=identity(m),left=new Float64Array(m*count);
 for(const k of nonzero)for(let i=0;i<m;i++)for(let j=0;j<m;j++)projection[i*m+j]-=(d.b[i*n+k]/d.sigma[k])*(d.b[j*n+k]/d.sigma[k]);
 for(let k=0;k<count;k++){
  let pivot=0;for(let i=1;i<m;i++)if(projection[i*m+i]>projection[pivot*m+pivot])pivot=i;
  const length=Math.sqrt(Math.max(0,projection[pivot*m+pivot]));
  if(length<1e-8)throw Error('Left nullspace completion did not converge');
  for(let i=0;i<m;i++)left[i*count+k]=projection[i*m+pivot]/length;
  for(let i=0;i<m;i++)for(let j=0;j<m;j++)projection[i*m+j]-=left[i*count+k]*left[j*count+k];
 }
 return {right:{data:right,cols:zero.length},left:{data:left,cols:count}};
}

function activeFit(c:Float64Array,m:number,n:number,target:ArrayLike<number>,a:Float64Array,k:number,bounds:ArrayLike<number>,active:number[]){
 for(let iteration=0;iteration<100;iteration++){
 const aa=Float64Array.from(active.flatMap(i=>Array.from(a.slice(i*n,(i+1)*n)))),b=active.map(i=>bounds[i]),p=active.length?solve(aa,active.length,n,b,1e-10):new Float64Array(n),z=nullspace(aa,active.length,n,1e-10);
 if(active.some((_,i)=>Math.abs(dot(aa.subarray(i*n,(i+1)*n),p)-b[i])>1e-8))throw Error('Incompatible active cable bounds');
 const cp=multiply(c,m,n,p,1),cz=multiply(c,m,n,z.data,z.cols),q=solve(cz,m,z.cols,Float64Array.from(target,(v,i)=>v-cp[i]),1e-10),x=Float64Array.from(p,(v,i)=>v+dot(z.data.subarray(i*z.cols,(i+1)*z.cols),q));
 let worst=-1,error=1e-10;for(let i=0;i<k;i++){const v=dot(a.subarray(i*n,(i+1)*n),x)-bounds[i];if(v>error){worst=i;error=v;}}
 if(worst>=0){if(active.includes(worst))throw Error('Cable active set did not converge');active.push(worst);continue;}
 if(active.length){const residual=Float64Array.from(multiply(c,m,n,x,1),(v,i)=>v-target[i]),gradient=multiply(transpose(c,m,n),n,m,residual,1),mu=solve(transpose(aa,active.length,n),n,active.length,Float64Array.from(gradient,v=>-v),1e-10);let bad=-1;for(let i=0;i<mu.length;i++)if(mu[i]<-1e-10&&(bad<0||mu[i]<mu[bad]))bad=i;if(bad>=0){active.splice(bad,1);continue;}}
 return x;
 }throw Error('Cable active set exceeded iteration budget');
}

export function constrainedFit(c:Float64Array,m:number,n:number,target:ArrayLike<number>,a:Float64Array,k:number,bounds:ArrayLike<number>,workingSet:number[]=[]){
 let active=workingSet.filter(i=>i>=0&&i<k);const hadWarmStart=active.length>0;let result:Float64Array;
 try{result=activeFit(c,m,n,target,a,k,bounds,active);}catch(error){if(!hadWarmStart)throw error;active=[];result=activeFit(c,m,n,target,a,k,bounds,active);}
 workingSet.splice(0,workingSet.length,...active);return result;
}
