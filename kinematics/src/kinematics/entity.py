"""The :class:`Entity` protocol and the shared base class.

An entity is anything that contributes a contiguous block of scalar
variables to a mechanism and can report where its material points are.
A general rigid body is ``pos + rot`` (6 variables, 6 degrees of
freedom).  Symmetric entities add a shape variable and drop degrees of
freedom instead: the *axial spin* of a segment or the *in-plane spin* of
a circle are symmetries of the shape, so they appear in the assembly
Jacobian as null directions rather than as free motion.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from .linalg import hat, rotvec_aligning, so3_exp, so3_log, so3_right_jacobian

__all__ = ["Entity", "BaseEntity", "World", "EX", "EY", "EZ", "AXIS_VECTORS"]

EX = np.array([1.0, 0.0, 0.0])
EY = np.array([0.0, 1.0, 0.0])
EZ = np.array([0.0, 0.0, 1.0])

AXIS_VECTORS = {"x": EX, "y": EY, "z": EZ}
_AXIS_VECTORS = AXIS_VECTORS  # backwards-compatible alias


@runtime_checkable
class Entity(Protocol):
    """Anything that owns variables inside a mechanism.

    The protocol is intentionally thin: :meth:`vars` hands back the raw
    numbers, and everything else is derived from them.
    """

    def vars(self) -> np.ndarray:
        """Current values of this entity's variables, in declaration order."""

    def set_vars(self, v: np.ndarray) -> None:
        """Overwrite this entity's variables in place."""


