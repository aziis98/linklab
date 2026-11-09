"""Compatibility import for native scene scripts. Browser scripts use build_scene."""
from kinematics.core.model import Vec, origin, right, left, up, down, forward, backward, sqrt, Scene
scene = Scene(dimension=None)
rod = scene.rod
body = scene.body
pin = scene.pin
coincident = scene.coincident
constraint_point_point = scene.coincident
distance = scene.distance
fixed = scene.fixed
point_on_plane = scene.point_on_plane
parallel = scene.parallel

plane = scene.plane
def scene_dimension(value):
    scene.dimension = value

ring = scene.ring
