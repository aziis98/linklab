import * as THREE from "three";
import { createCamera, type CameraSettings } from "./camera";

/** Match the SVG camera, including zoom and an off-axis pan in perspective. */
export function createThreeCamera(settings: CameraSettings) {
  const { eye, up, scale, distance, near } = createCamera(settings);
  const [width, height] = settings.size;
  const [px, py] = settings.pan;
  let camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  if (settings.perspective) {
    const fov = THREE.MathUtils.radToDeg(
      2 * Math.atan(height / (2 * scale * distance)),
    );
    camera = new THREE.PerspectiveCamera(
      fov,
      width / height,
      near,
      settings.extent * 2000,
    );
    camera.setViewOffset(width, height, -px, -py, width, height);
  } else {
    camera = new THREE.OrthographicCamera(
      (-width / 2 - px) / scale,
      (width / 2 - px) / scale,
      (height / 2 + py) / scale,
      (-height / 2 + py) / scale,
      settings.extent * 0.001,
      settings.extent * 2000,
    );
  }
  camera.position.set(...eye);
  camera.up.set(...up);
  camera.lookAt(...settings.center);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
  return camera;
}
