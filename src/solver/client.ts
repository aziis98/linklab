import type { Config, Engine, Model } from './engine';
export type DragBackend = 'javascript' | 'python';
type Preview = ReturnType<Engine['preview']>;
type Tag = { revision: number; generation: number; interaction: number };
type Message = { op: string; revision?: number; keys?: string[]; targets?: number[][]; weights?: number[]; preview_tag?: Tag };
type GhostJob = Message & { pose: Float64Array; epoch: number; sequence: number };
const KEY = 'linklab.drag-engine.v1';
const GHOST_INTERVAL = 1000 / 20;
const listeners = new Set<(event: { preview: Preview; tag: Tag }) => void>();
export function subscribePreview(listener: (event: { preview: Preview; tag: Tag }) => void) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
}
export function getDragBackend(): DragBackend { return localStorage.getItem(KEY) === 'python' ? 'python' : 'javascript'; }
export function setDragBackend(value: DragBackend) { localStorage.setItem(KEY, value); cancelGhost(); window.dispatchEvent(new Event('linklab-drag-backend-change')); }

/** Each worker owns its numerical state; returned buffers are recycled independently. */
class Transport {
    worker: Worker | null = null;
    recycle: ArrayBuffer | null = null;
    serial = 0;
    pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void }>();
    constructor(privateFailure: () => void) { this.failure = privateFailure; }
    failure: () => void;
    call(message: object): Promise<unknown> {
        if (!this.worker) {
            this.worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
            this.worker.onmessage = ({ data }) => {
                const entry = this.pending.get(data.id); this.pending.delete(data.id);
                if (data.error) entry?.reject(Error(data.error)); else entry?.resolve(data.result);
            };
            this.worker.onerror = event => { this.stop(Error(event.message)); this.failure(); };
        }
        const id = ++this.serial;
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            const recycle = this.recycle; this.recycle = null;
            this.worker!.postMessage({ ...message, id, recycle }, recycle ? [recycle] : []);
        });
    }
    stop(error = Error('Drag engine stopped')) {
        this.worker?.terminate(); this.worker = null; this.recycle = null;
        for (const entry of this.pending.values()) entry.reject(error);
        this.pending.clear();
    }
}
let loaded = false, dirty: Config | null = null, model: Model | null = null;
let epoch = 0, sequence = 0, previewEpoch = -1, latest: GhostJob | null = null;
let timer: ReturnType<typeof setTimeout> | null = null, ghostBusy = false, lastGhost = -Infinity;
const dragWorker = new Transport(() => { loaded = false; });
const ghostWorker = new Transport(() => { previewEpoch = -1; });
function decode(poses: Float64Array, activeModel: Model): Config {
    const d = activeModel.dimension;
    return Object.fromEntries(activeModel.keys.map((key, i) => [key, [...poses.slice(i*d, (i+1)*d), ...(d === 2 ? [0] : [])]]));
}
function cancelGhost() {
    epoch++; latest = null;
    if (timer !== null) clearTimeout(timer);
    timer = null;
}
function scheduleGhost() {
    if (timer !== null || ghostBusy || !latest) return;
    timer = setTimeout(() => { timer = null; void fitGhost(); }, Math.max(0, GHOST_INTERVAL - (performance.now() - lastGhost)));
}
async function fitGhost() {
    const job = latest, activeModel = model;
    if (!job || !activeModel) return;
    latest = null; ghostBusy = true; lastGhost = performance.now();
    try {
        if (previewEpoch !== job.epoch) {
            await ghostWorker.call({ op: 'init', model: activeModel }); previewEpoch = job.epoch;
        }
        if (job.epoch !== epoch) return;
        const result = await ghostWorker.call({ ...job, op: 'preview' }) as Preview & { poses: Float64Array };
        const preview = { ...result, configuration: decode(result.poses, activeModel) };
        ghostWorker.recycle = result.poses.buffer as ArrayBuffer;
        if (job.epoch === epoch && job.preview_tag) {
            for (const listener of listeners) listener({ preview, tag: job.preview_tag });
        }
    } catch {
        // A failed visual fit must never delay or roll back an accepted pose.
        previewEpoch = -1;
    } finally { ghostBusy = false; scheduleGhost(); }
}
export async function dispatch<T>(input: object, python: <R>(message: object) => Promise<R>): Promise<T> {
    const message = input as Message, op = message.op;
    if (op === 'drag' && getDragBackend() === 'javascript') {
        if (!loaded) {
            if (dirty) { await python({ op:'adopt', configuration:dirty }); dirty = null; }
            model = await python<Model>({ op:'numerical_model' });
            cancelGhost(); await dragWorker.call({ op:'init', model }); loaded = true;
        }
        const result = await dragWorker.call(message) as { poses: Float64Array; configuration: Config };
        result.configuration = decode(result.poses, model!);
        if (message.preview_tag) {
            // Copy only the latest accepted pose; ghost work has its own CPU queue.
            latest = { ...message, pose:result.poses.slice(), epoch, sequence:++sequence };
            scheduleGhost();
        }
        dragWorker.recycle = result.poses.buffer as ArrayBuffer;
        dirty = result.configuration;
        return { ...result, poses:undefined } as T;
    }
    cancelGhost();
    if (dirty) { await python({ op:'adopt', configuration:dirty }); dirty = null; }
    if (op === 'sync_drag') return {} as T;
    if (['run','adopt','reset','select','reassemble','drag'].includes(op)) loaded = false;
    return python<T>(input);
}
export function stopDragWorker() {
    cancelGhost(); dragWorker.stop(); ghostWorker.stop(); loaded = false; dirty = null; model = null; previewEpoch = -1;
}
