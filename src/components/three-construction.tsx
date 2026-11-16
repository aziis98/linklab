import { useLayoutEffect, useRef } from "preact/hooks";
import * as THREE from "three";
import { createCamera, type CameraSettings, type Vec3 } from "../camera";
import { createThreeCamera } from "../three-camera";
import type { SceneData } from "./viewer";

export interface ConstructionPick {
  keys: string[];
  edge?: [string, string];
  ring?: boolean;
  objectId?: string;
  matchIds?: string[];
}
type Config = Record<string, Vec3>;
interface Props {
  scene: SceneData;
  configuration: Config;
  camera: CameraSettings;
  highlightElementId?: string | string[] | null;
  onHoverElement?: (id: string | string[] | null) => void;
  onStart: (event: PointerEvent, pick: ConstructionPick) => void;
  onMove: (event: PointerEvent) => void;
  onEnd: (event: PointerEvent) => void;
  onZoom: (delta: number) => void;
  onError: (message: string) => void;
}

class ConstructionRenderer {
  renderer: THREE.WebGLRenderer;
  world = new THREE.Scene();
  camera: THREE.Camera = new THREE.PerspectiveCamera();
  raycaster = new THREE.Raycaster();
  pickables: THREE.Mesh[] = [];
  picks = new Map<THREE.Object3D, ConstructionPick>();
  cylinder = new THREE.CylinderGeometry(1, 1, 1, 12);
  sphere = new THREE.SphereGeometry(1, 16, 12);
  materials = {
    rod: new THREE.MeshPhongMaterial({ shininess: 35 }),
    rodActive: new THREE.MeshPhongMaterial({ shininess: 40 }),
    ground: new THREE.MeshPhongMaterial({ shininess: 20 }),
    groundActive: new THREE.MeshPhongMaterial({ shininess: 25 }),
    joint: new THREE.MeshPhongMaterial({ shininess: 45 }),
    jointActive: new THREE.MeshPhongMaterial({ shininess: 50 }),
    pin: new THREE.MeshPhongMaterial({ shininess: 30 }),
    pinActive: new THREE.MeshPhongMaterial({ shininess: 35 }),
    cable: new THREE.MeshPhongMaterial({ shininess: 25 }),
    cableActive: new THREE.MeshPhongMaterial({ shininess: 35 }),
    cableHit: new THREE.MeshBasicMaterial({
      transparent: true,
      opacity: 0,
      depthWrite: false,
    }),
  };
  meshMetadata = new Map<
    THREE.Mesh,
    { baseMaterial: THREE.MeshPhongMaterial; activeMaterial: THREE.MeshPhongMaterial; matchIds: string[] }
  >();
  edges: { a: string; b: string; cylinder: THREE.Mesh; ends: THREE.Mesh[] }[] =
    [];
  cables: {
    constraint: SceneData["constraints"][number];
    meshes: THREE.Mesh[];
    hitMesh: THREE.Mesh;
    slack: boolean;
  }[] = [];
  joints: { key: string; mesh: THREE.Mesh }[] = [];
  rings: { id: string; mesh: THREE.Mesh; radius: number }[] = [];
  labels: { object: SceneData["objects"][number]; element: HTMLSpanElement }[] =
    [];
  cableScale = 1;
  radius: number;
  viewport = [0, 0];
  constructor(
    canvas: HTMLCanvasElement,
    labels: HTMLDivElement,
    scene: SceneData,
    extent: number,
  ) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
    });
    this.renderer.setClearColor(0, 0);
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.radius = extent * 0.019;
    this.cableScale=scene.scale??1;
    this.world.add(new THREE.AmbientLight(0xffffff, 0.9));
    const light = new THREE.DirectionalLight(0xffffff, 1.7);
    light.position.set(3, 5, 6);
    this.world.add(light);
    const pinned = new Set(
      scene.constraints.filter((c) => c.kind === "pin").map((c) => c.a),
    );
    for (const object of scene.objects) {
      const keys = object.points.map((p) => `${object.id}:${p}`);
      const baseMat = object.fixed ? this.materials.ground : this.materials.rod;
      const activeMat = object.fixed
        ? this.materials.groundActive
        : this.materials.rodActive;
      if (object.kind === "ring") {
        const c = new THREE.Vector3(
          ...scene.configuration[`${object.id}:origin`],
        );
        const radius = new THREE.Vector3(
          ...scene.configuration[`${object.id}:x`],
        ).distanceTo(c);
        const mesh = new THREE.Mesh(
          new THREE.TorusGeometry(1, this.radius / radius, 10, 64),
          baseMat,
        );
        this.addMesh(
          mesh,
          { keys, ring: true, objectId: object.id, matchIds: [object.id, `${object.id}:ring`] },
          baseMat,
          activeMat,
          [object.id, `${object.id}:ring`],
        );
        this.rings.push({ id: object.id, mesh, radius });
      } else {
        keys.forEach((a, i) =>
          keys.slice(i + 1).forEach((b) => {
            const matchIds = [object.id, `${a}|${b}`];
            const pick: ConstructionPick = {
              keys,
              edge: [a, b],
              objectId: object.id,
              matchIds,
            };
            const cylinder = new THREE.Mesh(this.cylinder, baseMat);
            const aConstraints = scene.constraints
              .filter((c) => c.a === a || c.b === a)
              .map((c) => c.id);
            const bConstraints = scene.constraints
              .filter((c) => c.a === b || c.b === b)
              .map((c) => c.id);
            const ends = [
              new THREE.Mesh(this.sphere, baseMat),
              new THREE.Mesh(this.sphere, baseMat),
            ];
            this.addMesh(cylinder, pick, baseMat, activeMat, matchIds);
            this.addMesh(
              ends[0],
              pick,
              baseMat,
              activeMat,
              [...aConstraints, ...matchIds, a],
            );
            this.addMesh(
              ends[1],
              pick,
              baseMat,
              activeMat,
              [...bConstraints, ...matchIds, b],
            );
            this.edges.push({ a, b, cylinder, ends });
          }),
        );
      }
      const jointKeys=[...new Set([...keys,...scene.constraints.flatMap(c=>[c.a,c.b].filter((key):key is string=>!!key&&key.startsWith(`${object.id}:`)))])];
      for (const key of jointKeys) {
        if (
          object.kind === "ring" &&
          !scene.constraints.some((c) => c.a === key || c.b === key)
        )
          continue;
        const relatedConstraints =
          scene.constraints.filter((c) => c.a === key || c.b === key);
        const matchIds = [...relatedConstraints.map((c) => c.id), object.id, key];
        const jointBaseMat = object.fixed
          ? this.materials.ground
          : pinned.has(key)
            ? this.materials.pin
            : this.materials.joint;
        const jointActiveMat = object.fixed
          ? this.materials.groundActive
          : pinned.has(key)
            ? this.materials.pinActive
            : this.materials.jointActive;
        const mesh = new THREE.Mesh(this.sphere, jointBaseMat);
        this.addMesh(
          mesh,
          { keys: [key], objectId: object.id, matchIds },
          jointBaseMat,
          jointActiveMat,
          matchIds,
        );
        this.joints.push({ key, mesh });
      }
      const label = document.createElement("span");
      label.className = "three-label";
      label.dataset.objectLabel = object.id;
      label.textContent = object.id;
      labels.append(label);
      this.labels.push({ object, element: label });
    }
    for (const constraint of scene.constraints.filter(
      (c) => c.kind === "cable",
    )) {
      const pick: ConstructionPick = { keys: [], matchIds: [constraint.id] };
      const hitMesh = new THREE.Mesh(this.cylinder, this.materials.cableHit);
      this.world.add(hitMesh);
      this.pickables.push(hitMesh);
      this.picks.set(hitMesh, pick);
      const meshes = Array.from({ length: 16 }, () => {
        const mesh = new THREE.Mesh(this.cylinder, this.materials.cable);
        this.addMesh(
          mesh,
          pick,
          this.materials.cable,
          this.materials.cableActive,
          [constraint.id],
        );
        return mesh;
      });
      this.cables.push({ constraint, meshes, hitMesh, slack: false });
    }
    this.recolor(canvas);
  }
  addMesh(
    mesh: THREE.Mesh,
    pick: ConstructionPick,
    baseMaterial: THREE.MeshPhongMaterial,
    activeMaterial: THREE.MeshPhongMaterial,
    matchIds: string[],
  ) {
    this.world.add(mesh);
    this.pickables.push(mesh);
    this.picks.set(mesh, pick);
    this.meshMetadata.set(mesh, { baseMaterial, activeMaterial, matchIds });
  }
  recolor(canvas: HTMLCanvasElement) {
    const css = getComputedStyle(canvas);
    const color = (token: string) =>
      new THREE.Color(css.getPropertyValue(token).trim());
    const background = color("--cad-bg");
    const dark = background.getHSL({ h: 0, s: 0, l: 0 }).l < 0.3;
    const accent = color("--accent");

    this.materials.rod.color
      .copy(color("--cad-rod-stroke"))
      .lerp(background, dark ? 0.25 : 0.68);
    this.materials.rodActive.color
      .copy(this.materials.rod.color)
      .lerp(accent, 0.45);

    this.materials.ground.color
      .copy(color("--cad-ground-stroke"))
      .lerp(background, 0.45);
    this.materials.groundActive.color
      .copy(this.materials.ground.color)
      .lerp(accent, 0.45);

    this.materials.joint.color.copy(color("--cad-joint-ring"));
    this.materials.jointActive.color
      .copy(this.materials.joint.color)
      .lerp(accent, 0.55);

    this.materials.pin.color.copy(color("--cad-joint-pin"));
    this.materials.pinActive.color
      .copy(this.materials.pin.color)
      .lerp(accent, 0.55);

    this.materials.cable.color.copy(color("--cad-cable"));
    this.materials.cableActive.color.copy(accent);
  }
  setHighlight(highlightId: string | string[] | null) {
    const activeIds = !highlightId
      ? null
      : Array.isArray(highlightId)
        ? new Set(highlightId)
        : new Set([highlightId]);
    for (const [mesh, meta] of this.meshMetadata) {
      const active =
        activeIds != null && meta.matchIds.some((id) => activeIds.has(id));
      mesh.material = active ? meta.activeMaterial : meta.baseMaterial;
    }
  }
  update(
    configuration: Config,
    settings: CameraSettings,
    highlightId: string | string[] | null = null,
  ) {
    if (settings.size.some((value, i) => value !== this.viewport[i])) {
      this.renderer.setSize(settings.size[0], settings.size[1], false);
      this.viewport = [...settings.size];
    }
    this.camera = createThreeCamera(settings);
    const r = this.radius,
      y = new THREE.Vector3(0, 1, 0);
    const activeIds = !highlightId
      ? null
      : Array.isArray(highlightId)
        ? new Set(highlightId)
        : new Set([highlightId]);
    for (const edge of this.edges) {
      const a = new THREE.Vector3(...configuration[edge.a]),
        b = new THREE.Vector3(...configuration[edge.b]);
      const delta = b.clone().sub(a);
      const length = delta.length();
      edge.cylinder.position.copy(a).add(b).multiplyScalar(0.5);
      edge.cylinder.quaternion.setFromUnitVectors(y, delta.normalize());
      edge.cylinder.scale.set(r, Math.max(length, 1e-8), r);
      edge.ends.forEach((mesh, i) => {
        mesh.position.copy(i ? b : a);
        mesh.scale.setScalar(r);
      });
    }
    for (const cable of this.cables) {
      const a = new THREE.Vector3(...configuration[cable.constraint.a]),
        b = new THREE.Vector3(...configuration[cable.constraint.b!]),
        delta = b.clone().sub(a),
        length = delta.length(),
        slack =
          ((cable.constraint.length ?? 0) - length) / this.cableScale >
          (cable.slack ? 1e-8 : 5e-8);
      cable.slack = slack;
      const dir = length > 1e-12 ? delta.clone().normalize() : y.clone();
      cable.hitMesh.position.copy(a).add(b).multiplyScalar(0.5);
      cable.hitMesh.quaternion.setFromUnitVectors(y, dir);
      cable.hitMesh.scale.set(r * 1.1, Math.max(length, 1e-8), r * 1.1);
      cable.meshes.forEach((mesh, i) => {
        const t = (i + 0.5) / 16;
        mesh.position.copy(a).addScaledVector(delta, t);
        mesh.quaternion.setFromUnitVectors(y, dir);
        mesh.scale.set(
          r * 0.35,
          Math.max((length / 16) * (slack ? 0.6 : 1), 1e-8),
          r * 0.35,
        );
      });
    }
    for (const { key, mesh } of this.joints) {
      mesh.position.set(...configuration[key]);
      const meta = this.meshMetadata.get(mesh);
      const active =
        activeIds != null &&
        (meta?.matchIds.some((id) => activeIds.has(id)) ?? false);
      mesh.scale.setScalar(r * (active ? 1.7 : 1.4));
    }
    for (const { id, mesh, radius } of this.rings) {
      const c = new THREE.Vector3(...configuration[`${id}:origin`]);
      const x = new THREE.Vector3(...configuration[`${id}:x`])
        .sub(c)
        .normalize();
      const y = new THREE.Vector3(...configuration[`${id}:y`])
        .sub(c)
        .normalize();
      mesh.position.copy(c);
      mesh.quaternion.setFromRotationMatrix(
        new THREE.Matrix4().makeBasis(x, y, x.clone().cross(y).normalize()),
      );
      mesh.scale.setScalar(radius);
    }
    const projection = createCamera(settings);
    for (const { object, element } of this.labels) {
      const point: Vec3 =
        object.kind === "ring"
          ? configuration[`${object.id}:x`]
          : ([0, 1, 2].map(
              (axis) =>
                object.points.reduce(
                  (s, p) => s + configuration[`${object.id}:${p}`][axis],
                  0,
                ) / object.points.length,
            ) as Vec3);
      const [x, y] = projection.project(point);
      element.hidden =
        !projection.visible(point) ||
        x < 0 ||
        y < 0 ||
        x > settings.size[0] ||
        y > settings.size[1];
      element.style.transform = `translate(${x + 10}px,${y - 12}px)`;
      if (activeIds != null && activeIds.has(object.id)) {
        element.style.color = "var(--accent)";
        element.style.fontWeight = "bold";
      } else {
        element.style.color = "";
        element.style.fontWeight = "";
      }
    }
    this.setHighlight(highlightId);
    this.world.updateMatrixWorld(true);
    this.renderer.render(this.world, this.camera);
    this.renderer.domElement.dataset.meshCount = String(this.pickables.length);
    this.renderer.domElement.dataset.ready = "true";
  }
  pick(event: PointerEvent, canvas: HTMLCanvasElement): ConstructionPick {
    const rect = canvas.getBoundingClientRect();
    this.raycaster.setFromCamera(
      new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        (-(event.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      this.camera,
    );
    const hit = this.raycaster.intersectObjects(this.pickables, false)[0];
    return hit ? this.picks.get(hit.object)! : { keys: [] };
  }
  dispose() {
    this.cylinder.dispose();
    this.sphere.dispose();
    for (const ring of this.rings) ring.mesh.geometry.dispose();
    for (const material of Object.values(this.materials)) material.dispose();
    for (const label of this.labels) label.element.remove();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
  }
}

export default function ThreeConstruction(props: Props) {
  const canvas = useRef<HTMLCanvasElement>(null),
    labels = useRef<HTMLDivElement>(null);
  const runtime = useRef<ConstructionRenderer | null>(null);
  const latest = useRef(props);
  latest.current = props;
  useLayoutEffect(() => {
    const element = canvas.current!;
    try {
      runtime.current = new ConstructionRenderer(
        element,
        labels.current!,
        props.scene,
        props.camera.extent,
      );
      runtime.current.update(
        props.configuration,
        props.camera,
        props.highlightElementId ?? null,
      );
    } catch (error) {
      runtime.current?.dispose();
      runtime.current = null;
      latest.current.onError(`Three.js could not start: ${String(error)}`);
      return;
    }
    const media = matchMedia("(prefers-color-scheme: dark)");
    const recolor = () => {
      runtime.current?.recolor(element);
      runtime.current?.update(
        latest.current.configuration,
        latest.current.camera,
        latest.current.highlightElementId ?? null,
      );
    };
    const lost = (event: Event) => {
      event.preventDefault();
      latest.current.onError("The WebGL context was lost; switched to SVG.");
    };
    media.addEventListener("change", recolor);
    element.addEventListener("webglcontextlost", lost);
    return () => {
      media.removeEventListener("change", recolor);
      element.removeEventListener("webglcontextlost", lost);
      runtime.current?.dispose();
      runtime.current = null;
    };
  }, [props.scene.revision]);
  useLayoutEffect(() => {
    runtime.current?.update(
      props.configuration,
      props.camera,
      props.highlightElementId ?? null,
    );
  });
  return (
    <div class="three-construction" data-renderer="three">
      <canvas
        ref={canvas}
        aria-label="Three.js construction"
        role="img"
        onPointerDown={(e) =>
          props.onStart(
            e,
            runtime.current?.pick(e, canvas.current!) ?? { keys: [] },
          )
        }
        onPointerMove={(e) => {
          props.onMove(e);
          if (props.onHoverElement && canvas.current) {
            const picked = runtime.current?.pick(e, canvas.current);
            props.onHoverElement(
              picked?.matchIds?.[0] ?? picked?.objectId ?? null,
            );
          }
        }}
        onPointerLeave={() => {
          props.onHoverElement?.(null);
        }}
        onPointerUp={props.onEnd}
        onPointerCancel={props.onEnd}
        onLostPointerCapture={props.onEnd}
        onWheel={(e) => {
          e.preventDefault();
          props.onZoom(e.deltaY);
        }}
      />
      <div class="three-labels" ref={labels} />
    </div>
  );
}
