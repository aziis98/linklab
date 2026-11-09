import { describe, expect, test } from "bun:test";
import { createCamera, type Vec3 } from "../src/camera";
import { createThreeCamera } from "../src/three-camera";
import { Vector3 } from "three";

const settings = {
  center: [0, 0, 0] as Vec3,
  extent: 2,
  size: [900, 700],
  pan: [20, -10],
  zoom: 1.3,
  angles: [0.6, 0.4],
  dimension: 3,
};

describe("SVG camera", () => {
  for (const perspective of [false, true]) {
    test(`Three.js and SVG ${perspective ? "perspective" : "orthographic"} projections match`, () => {
      const svg = createCamera({ ...settings, perspective });
      const three = createThreeCamera({ ...settings, perspective });
      for (const point of [
        [1, 2, -1],
        [-2, 0.3, 1],
        [0, 0, 0],
      ] as Vec3[]) {
        const projected = new Vector3(...point).project(three);
        const pixel = [
          ((projected.x + 1) * settings.size[0]) / 2,
          ((1 - projected.y) * settings.size[1]) / 2,
        ];
        svg
          .project(point)
          .forEach((v, i) => expect(v).toBeCloseTo(pixel[i], 9));
      }
    });
    test(`${perspective ? "perspective" : "orthographic"} cursor rays recover points on the view plane`, () => {
      const camera = createCamera({ ...settings, perspective });
      for (const point of [
        [1, 2, -1],
        [-2, 0.3, 1],
        [0, 0, 0],
      ] as Vec3[]) {
        const result = camera.unproject(camera.project(point), point)!;
        result.forEach((v, i) => expect(v).toBeCloseTo(point[i], 10));
      }
    });
    test(`${perspective ? "perspective" : "orthographic"} picking preserves the clicked material fraction`, () => {
      const camera = createCamera({ ...settings, perspective });
      const a: Vec3 = [-1, 0, -1],
        b: Vec3 = [2, 1, 2];
      const t = 0.37;
      const point = a.map((v, i) => v + t * (b[i] - v)) as Vec3;
      const p = camera.project(a),
        q = camera.project(b),
        picked = camera.project(point);
      const delta = q.map((v, i) => v - p[i]);
      const screenFraction =
        delta.reduce((s, v, i) => s + v * (picked[i] - p[i]), 0) /
        delta.reduce((s, v) => s + v * v, 0);
      expect(camera.materialFraction(a, b, screenFraction)).toBeCloseTo(t, 10);
    });
  }
  test("perspective changes apparent size with depth while preserving the target-plane scale", () => {
    const ortho = createCamera({
      ...settings,
      angles: [0, 0],
      perspective: false,
    });
    const camera = createCamera({
      ...settings,
      angles: [0, 0],
      perspective: true,
    });
    expect(camera.project([1, 0, 0])).toEqual(ortho.project([1, 0, 0]));
    expect(camera.project([1, 0, 1])[0]).toBeGreaterThan(
      camera.project([1, 0, -1])[0],
    );
  });
  test("perspective clips segments crossing the near plane and hides segments behind the eye", () => {
    const camera = createCamera({
      ...settings,
      angles: [0, 0],
      perspective: true,
    });
    expect(camera.clipSegment([0, 0, 9], [1, 0, 10])).toBeNull();
    const ends = camera.segment([0, 0, 0], [1, 1, 10])!;
    expect(ends.flat().every(Number.isFinite)).toBe(true);
    const path = camera.projectPath(
      [
        [0, 0, 0],
        [1, 1, 10],
        [-1, 0, 0],
      ],
      true,
    );
    expect(path).not.toContain("NaN");
    expect(path).not.toContain("Infinity");
    expect(camera.visible([0, 0, 9])).toBe(false);
  });
});
