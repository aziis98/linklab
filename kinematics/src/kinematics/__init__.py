"""Objects with reduced rigid motions, assembly constraints, and free-motion
analysis for implicit mechanisms.

Quick start::

    from kinematics import Mechanism, Rod, PointConstraint, Fixed, AlignAxis

    m = Mechanism()
    ground, crank = Rod(length=3.0, name="ground"), Rod(length=2.0, name="crank")
    m.add(ground, crank, Fixed(world, ground), PointConstraint(crank, "a", ground, "a"))
    m.dof()          # 1
    m.tangent_basis()  # columns span the instantaneous motion
"""

from __future__ import annotations

from .constraints import (
    AlignAxis,
    Constraint,
    Distance,
    Fixed,
    Planar,
    PointConstraint,
    Value,
)
from .entities import Circle, RigidObject, Rod, Sphere
from .entity import BaseEntity, Entity, World
from .linalg import SE3
from .system import Mechanism, Mobility, Solution

__all__ = [
    # entities
    "Entity",
    "BaseEntity",
    "World",
    "RigidObject",
    "Rod",
    "Circle",
    "Sphere",
    # constraints
    "Constraint",
    "Fixed",
    "PointConstraint",
    "Planar",
    "AlignAxis",
    "Distance",
    "Value",
    # system
    "Mechanism",
    "Mobility",
    "Solution",
    "SE3",
]

__version__ = "0.1.0"
