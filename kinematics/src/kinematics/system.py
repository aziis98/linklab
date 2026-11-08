"""The :class:`Mechanism` container: assembly, degree-of-freedom counting and
instantaneous free-motion analysis.

A mechanism is a flat variable vector plus a stack of constraint residuals.
Everything is dense and explicit here because the sizes involved (tens to
hundreds of variables) are small enough that clarity beats sparsity.

The two results you will use most are :meth:`Mechanism.dof` and
:meth:`Mechanism.tangent_basis`.  Both go through a single SVD, so both
report the *rank* of the constraint Jacobian rather than its row count.  That
is what makes them robust to redundant constraints, which real mechanisms
(and every planar loop) have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
from scipy.linalg import null_space
from scipy.optimize import least_squares

from .constraints import Constraint
from .entity import BaseEntity, Entity, World

__all__ = ["Mechanism", "Solution", "Mobility"]


@dataclass
class Mobility:
    """The local mobility of an assembly.

    Attributes
    ----------
    n_vars, n_eq, rank
        Raw sizes and the numerical rank of the constraint Jacobian.
    dof
        ``n_vars - rank``: genuine internal degrees of freedom.
    redundant_eq
        ``n_eq - rank``: surplus equations.  Non-zero means the constraints
        are over-determined; the assembly is still solvable as long as the
        duplicate rows are consistent, but there is no unique Jacobian-based
        redundancy decomposition.
    over_constrained
        ``True`` when ``n_eq > n_vars + dof`` in a way that cannot be
        explained by rank alone, i.e. the system needs more equations than
        it has unknown directions.
    singular_values
        Singular values of the Jacobian, largest first.
    """

    n_vars: int
    n_eq: int
    rank: int
    dof: int
    redundant_eq: int
    singular_values: np.ndarray = field(repr=False)

    @property
    def over_constrained(self) -> bool:
        return self.n_eq > self.n_vars

    def __str__(self) -> str:
        lines = [
            f"variables      {self.n_vars:5d}",
            f"equations      {self.n_eq:5d}",
            f"jacobian rank  {self.rank:5d}",
            f"degrees of freedom {self.dof:3d}",
            f"redundant equations {self.redundant_eq:3d}",
        ]
        if self.n_vars:
            lines.append(
                f"smallest/largest singular value  "
                f"{_fmt_ratio(self.singular_values)}"
            )
        return "\n".join(lines)


@dataclass
class Solution:
    """Result of a solve, plus the mobility measured at the solution."""

    x: np.ndarray
    residual: np.ndarray
    mobility: Mobility
    success: bool
    cost: float
    optimality: float
    n_iter: int = 0
    message: str = ""

    @property
    def residual_norm(self) -> float:
        return float(np.linalg.norm(self.residual))

    def entity_vars(self, entity: BaseEntity) -> np.ndarray:
        """The slice of ``x`` belonging to ``entity``."""
        return self.x[entity.global_slice]


def _fmt_ratio(sv: np.ndarray) -> str:
    if sv.size == 0:
        return "n/a"
    lo, hi = float(sv[-1]), float(sv[0])
    if hi < 1e-300:
        return "n/a"
    return f"{lo:.3e} / {hi:.3e} = {lo / hi:.3e}"


class Mechanism:
    """A set of entities plus the constraints that locate them relative to
    one another.

    Entities are given contiguous, non-overlapping variable blocks in the
    order they are added.  :class:`~kinematics.entity.World` instances are
    recognised and attached to constraints without taking a block.
    """

    def __init__(self, name: str = "mechanism") -> None:
        self.name = name
        self._entities: list[BaseEntity] = []
        self._worlds: list[World] = []
        self._constraints: list[Constraint] = []
        self._dirty = True
        self._n_vars = 0
        self._n_eq = 0

    # ------------------------------------------------------------- assembly

    def add(self, *items: Entity | Constraint) -> "Mechanism":
        """Add entities and/or constraints, in any order, and return self.

        Dispatch is by interface rather than by nominal type: anything with
        ``vars`` and ``point`` is an entity, anything with ``residual`` and
        ``jac`` is a constraint.  A :class:`~kinematics.entity.World` is
        filed separately since it owns no variables.
        """
        for item in items:
            if isinstance(item, World):
                self._worlds.append(item)
            elif _is_constraint(item):
                self._constraints.append(item)  # type: ignore[arg-type]
            elif _is_entity(item):
                self._entities.append(item)  # type: ignore[arg-type]
            else:
                raise TypeError(
                    f"cannot add {type(item).__name__}: not an entity or a constraint"
                )
        self._invalidate()
        # Rebind eagerly: entity offsets are cheap to recompute and having them
        # valid immediately avoids a class of confusing stale-slice bugs.
        self._sync()
        return self

    def add_entity(self, *entities: BaseEntity) -> "Mechanism":
        return self.add(*entities)

    def add_constraint(self, *constraints: Constraint) -> "Mechanism":
        return self.add(*constraints)

    def remove_constraint(self, constraint: Constraint) -> "Mechanism":
        self._constraints.remove(constraint)
        self._invalidate()
        return self

    @property
    def entities(self) -> tuple[BaseEntity, ...]:
        return tuple(self._entities)

    @property
    def worlds(self) -> tuple[World, ...]:
        return tuple(self._worlds)

    @property
    def constraints(self) -> tuple[Constraint, ...]:
        return tuple(self._constraints)

    def entity(self, name: str) -> BaseEntity:
        for e in self._entities:
            if e.name == name:
                return e
        raise KeyError(f"no entity named {name!r}")

    def world(self, name: str = "world") -> World:
        for w in self._worlds:
            if w.name == name:
                return w
        raise KeyError(f"no world named {name!r}")

    def _invalidate(self) -> None:
        self._dirty = True

    def _sync(self) -> None:
        if not self._dirty:
            return
        offset = 0
        for e in self._entities:
            e._bind(offset)
            offset += e.n_vars
        self._n_vars = offset
        self._n_eq = sum(c.n_eq for c in self._constraints)
        self._dirty = False

    @property
    def n_vars(self) -> int:
        self._sync()
        return self._n_vars

    @property
    def n_eq(self) -> int:
        self._sync()
        return self._n_eq

    # ------------------------------------------------------------- residuals

    def vars(self) -> np.ndarray:
        self._sync()
        if not self._entities:
            return np.zeros(0)
        return np.concatenate([e.vars() for e in self._entities])

    def set_vars(self, x: np.ndarray) -> None:
        self._sync()
        x = np.asarray(x, dtype=float).reshape(-1)
        if x.size != self._n_vars:
            raise ValueError(f"expected {self._n_vars} variables, got {x.size}")
        for e in self._entities:
            e.set_vars(x[e.global_slice])

    def residual(self, x: np.ndarray | None = None) -> np.ndarray:
        self._sync()
        if x is not None:
            self.set_vars(x)
        if not self._constraints:
            return np.zeros(0)
        return np.concatenate([np.atleast_1d(c.residual()) for c in self._constraints])

    @property
    def residual_norm(self) -> float:
        """Euclidean norm of the assembled constraint residual."""
        return float(np.linalg.norm(self.residual()))

    def jac(self, x: np.ndarray | None = None) -> np.ndarray:
        self._sync()
        if x is not None:
            self.set_vars(x)
        J = np.zeros((self._n_eq, self._n_vars))
        row = 0
        for c in self._constraints:
            block = np.atleast_2d(c.jac(self._n_vars))
            if block.shape != (c.n_eq, self._n_vars):
                raise ValueError(
                    f"{c!r} returned jac shape {block.shape}, "
                    f"expected {(c.n_eq, self._n_vars)}"
                )
            J[row : row + c.n_eq] = block
            row += c.n_eq
        return J

    # --------------------------------------------------------------- mobility

    def mobility(self, x: np.ndarray | None = None, rcond: float = 1e-9) -> Mobility:
        """Degree-of-freedom counts at ``x`` (default: the current assembly).

        The degree of freedom is ``n_vars - rank(J)`` and the redundancy is
        ``n_eq - rank(J)``.  Both are SVD based, so a duplicated or linearly
        dependent constraint is absorbed into the rank instead of
        incorrectly zeroing the mobility.
        """
        self._sync()
        J = self.jac(x)
        rank, sv = _rank(J, rcond)
        return Mobility(
            n_vars=self._n_vars,
            n_eq=self._n_eq,
            rank=rank,
            dof=self._n_vars - rank,
            redundant_eq=self._n_eq - rank,
            singular_values=sv,
        )

    def dof(self, x: np.ndarray | None = None, rcond: float = 1e-9) -> int:
        return self.mobility(x, rcond).dof

    def tangent_basis(
        self,
        x: np.ndarray | None = None,
        *,
        rcond: float = 1e-9,
        subset: Iterable[int] | None = None,
    ) -> np.ndarray:
        """Basis of instantaneous free motions, as columns in variable space.

        Returns a ``(n_vars, dof)`` array whose columns span the null space
        of the constraint Jacobian.  Moving the mechanism by
        ``x + eps * T`` for small ``eps`` is therefore a first-order-feasible
        displacement; the second-order error is what the null space does not
        capture.

        Parameters
        ----------
        subset
            Restrict the search to these variable indices.  Useful for
            dropping shape variables and symmetry spins, which are real null
            directions of the constraint system but not interesting
            mechanisms: for a :class:`~kinematics.entities.Rod` the spin
            about its own axis is one of them.
        """
        self._sync()
        J = self.jac(x)
        if subset is None:
            return null_space(J, rcond=rcond)
        idx = np.asarray(list(subset), dtype=int)
        if idx.size == 0:
            return np.zeros((self._n_vars, 0))
        Z = null_space(J[np.ix_(idx, np.arange(J.shape[1]))], rcond=rcond)
        out = np.zeros((self._n_vars, Z.shape[1]))
        out[idx, :] = Z
        return out

    def tangent_norm(
        self, x: np.ndarray | None = None, *, rcond: float = 1e-9
    ) -> float:
        """Smallest singular value of the Jacobian: conditioning indicator.

        As this goes to zero a free motion becomes infinitesimally cheap
        while the others do not, which is how a mechanism approaches a
        singular configuration (a dead centre, a fold, a lock-up).  It is
        the quantity to watch when deciding whether a null direction is a
        genuine motion or a numerical artefact.
        """
        return _rank(self.jac(x), rcond)[1][-1] if self._n_eq else 0.0

    # ----------------------------------------------------------------- solve

    def solve(
        self,
        guess: np.ndarray | None = None,
        *,
        method: str = "trf",
        xtol: float = 1e-12,
        ftol: float = 1e-12,
        gtol: float = 1e-12,
        max_nfev: int = 2000,
    ) -> Solution:
        """Find an assembly satisfying every constraint.

        Solves ``minimise ||residual(x)||^2`` from ``guess`` (default: the
        current assembly) with the analytic Jacobian, and reports the
        mobility measured at the solution.
        """
        self._sync()
        x0 = self.vars() if guess is None else np.asarray(guess, float).reshape(-1)
        if self._n_eq == 0:
            sol = Solution(
                x=self.vars(),
                residual=np.zeros(0),
                mobility=self.mobility(),
                success=True,
                cost=0.0,
                optimality=0.0,
                message="no constraints",
            )
            return sol
        res = least_squares(
            self.residual,
            x0,
            jac=self.jac,
            method=method,
            xtol=xtol,
            ftol=ftol,
            gtol=gtol,
            max_nfev=max_nfev,
        )
        self.set_vars(res.x)
        r = self.residual()
        return Solution(
            x=np.array(res.x),
            residual=r,
            mobility=self.mobility(),
            success=bool(res.success) and float(np.linalg.norm(r)) < 1e-8,
            cost=float(res.cost),
            optimality=float(res.optimality),
            n_iter=int(res.nfev),
            message=str(res.message),
        )

    def solve_guesses(
        self, guesses: Sequence[np.ndarray], **kwargs
    ) -> list[Solution]:
        """Try each starting assembly in turn, keep the ones that converge.

        The first seed usually suffices, but a spatial loop such as a four
        bar has two assembly branches, so seeding several places is the
        cheap way to reach both.
        """
        out: list[Solution] = []
        for g in guesses:
            g = np.asarray(g, dtype=float).reshape(-1)
            if g.size != self.n_vars:
                raise ValueError(f"guess has {g.size} variables, expected {self.n_vars}")
            s = self.solve(g, **kwargs)
            if s.success:
                out.append(s)
        return out

    def __repr__(self) -> str:
        return (
            f"Mechanism({self.name!r}, {len(self._entities)} entities, "
            f"{len(self._constraints)} constraints)"
        )


def _is_entity(item: object) -> bool:
    return all(hasattr(item, a) for a in ("vars", "set_vars", "point", "point_jac", "offset"))


def _is_constraint(item: object) -> bool:
    return all(hasattr(item, a) for a in ("residual", "jac", "n_eq"))


def _rank(J: np.ndarray, rcond: float) -> tuple[int, np.ndarray]:
    if J.size == 0:
        return 0, np.zeros(0)
    sv = np.linalg.svd(J, compute_uv=False)
    tol = rcond * float(sv[0]) if sv.size else 0.0
    return int(np.count_nonzero(sv > tol)), sv
