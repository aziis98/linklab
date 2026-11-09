import { useLayoutEffect, useRef } from "preact/hooks";
import * as THREE from "three";
import { createCamera, type CameraSettings, type Vec3 } from "../camera";
import { createThreeCamera } from "../three-camera";
import type { SceneData } from "./viewer";

export interface ConstructionPick {
  keys: string[];
  edge?: [string, string];
  ring?: boolean;
}
type Config = Record<string, Vec3>;
interface Props {
  scene: SceneData;
  configuration: Config;
  camera: CameraSettings;
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
    ground: new THREE.MeshPhongMaterial({ shininess: 20 }),
    joint: new THREE.MeshPhongMaterial({ shininess: 45 }),
    pin: new THREE.MeshPhongMaterial({ shininess: 30 }),
  };
  edges: { a: string; b: string; cylinder: THREE.Mesh; ends: THREE.Mesh[] }[] =
    [];
  joints: { key: string; mesh: THREE.Mesh }[] = [];
  rings: { id: string; mesh: THREE.Mesh; radius: number }[] = [];
  labels: { object: SceneData["objects"][number]; element: HTMLSpanElement }[] =
    [];
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
    this.world.add(new THREE.AmbientLight(0xffffff, 0.9));
    const light = new THREE.DirectionalLight(0xffffff, 1.7);
    light.position.set(3, 5, 6);
    this.world.add(light);
    const pinned = new Set(
      scene.constraints.filter((c) => c.kind === "pin").map((c) => c.a),
    );
    for (const object of scene.objects) {
      const keys = object.points.map((p) => `${object.id}:${p}`);
      const material = object.fixed
        ? this.materials.ground
        : this.materials.rod;
      if (object.kind === "ring") {
        const c = new THREE.Vector3(
          ...scene.configuration[`${object.id}:origin`],
        );
        const radius = new THREE.Vector3(
          ...scene.configuration[`${object.id}:x`],
        ).distanceTo(c);
        const mesh = new THREE.Mesh(
          new THREE.TorusGeometry(1, this.radius / radius, 10, 64),
          material,
        );
        this.addMesh(mesh, { keys, ring: true });
        this.rings.push({ id: object.id, mesh, radius });
      } else {
        keys.forEach((a, i) =>
          keys.slice(i + 1).forEach((b) => {
            const pick: ConstructionPick = { keys, edge: [a, b] };
            const cylinder = new THREE.Mesh(this.cylinder, material);
            const ends = [
              new THREE.Mesh(this.sphere, material),
              new THREE.Mesh(this.sphere, material),
            ];
            for (const mesh of [cylinder, ...ends]) this.addMesh(mesh, pick);
            this.edges.push({ a, b, cylinder, ends });
          }),
        );
      }
      for (const key of keys) {
        if (
          object.kind === "ring" &&
          !scene.constraints.some((c) => c.a === key || c.b === key)
        )
          continue;
        const mesh = new THREE.Mesh(
          this.sphere,
          object.fixed
            ? this.materials.ground
            : pinned.has(key)
              ? this.materials.pin
              : this.materials.joint,
        );
        this.addMesh(mesh, { keys: [key] });
        this.joints.push({ key, mesh });
      }
      const label = document.createElement("span");
      label.className = "three-label";
      label.dataset.objectLabel = object.id;
      label.textContent = object.id;
      labels.append(label);
      this.labels.push({ object, element: label });
    }
    this.recolor(canvas);
  }
  addMesh(mesh: THREE.Mesh, pick: ConstructionPick) {
    this.world.add(mesh);
    this.pickables.push(mesh);
    this.picks.set(mesh, pick);
  }
  recolor(canvas: HTMLCanvasElement) {
    const css = getComputedStyle(canvas);
    const color = (token: string) =>
      new THREE.Color(css.getPropertyValue(token).trim());
    const background = color("--cad-bg");
    const dark = background.getHSL({ h: 0, s: 0, l: 0 }).l < 0.3;
    this.materials.rod.color
      .copy(color("--cad-rod-stroke"))
      .lerp(background, dark ? 0.25 : 0.68);
    this.materials.ground.color
      .copy(color("--cad-ground-stroke"))
      .lerp(background, 0.45);
    this.materials.joint.color.copy(color("--cad-joint-ring"));
    this.materials.pin.color.copy(color("--cad-joint-pin"));
  }
  update(configuration: Config, settings: CameraSettings) {
    if (settings.size.some((value, i) => value !== this.viewport[i])) {
      this.renderer.setSize(settings.size[0], settings.size[1], false);
      this.viewport = [...settings.size];
    }
    this.camera = createThreeCamera(settings);
    const r = this.radius,
      y = new THREE.Vector3(0, 1, 0);
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
    for (const { key, mesh } of this.joints) {
      mesh.position.set(...configuration[key]);
      mesh.scale.setScalar(r * 1.4);
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
    }
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
      runtime.current.update(props.configuration, props.camera);
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
    runtime.current?.update(props.configuration, props.camera);
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
        onPointerMove={props.onMove}
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
