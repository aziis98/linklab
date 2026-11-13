"""Standalone planar/spatial rigid geometry and motion exploration."""

from .core import (
    Constraint,
    Engine,
    FrameKind,
    PointRef,
    RigidBody,
    RigidObject,
    Ring,
    Rod,
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
    "Exploration",
    "FrameKind",
    "Line",
    "Plane",
    "PointRef",
    "RigidBody",
    "RigidObject",
    "Ring",
    "Rod",
    "Scene",
    "Segment",
    "Session",
    "Sphere",
    "TourPreparation",
    "Vec",
    "Wander",
    "build_scene",
    "intersect",
    "render_png",
]

from .core.exploration import Exploration, TourPreparation
from .core.geometry import Circle, Line, Plane, Segment, Sphere, intersect
from .core.wander import Wander
