"""Standalone planar/spatial rigid geometry and motion exploration."""

from .core import (
    Constraint,
    Engine,
    PointRef,
    RigidObject,
    Scene,
    Session,
    Vec,
    build_scene,
    render_png,
)

__all__ = [
    "Circle",
    "Constraint",
    "Engine",
    "Line",
    "Plane",
    "PointRef",
    "RigidObject",
    "Scene",
    "Segment",
    "Session",
    "Sphere",
    "Vec",
    "build_scene",
    "intersect",
    "render_png",
]

from .core.geometry import Circle, Line, Plane, Segment, Sphere, intersect
