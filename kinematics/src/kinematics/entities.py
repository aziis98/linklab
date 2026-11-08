"""Concrete entity types.

Variable layout for every entity is ``[px, py, pz, rx, ry, rz, *shape]``
where ``(rx, ry, rz)`` is a rotation vector applied by :func:`so3_exp`.

===========================  =====  =====  =====================================
entity                       vars   dof    reduced motion
===========================  =====  =====  =====================================
:class:`RigidObject`           6      6    none, full SE(3)
:class:`Rod`                   7      5    axial spin about its own axis
:class:`Circle`                7      5    spin about its own normal
:class:`Sphere`                4      4    full SO(3) orientation is a symmetry
===========================  =====  =====  =====================================

The reduced-motion columns are not enforced anywhere: the symmetry simply
shows up as a null direction of the assembly Jacobian, so
``Mechanism.dof`` and ``Mechanism.tangent_basis`` pick it up on their own.
"""

from __future__ import annotations

import numpy as np

from .entity import AXIS_VECTORS, EX, BaseEntity, _check_axis

__all__ = ["RigidObject", "Rod", "Circle", "Sphere"]


class RigidObject(BaseEntity):
    """A fully general body: 6 variables, 6 degrees of freedom."""

    shape_names: tuple[str, ...] = ()
    n_dof = 6

    def __init__(self, name: str = "body") -> None:
        super().__init__(name)


class Rod(BaseEntity):
    """A straight segment centred on its own origin, with a variable length.

    7 variables but only 5 degrees of freedom: the 3 translation and the 2
    directions of the local x axis.  The spin about that axis is a
    symmetry of the segment and appears as a null direction.

    Material points in the body frame, with ``L`` the length variable:

    ``origin``  ``(0, 0, 0)``    the centre of mass
    ``a``       ``(-L/2, 0, 0)``  first end
    ``b``       ``( L/2, 0, 0)``  second end
    ``unit``    ``( 1, 0, 0)``   one unit along the axis, for points at an
                                 arbitrary distance along the rod
    """

    shape_names = ("length",)
    n_dof = 5

    def __init__(self, length: float = 1.0, name: str = "rod") -> None:
        super().__init__(name, length=length)
        if self.length <= 0.0:
            raise ValueError(f"{name}: length must be positive, got {length}")

    @property
    def length(self) -> float:
        return float(self._vars[6])

    @length.setter
    def length(self, value: float) -> None:
        if value <= 0.0:
            raise ValueError(f"{self.name}: length must be positive, got {value}")
        self._vars[6] = float(value)

    @property
    def direction(self) -> np.ndarray:
        """Unit vector along the rod, in world coordinates."""
        return self.rot @ EX

    def _local_points(self) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        L = self.length
        half = np.array([L / 2.0, 0.0, 0.0])
        # Each entry is (3, n_shape) = d(local point) / d(length).
        return (
            {
                "origin": np.zeros(3),
                "a": -half,
                "b": half.copy(),
                "unit": EX.copy(),
            },
            {
                "origin": np.zeros((3, 1)),
                "a": np.array([[-0.5], [0.0], [0.0]]),
                "b": np.array([[0.5], [0.0], [0.0]]),
                "unit": np.zeros((3, 1)),
            },
        )


class Circle(BaseEntity):
    """A planar circle: position, normal, radius.

    7 variables, 5 degrees of freedom.  Only the 3 position and the 2
    directions of the normal (the local z axis) matter; spinning about the
    normal is a symmetry.
    """

    shape_names = ("radius",)
    n_dof = 5

    def __init__(self, radius: float = 1.0, name: str = "circle") -> None:
        super().__init__(name, radius=radius)
        if self.radius <= 0.0:
            raise ValueError(f"{name}: radius must be positive, got {radius}")

    @property
    def radius(self) -> float:
        return float(self._vars[6])

    @radius.setter
    def radius(self, value: float) -> None:
        if value <= 0.0:
            raise ValueError(f"{self.name}: radius must be positive, got {value}")
        self._vars[6] = float(value)

    @property
    def normal(self) -> np.ndarray:
        """Unit normal of the circle's plane, in world coordinates."""
        return self.axis("z")

    def _local_points(self) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        # d(local point) / d(radius)
        return (
            {
                "origin": np.zeros(3),
                "edge": np.array([self.radius, 0.0, 0.0]),
            },
            {
                "origin": np.zeros((3, 1)),
                "edge": np.array([[1.0], [0.0], [0.0]]),
            },
        )


class Sphere(BaseEntity):
    """A ball: position and radius only.

    4 variables, 4 degrees of freedom.  Orientation is a complete symmetry,
    so there is no rotation block at all and only the first three entries
    of the variable vector are used.
    """

    shape_names = ("radius",)
    n_dof = 4

    def __init__(self, radius: float = 1.0, name: str = "sphere") -> None:
        self.name = name
        self._vars = np.zeros(4)
        self._vars[3] = float(radius)
        self._offset = 0
        if self.radius <= 0.0:
            raise ValueError(f"{name}: radius must be positive, got {radius}")

    @property
    def n_vars(self) -> int:
        return 4

    @property
    def n_shape(self) -> int:
        return 1

    def var_names(self) -> list[str]:
        return ["px", "py", "pz", "radius"]

    @property
    def pos(self) -> np.ndarray:
        return self._vars[:3].copy()

    @property
    def rotvec(self) -> np.ndarray:
        # Orientation is a symmetry, so it is pinned to identity.
        return np.zeros(3)

    @property
    def rot(self) -> np.ndarray:
        return np.eye(3)

    @property
    def radius(self) -> float:
        return float(self._vars[3])

    @radius.setter
    def radius(self, value: float) -> None:
        if value <= 0.0:
            raise ValueError(f"{self.name}: radius must be positive, got {value}")
        self._vars[3] = float(value)

    def axis(self, axis: str = "z") -> np.ndarray:
        # Every direction is a symmetry, so any axis reads as the global one.
        return AXIS_VECTORS[_check_axis(axis)].copy()

    def axis_jac(self, axis: str = "z") -> np.ndarray:
        _check_axis(axis)
        return np.zeros((3, self.n_vars))

    def set_axis(self, direction: np.ndarray, axis: str = "x") -> None:
        # A sphere's orientation is a symmetry, so there is nothing to set.
        # Overriding this matters: BaseEntity writes into vars[3:6], which for
        # a Sphere would silently overwrite the radius.
        _check_axis(axis)

    def set_position(self, pos: np.ndarray) -> None:
        self._vars[:3] = np.asarray(pos, dtype=float).reshape(3)

    def place_between(
        self, pa: np.ndarray, pb: np.ndarray, *, scale_shape: bool = True
    ) -> None:
        """A sphere has no orientation, so only the midpoint is meaningful."""
        pa = np.asarray(pa, dtype=float).reshape(3)
        pb = np.asarray(pb, dtype=float).reshape(3)
        self.set_position(0.5 * (pa + pb))

    def point_jac(self, name: str) -> np.ndarray:
        """A sphere's only material point is its centre, so the radius drops out.

        Overriding is necessary: the base class assumes a ``[pos, rot, shape]``
        layout and would read the radius column as a rotation column.
        """
        self._local_point(name)  # validate the name
        J = np.zeros((3, self.n_vars))
        J[:, :3] = np.eye(3)
        return J

    def _local_points(self) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        return (
            {"origin": np.zeros(3)},
            {"origin": np.zeros((3, 1))},
        )