class BaseEntity:
    """Common machinery for entities laid out as ``[pos(3), rot(3), *shape]``.

    Subclasses provide :attr:`shape_names`, :attr:`n_dof`, and
    :meth:`_local_points`.  The local x axis of every body points along its
    principal direction, so a segment's endpoints are at
    ``pos -/+ (length/2) * R @ EX``.
    """

    shape_names: tuple[str, ...] = ()
    n_dof: int = 6

    def __init__(self, name: str = "entity", **shape: float) -> None:
        if set(shape) != set(self.shape_names):
            raise TypeError(
                f"{type(self).__name__} expects shape {tuple(self.shape_names)}, "
                f"got {tuple(shape)}"
            )
        self.name = name
        self._vars = np.zeros(6 + len(self.shape_names))
        self._vars[6:] = [float(shape[s]) for s in self.shape_names]
        self._offset = 0

    # ---------------------------------------------------------------- layout

    @property
    def n_vars(self) -> int:
        return 6 + len(self.shape_names)

    @property
    def n_shape(self) -> int:
        return len(self.shape_names)

    def var_names(self) -> list[str]:
        return ["px", "py", "pz", "rx", "ry", "rz", *self.shape_names]

    def index(self, var: str | int) -> int:
        """Local index of a named or numbered variable."""
        if isinstance(var, (int, np.integer)):
            return int(var)
        return self.var_names().index(var)

    @property
    def offset(self) -> int:
        """Where this entity's variables start in the mechanism's vector.

        Assigned when the entity is added to a :class:`~kinematics.system.Mechanism`.
        """
        return self._offset

    @property
    def global_slice(self) -> slice:
        return slice(self._offset, self._offset + self.n_vars)

    def _bind(self, offset: int) -> None:
        self._offset = int(offset)

    # ------------------------------------------------------------- variables

    def vars(self) -> np.ndarray:
        return self._vars.copy()

    def set_vars(self, v: np.ndarray) -> None:
        v = np.asarray(v, dtype=float).reshape(-1)
        if v.size != self.n_vars:
            raise ValueError(
                f"{self.name}: expected {self.n_vars} variables, got {v.size}"
            )
        self._vars[...] = v

    def get_var(self, var: str | int) -> float:
        return float(self._vars[self.index(var)])

    def set_var(self, var: str | int, value: float) -> None:
        self._vars[self.index(var)] = float(value)

    @property
    def pos(self) -> np.ndarray:
        return self._vars[:3].copy()

    @property
    def rotvec(self) -> np.ndarray:
        return self._vars[3:6].copy()

    @property
    def rot(self) -> np.ndarray:
        return so3_exp(self._vars[3:6])

    def shape(self) -> dict[str, float]:
        return {s: float(self._vars[6 + i]) for i, s in enumerate(self.shape_names)}

    # ---------------------------------------------------------- pose & points

    def _local_points(self) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        """Body-frame material points and their shape derivative.

        Returns two dicts with the same keys.  The second holds arrays of
        shape ``(3, n_shape)``, i.e. the derivative of each point's body
        coordinates with respect to the trailing shape variables.
        """
        zero = np.zeros((3, self.n_shape))
        return {"origin": np.zeros(3)}, {"origin": zero}

    def _local_point(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        points, jac = self._local_points()
        if name not in points:
            raise KeyError(
                f"{type(self).__name__} {self.name!r} has no point {name!r}; "
                f"available: {sorted(points)}"
            )
        return points[name], jac[name]

    def point(self, name: str) -> np.ndarray:
        """World position of the material point ``name``."""
        local, _ = self._local_point(name)
        return self._vars[:3] + self.rot @ local

    def point_jac(self, name: str) -> np.ndarray:
        """Jacobian of :meth:`point` with respect to this entity's variables."""
        local, dlocal = self._local_point(name)
        R = self.rot
        J = np.zeros((3, self.n_vars))
        J[:, :3] = np.eye(3)
        # d/d(rotvec) of (pos + R @ local).  A rotation-vector increment is
        # not orthonormal, so pull it back first, dtheta = Jr(rotvec) d(rotvec),
        # and then d(R u) = -R hat(u) dtheta.  Note this is R hat(u), not
        # hat(R u): only R hat(u) R^T equals hat(R u).
        J[:, 3:6] = -R @ hat(local) @ so3_right_jacobian(self._vars[3:6])
        J[:, 6:] = R @ dlocal                 # shape variables move the point
        return J

    def points(self, *names: str) -> dict[str, np.ndarray]:
        return {n: self.point(n) for n in names}

    def axis(self, axis: str = "z") -> np.ndarray:
        """World direction of a body-frame principal axis."""
        return self.rot @ _AXIS_VECTORS[_check_axis(axis)]

    def axis_jac(self, axis: str = "z") -> np.ndarray:
        """Jacobian of :meth:`axis` with respect to the rotation vector."""
        u = _AXIS_VECTORS[_check_axis(axis)]
        R = self.rot
        J = np.zeros((3, self.n_vars))
        # d(R u)/d(rotvec): with R -> R exp(dtheta) and dtheta = Jr d(rotvec),
        #   R u -> R (u + dtheta x u) = R u - R hat(u) dtheta
        J[:, 3:6] = -R @ hat(u) @ so3_right_jacobian(self._vars[3:6])
        return J

    # --------------------------------------------------------------- helpers

    def set_position(self, pos: np.ndarray) -> None:
        self._vars[:3] = np.asarray(pos, dtype=float).reshape(3)

    def set_axis(self, direction: np.ndarray, axis: str = "x") -> None:
        """Rotate the body so that its ``axis`` points along ``direction``.

        Uses the minimal single-axis rotation, which keeps an in-plane
        direction mapped to an in-plane rotation vector.
        """
        u = _AXIS_VECTORS[_check_axis(axis)]
        direction = np.asarray(direction, dtype=float).reshape(3)
        if axis == "x":
            self._vars[3:6] = rotvec_aligning(direction)
            return
        # Want R u = d.  Build it directly: R = [d, w, u x d] with
        # w = (u x d) x d, then convert the matrix to a rotation vector.
        u = u / np.linalg.norm(u)
        d = direction / np.linalg.norm(direction)
        w = np.cross(np.cross(u, d), d)
        R = np.column_stack([d, w, np.cross(u, d)])
        self._vars[3:6] = so3_log(R)

    def place_between(
        self, pa: np.ndarray, pb: np.ndarray, *, scale_shape: bool = True
    ) -> None:
        """Put the body so that its ``a``/``b`` points sit at ``pa``/``pb``.

        Sets the position to the midpoint of ``pa`` and ``pb`` and points
        the local x axis at ``pb``.  With ``scale_shape`` the shape
        variables are also set to match ``|pb - pa|``.
        """
        pa = np.asarray(pa, dtype=float).reshape(3)
        pb = np.asarray(pb, dtype=float).reshape(3)
        d = pb - pa
        length = float(np.linalg.norm(d))
        if length < 1e-12:
            raise ValueError(f"{self.name}: degenerate placement, pa == pb")
        self.set_position(0.5 * (pa + pb))
        self.set_axis(d / length, "x")
        if scale_shape and self.n_shape:
            self._vars[6:] = length

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"


def _check_axis(axis: str) -> str:
    if axis not in _AXIS_VECTORS:
        raise ValueError(f"unknown axis {axis!r}, expected one of {sorted(_AXIS_VECTORS)}")
    return axis


class World:
    """A fixed reference frame: zero variables, usable as a constraint partner.

    Named fixed points let joints be written against ground features, e.g.
    ``world.add_point("pivot", (3, 0, 0))``.
    """

    n_vars = 0
    n_shape = 0
    shape_names: tuple[str, ...] = ()
    n_dof = 0
    offset = 0
    global_slice = slice(0, 0)

    def __init__(self, name: str = "world") -> None:
        self.name = name
        self._points = {"origin": np.zeros(3)}

    def add_point(self, name: str, pos: np.ndarray) -> "World":
        self._points[name] = np.asarray(pos, dtype=float).reshape(3).copy()
        return self

    def vars(self) -> np.ndarray:
        return np.zeros(0)

    def set_vars(self, v: np.ndarray) -> None:
        if np.asarray(v).size:
            raise ValueError("World has no variables")

    def point(self, name: str) -> np.ndarray:
        if name not in self._points:
            raise KeyError(f"World {self.name!r} has no point {name!r}; "
                           f"available: {sorted(self._points)}")
        return self._points[name].copy()

    def point_jac(self, name: str) -> np.ndarray:
        self.point(name)
        return np.zeros((3, 0))

    def axis(self, axis: str = "z") -> np.ndarray:
        return AXIS_VECTORS[_check_axis(axis)].copy()

    def axis_jac(self, axis: str = "z") -> np.ndarray:
        return np.zeros((3, 0))

    @property
    def rotvec(self) -> np.ndarray:
        """A world frame cannot be perturbed, so this is fixed at zero."""
        return np.zeros(3)

    @property
    def rot(self) -> np.ndarray:
        return np.eye(3)

    def __repr__(self) -> str:
        return f"World({self.name!r})"
