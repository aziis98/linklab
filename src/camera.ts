export type Vec3 = [number, number, number];
const add = (a: Vec3, b: Vec3): Vec3 => a.map((v, i) => v + b[i]) as Vec3;
const sub = (a: Vec3, b: Vec3): Vec3 => a.map((v, i) => v - b[i]) as Vec3;
const mul = (a: Vec3, s: number): Vec3 => a.map((v) => v * s) as Vec3;
const dot = (a: Vec3, b: Vec3) => a.reduce((s, v, i) => s + v * b[i], 0);

export interface CameraSettings {
  center: Vec3;
  extent: number;
  size: number[];
  pan: number[];
  zoom: number;
  angles: number[];
  perspective: boolean;
  dimension: number;
}

/** Shared projection, near-plane clipping, and cursor rays for both renderers. */
export function createCamera({
  center,
  extent,
  size,
  pan,
  zoom,
  angles,
  perspective,
  dimension,
}: CameraSettings) {
  const [yaw, pitch] = angles;
  const right: Vec3 = [Math.cos(yaw), 0, -Math.sin(yaw)];
  const up: Vec3 = [
    -Math.sin(yaw) * Math.sin(pitch),
    Math.cos(pitch),
    -Math.cos(yaw) * Math.sin(pitch),
  ];
  const ray: Vec3 = [
    Math.sin(yaw) * Math.cos(pitch),
    Math.sin(pitch),
    Math.cos(yaw) * Math.cos(pitch),
  ];
  const scale = (Math.min(...size) / (extent * 2.8)) * zoom;
  const distance = 4 * extent;
  const near = distance * 0.05;
  const eye = add(center, mul(ray, distance));
  const depth = (point: Vec3) => distance - dot(sub(point, center), ray);
  const visible = (point: Vec3) => !perspective || depth(point) >= near;
  function project(point: Vec3): [number, number] {
    const offset = sub(point, center);
    const factor = perspective ? distance / Math.max(near, depth(point)) : 1;
    return [
      size[0] / 2 + pan[0] + scale * factor * dot(offset, right),
      size[1] / 2 + pan[1] - scale * factor * dot(offset, up),
    ];
  }
  function clipSegment(a: Vec3, b: Vec3): [Vec3, Vec3] | null {
    if (!perspective) return [a, b];
    const da = depth(a),
      db = depth(b);
    if (da < near && db < near) return null;
    const delta = sub(b, a);
    return [
      da < near ? add(a, mul(delta, (near - da) / (db - da))) : a,
      db < near ? add(a, mul(delta, (near - da) / (db - da))) : b,
    ];
  }
  function segment(a: Vec3, b: Vec3): [number[], number[]] | null {
    const clipped = clipSegment(a, b);
    return clipped && [project(clipped[0]), project(clipped[1])];
  }
  function projectPath(points: Vec3[], closed = false): string {
    if (!points.length) return "";
    if (points.every(visible))
      return `M ${points.map((p) => project(p).join(",")).join(" L ")}${closed ? " Z" : ""}`;
    const chain = closed ? [...points, points[0]] : points;
    return chain
      .slice(1)
      .map((b, i) => {
        const ends = segment(chain[i], b);
        return ends ? `M ${ends[0].join(",")} L ${ends[1].join(",")}` : "";
      })
      .join(" ");
  }
  function unproject(screen: number[], anchor: Vec3): Vec3 | null {
    const horizontal = (screen[0] - size[0] / 2 - pan[0]) / scale;
    const vertical = -(screen[1] - size[1] / 2 - pan[1]) / scale;
    const base = perspective
      ? eye
      : add(center, add(mul(right, horizontal), mul(up, vertical)));
    const direction = perspective
      ? add(
          mul(ray, -1),
          add(mul(right, horizontal / distance), mul(up, vertical / distance)),
        )
      : ray;
    const normal: Vec3 = dimension === 2 ? [0, 0, 1] : ray;
    const denominator = dot(direction, normal);
    if (Math.abs(denominator) < 1e-6) return null;
    const result = add(
      base,
      mul(direction, dot(sub(anchor, base), normal) / denominator),
    );
    return visible(result) ? result : null;
  }
  function materialFraction(a: Vec3, b: Vec3, screenFraction: number): number {
    if (!perspective) return screenFraction;
    return (
      (screenFraction * depth(a)) /
      ((1 - screenFraction) * depth(b) + screenFraction * depth(a))
    );
  }
  return {
    eye,
    up,
    distance,
    near,
    ray,
    scale,
    project,
    visible,
    clipSegment,
    segment,
    projectPath,
    unproject,
    materialFraction,
  };
}
