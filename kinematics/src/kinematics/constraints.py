"""Assembly constraints.

Every constraint implements the same two-method protocol:

* :meth:`Constraint.residual` -> a 1-D array of ``n_eq`` error terms
* :meth:`Constraint.jac` -> the ``(n_eq, n_total_vars)`` Jacobian

The Jacobian is handed the mechanism's total variable count so it can
scatter local derivatives into the right columns without knowing anything
about the mechanism itself.

Implemented
-----------
:class:`Fixed`          6 eq, welds two bodies into a given relative pose
:class:`PointConstraint` 3 eq, makes two material points coincide
:class:`Planar`         1 eq (or 3), keeps material points in a plane
:class:`AlignAxis`      2 eq, aims a body axis at a fixed direction
:class:`Value`          1 eq, pins a single scalar variable
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from .entity import AXIS_VECTORS, BaseEntity, World, _check_axis
from .linalg import (
    SE3,
    perp_basis,
    so3_left_jacobian_inv,
    so3_log,
    so3_right_jacobian,
)

__all__ = [
    "Constraint",
    "Fixed",
    "PointConstraint",
    "Planar",
    "AlignAxis",
    "Value",
    "Distance",
]


@runtime_checkable
class Constraint(Protocol):
    """An assembly condition on a set of entities."""

    n_eq: int
    entities: tuple[BaseEntity | World, ...]

    def residual(self) -> np.ndarray: ...

    def jac(self, total: int) -> np.ndarray: ...


class _Base:
    """Shared plumbing: collect entities, size the residual, build the Jacobian."""

    def __init__(self, *entities: BaseEntity | World) -> None:
        for e in entities:
            if not (hasattr(e, "point") and hasattr(e, "offset")):
                raise TypeError(f"{type(e).__name__} is not an entity")
        self.entities = tuple(entities)

    @property
    def n_eq(self) -> int:  # pragma: no cover - overridden
        raise NotImplementedError

    def residual(self) -> np.ndarray:  # pragma: no cover - overridden
        raise NotImplementedError

    def jac(self, total: int) -> np.ndarray:  # pragma: no cover - overridden
        raise NotImplementedError

    def _blank(self, total: int) -> np.ndarray:
        return np.zeros((self.n_eq, total))

    def _scatter(self, J: np.ndarray, entity: BaseEntity | World, block: np.ndarray) -> None:
        """Place a local ``(rows, entity.n_vars)`` block into global columns."""
        sl = entity.global_slice
        if block.shape[1] == 0:
            return
        J[:, sl] += block

    def __repr__(self) -> str:
        names = ", ".join(e.name for e in self.entities)
        return f"{type(self).__name__}({names})"


class Fixed(_Base):
    """Holds the relative pose of two entities.

    Six equations.  The residual is the SE(3) logarithm of the error, so it
    is the first-order (and, for small errors, first-order-accurate) measure
    of the pose mismatch.  The derivative uses the left inverse Jacobian of
    the relative rotation, which is the standard "right perturbation"
    convention:

    ``R_a -> R_a exp(dtheta)``  and  ``R_b -> R_b exp(dtheta)``
    gives  ``d(log(R_a^T R_b)) = -Jl^{-1} dtheta_a + Jl^{-1} dtheta_b``

    With ``target=None`` this simply welds the two bodies into the same
    pose.
    """

    def __init__(
        self,
        a: BaseEntity | World,
        b: BaseEntity | World,
        target: SE3 | None = None,
    ) -> None:
        super().__init__(a, b)
        self.a = a
        self.b = b
        self.target = target if target is not None else SE3.identity()

    @property
    def n_eq(self) -> int:
        return 6

    def residual(self) -> np.ndarray:
        a, b = self.a, self.b
        da = a.point("origin")
        db = b.point("origin")
        ra, rb = a.rot, b.rot
        # The generic BaseEntity does not expose a rotation for World, but
        # World.rot is defined there too, so this is uniform.
        phi = so3_log(ra.T @ rb)
        phi_t = so3_log(self.target.rot)
        return np.concatenate([db - da - self.target.pos, phi - phi_t])

    def jac(self, total: int) -> np.ndarray:
        J = self._blank(total)
        I = np.eye(3)
        for entity, sign in ((self.a, -1.0), (self.b, 1.0)):
            if not isinstance(entity, BaseEntity):
                continue  # a World contributes no columns
            block = np.zeros((3, entity.n_vars))
            block[:3, :3] = sign * I
            self._scatter(J[0:3], entity, block)
        phi = so3_log(self.a.rot.T @ self.b.rot)
        jl_inv = so3_left_jacobian_inv(phi)
        for entity, sign in ((self.a, -1.0), (self.b, 1.0)):
            if not isinstance(entity, BaseEntity):
                continue
            block = np.zeros((3, entity.n_vars))
            block[:, 3:6] = sign * jl_inv @ so3_right_jacobian(entity.rotvec)
            self._scatter(J[3:6], entity, block)
        return J


class PointConstraint(_Base):
    """Makes material point ``name_a`` of ``a` coincide with ``name_b`` of ``b``.

    Three equations, zero residual when
    ``a.point(name_a) == b.point(name_b)``.  Either entity may be a
    :class:`~kinematics.entity.World`, in which case the point is a fixed
    ground feature and the constraint simply pins the other body's point
    there.
    """

    def __init__(
        self,
        a: BaseEntity | World,
        name_a: str,
        b: BaseEntity | World,
        name_b: str,
    ) -> None:
        super().__init__(a, b)
        self.a, self.name_a = a, name_a
        self.b, self.name_b = b, name_b

    @property
    def n_eq(self) -> int:
        return 3

    def residual(self) -> np.ndarray:
        return self.a.point(self.name_a) - self.b.point(self.name_b)

    def jac(self, total: int) -> np.ndarray:
        J = self._blank(total)
        ja = self.a.point_jac(self.name_a)
        jb = self.b.point_jac(self.name_b)
        if ja.shape[1]:
            sl = self.a.global_slice
            J[0:3, sl] += ja
        if jb.shape[1]:
            sl = self.b.global_slice
            J[0:3, sl] -= jb
        return J


class Distance(_Base):
    """Holds the distance between two material points at a given value.

    One equation, zero residual at the correct separation.  Handy as an
    explicit link-length constraint when you would rather not rely on the
    length shape variable.
    """

    def __init__(
        self,
        a: BaseEntity | World,
        name_a: str,
        b: BaseEntity | World,
        name_b: str,
        value: float,
    ) -> None:
        super().__init__(a, b)
        self.a, self.name_a = a, name_a
        self.b, self.name_b = b, name_b
        self.value = float(value)
        if self.value <= 0.0:
            raise ValueError(f"{a.name}/{b.name}: distance must be positive")

    @property
    def n_eq(self) -> int:
        return 1

    def residual(self) -> np.ndarray:
        d = self.a.point(self.name_a) - self.b.point(self.name_b)
        return np.array([np.linalg.norm(d) - self.value])

    def jac(self, total: int) -> np.ndarray:
        J = self._blank(total)
        d = self.a.point(self.name_a) - self.b.point(self.name_b)
        n = np.linalg.norm(d)
        if n < 1e-12:
            # At coincident points the distance function has a cusp; the
            # derivative there is undefined, so contribute nothing.
            return J
        u = d / n
        for entity, name, sign in (
            (self.a, self.name_a, 1.0),
            (self.b, self.name_b, -1.0),
        ):
            block = entity.point_jac(name)
            if block.shape[1] == 0:
                continue
            sl = entity.global_slice
            J[0, sl] += sign * (u @ block)
        return J


class Planar(_Base):
    """Keeps material points of an entity in a fixed plane.

    With ``orientation=False`` (the default) this is a single equation per
    named point: the signed distance from the plane.  With
    ``orientation=True`` two further equations lock the body's z axis to
    the plane normal, bringing the total to three independent equations
    per point.

    Note that adding planarity to *every* link of a closed loop is normally
    over-specified: the ground link already fixes the plane, so some of the
    rows will be linearly dependent.  :meth:`~kinematics.system.Mechanism.dof`
    uses an SVD rank so the reported degree of freedom stays correct, and
    ``Mechanism.redundancy`` will report the surplus.
    """

    def __init__(
        self,
        entity: BaseEntity | World,
        name: str,
        origin: np.ndarray = (0.0, 0.0, 0.0),
        normal: np.ndarray = (0.0, 0.0, 1.0),
        *,
        orientation: bool = False,
        body_axis: str = "z",
    ) -> None:
        super().__init__(entity)
        self.entity = entity
        self.name = name
        self.origin = np.asarray(origin, dtype=float).reshape(3)
        n = np.asarray(normal, dtype=float).reshape(3)
        norm = np.linalg.norm(n)
        if norm < 1e-12:
            raise ValueError("plane normal must be non-zero")
        self.normal = n / norm
        self.orientation = bool(orientation)
        self.body_axis = _check_axis(body_axis)
        # Build a basis in the plane once, for the orientation rows.
        self._b1, self._b2 = perp_basis(self.normal)

    @property
    def n_eq(self) -> int:
        return 3 if self.orientation else 1

    def residual(self) -> np.ndarray:
        x = self.entity.point(self.name)
        out = [float(self.normal @ (x - self.origin))]
        if self.orientation:
            u = self.entity.axis(self.body_axis)
            out += [float(self._b1 @ u), float(self._b2 @ u)]
        return np.array(out)

    def jac(self, total: int) -> np.ndarray:
        J = self._blank(total)
        block = self.entity.point_jac(self.name)
        if block.shape[1] == 0:
            return J
        sl = self.entity.global_slice
        J[0, sl] += self.normal @ block
        if self.orientation:
            J[1, sl] += self._b1 @ self.entity.axis_jac(self.body_axis)
            J[2, sl] += self._b2 @ self.entity.axis_jac(self.body_axis)
        return J


class AlignAxis(_Base):
    """Aims one body axis at a fixed world direction: two equations.

    This is a directional constraint, not an orientation lock: the body's
    rotation about its own aimed axis stays free.  Two independent
    equations are obtained by projecting the aim error onto a basis
    orthogonal to the target, so the rank is exact rather than relying on
    one row of the cross product being identically zero.
    """

    def __init__(
        self,
        entity: BaseEntity,
        direction: np.ndarray,
        axis: str = "x",
    ) -> None:
        super().__init__(entity)
        self.entity = entity
        self.axis = _check_axis(axis)
        self.direction = _unit(direction, f"{entity.name} align direction")
        self._b1, self._b2 = perp_basis(self.direction)

    @property
    def n_eq(self) -> int:
        return 2

    def residual(self) -> np.ndarray:
        u = self.entity.axis(self.axis)
        return np.array([float(self._b1 @ u), float(self._b2 @ u)])

    def jac(self, total: int) -> np.ndarray:
        J = self._blank(total)
        block = self.entity.axis_jac(self.axis)
        if block.shape[1] == 0:
            return J
        sl = self.entity.global_slice
        J[0, sl] += self._b1 @ block
        J[1, sl] += self._b2 @ block
        return J

    def set_direction(self, direction: np.ndarray) -> None:
        """Retarget, e.g. while sweeping a driving angle."""
        self.direction = _unit(direction, "align direction")
        self._b1, self._b2 = perp_basis(self.direction)


class Value(_Base):
    """Pins one scalar variable of an entity to a number: one equation.

    Use it to hold a design parameter such as a rod length while leaving
    the rest of the mechanism free.
    """

    def __init__(self, entity: BaseEntity, var: str | int, target: float) -> None:
        super().__init__(entity)
        self.entity = entity
        self.var = var
        self.index = entity.index(var)
        self.target = float(target)

    @property
    def n_eq(self) -> int:
        return 1

    def residual(self) -> np.ndarray:
        return np.array([self.entity.get_var(self.index) - self.target])

    def jac(self, total: int) -> np.ndarray:
        J = self._blank(total)
        J[0, self.entity.offset + self.index] = 1.0
        return J


def _unit(v: np.ndarray, what: str) -> np.ndarray:
    v = np.asarray(v, dtype=float).reshape(3)
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError(f"{what} must be non-zero")
    return v / n
