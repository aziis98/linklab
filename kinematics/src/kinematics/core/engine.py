"""Constraint embeddings, analytic Jacobians and conservative local continuation."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import null_space
from scipy.optimize import least_squares

from .model import Scene

FloatArray = NDArray[np.float64]
Configuration = dict[str, list[float]]


class MobilityResult(TypedDict):
    first_order: int
    second_order: str
    linear_compatible_dimension: int
    linear_compatible_tangents: list[list[list[float]]]
    quadratic_forms: list[list[list[float]]]
    tangents: list[list[list[float]]]
    rank: int
    residual: float


class DragResult(TypedDict):
    configuration: Configuration
    mobility: MobilityResult
    reachable: bool


class Engine:
    def __init__(self, scene: Scene):
        scene.resolve_dimension()
        self.scene = scene
        self.d = scene.dimension
        self.keys = [f"{o.id}:{name}" for o in scene.objects for name in o.points]
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.initial = np.array(
            [
                [float(v) for v in p[: self.d]]
                for o in scene.objects
                for p in o.points.values()
            ]
        )
        if not len(self.initial):
            raise ValueError("scene must contain at least one rigid object")
        if not np.all(np.isfinite(self.initial)):
            raise ValueError("coordinates must be finite")
        self.scale = max(
            float(np.ptp(self.initial, axis=0).max()) if len(self.initial) else 1, 1e-6
        )
        self.pins = {}
        self.equal = []
        self.lengths = []
        self.planes = []
        self.parallels = []
        self.fixed_equations = []
        for o in scene.objects:
            ids = [self.index[f"{o.id}:{n}"] for n in o.points]
            for i, j in combinations(ids, 2):
                self.lengths.append(
                    (i, j, float(np.sum((self.initial[i] - self.initial[j]) ** 2)))
                )
            if o.fixed:
                for i in ids:
                    self.pins[i] = self.initial[i].copy()
        for c in scene.constraints:
            i = self.index[c.a]
            if c.kind == "pin":
                if i in self.pins:
                    self.fixed_equations.append((i, self.pins[i].copy()))
                self.pins[i] = np.array([float(v) for v in c.value[: self.d]])
            elif c.kind == "coincident":
                self.equal.append((i, self.index[c.b]))
            elif c.kind == "distance":
                self.lengths.append((i, self.index[c.b], float(c.value)))
            elif c.kind == "parallel":
                self.parallels.append(
                    tuple(self.index[k] for k in (c.a, c.b, *c.value))
                )
            elif c.kind == "plane":
                p, n = np.array(c.value[0], float), np.array(c.value[1], float)
                if self.d == 2:
                    if np.linalg.norm(n[:2]) == 0:
                        if abs(p @ n) > 1e-12:
                            raise ValueError("plane excludes the scene plane")
                        continue
                    p = p[:2] + n[:2] * p[2] * n[2] / np.dot(n[:2], n[:2])
                    n = n[:2]
                self.planes.append((i, p, n))
        self.current = self.initial.copy()
        # Contradictory fixed positions are retained as equations, never silently merged.
        for o in scene.objects:
            if o.fixed:
                for n in o.points:
                    i = self.index[f"{o.id}:{n}"]
                    self.fixed_equations.append((i, self.initial[i]))

    def residual(self, flat: FloatArray) -> FloatArray:
        x = np.asarray(flat).reshape(-1, self.d)
        s = self.scale
        rows = [
            (np.dot(x[i] - x[j], x[i] - x[j]) - l) / (2 * s * s)
            for i, j, l in self.lengths
        ]
        for i, j in self.equal:
            rows.extend((x[i] - x[j]) / s)
        for i, p in list(self.pins.items()) + self.fixed_equations:
            rows.extend((x[i] - p) / s)
        for i, p, n in self.planes:
            rows.append(np.dot(x[i] - p, n) / (s * np.linalg.norm(n)))
        for i, j, k, l in self.parallels:
            a = x[j] - x[i]
            b = x[l] - x[k]
            rows.extend(
                np.atleast_1d(np.cross(a, b) / s**2)
            ) if self.d == 3 else rows.append((a[0] * b[1] - a[1] * b[0]) / s**2)
        return np.array(rows)

    def jac(self, flat: FloatArray) -> FloatArray:
        x = np.asarray(flat).reshape(-1, self.d)
        rows = []
        s = self.scale

        def blank():
            return np.zeros_like(x)

        for i, j, _ in self.lengths:
            r = blank()
            r[i] = (x[i] - x[j]) / s**2
            r[j] = -r[i]
            rows.append(r.ravel())
        for i, j in self.equal:
            for a in range(self.d):
                r = blank()
                r[i, a] = 1 / s
                r[j, a] = -1 / s
                rows.append(r.ravel())
        for i, _ in list(self.pins.items()) + self.fixed_equations:
            for a in range(self.d):
                r = blank()
                r[i, a] = 1 / s
                rows.append(r.ravel())
        for i, _, n in self.planes:
            r = blank()
            r[i] = n / (s * np.linalg.norm(n))
            rows.append(r.ravel())
        for i, j, k, l in self.parallels:
            a = x[j] - x[i]
            b = x[l] - x[k]
            block = np.zeros((3 if self.d == 3 else 1, *x.shape))
            for axis in range(self.d):
                unit = np.eye(self.d)[axis]
                da = (
                    np.cross(unit, b)
                    if self.d == 3
                    else unit[0] * b[1] - unit[1] * b[0]
                )
                db = (
                    np.cross(a, unit)
                    if self.d == 3
                    else a[0] * unit[1] - a[1] * unit[0]
                )
                block[:, j, axis] += da
                block[:, i, axis] -= da
                block[:, l, axis] += db
                block[:, k, axis] -= db
            rows.extend(block.reshape(-1, x.size) / s**2)
        return np.array(rows).reshape(len(rows), x.size)

    def error(self, x: FloatArray) -> float:
        r = self.residual(x.ravel())
        residual = float(np.max(np.abs(r))) if r.size else 0.0
        for i, j, squared_length in self.lengths:
            residual = max(
                residual,
                abs(np.linalg.norm(x[i] - x[j]) - np.sqrt(squared_length)) / self.scale,
            )
        return residual

    def project(self, guess: FloatArray) -> FloatArray:
        if not len(self.residual(guess.ravel())):
            return guess.copy()
        sol = least_squares(
            self.residual,
            guess.ravel(),
            jac=self.jac,
            xtol=1e-13,
            ftol=1e-13,
            gtol=1e-13,
            max_nfev=300,
        )
        x = sol.x.reshape(-1, self.d)
        if self.error(x) > 1e-9:
            raise ValueError(
                f"assembly did not converge; normalized residual {self.error(x):.3g}"
            )
        return x

    def mobility(self, x: FloatArray | None = None) -> MobilityResult:
        x = self.current if x is None else x
        J = self.jac(x.ravel())
        T = null_space(J, rcond=1e-8)
        U = null_space(J.T, rcond=1e-8)
        forms = []
        for u in U.T:
            H = np.zeros((T.shape[1], T.shape[1]))
            for k, (i, j, _) in enumerate(self.lengths):
                D = T[i * self.d : (i + 1) * self.d] - T[j * self.d : (j + 1) * self.d]
                H += u[k] * (D.T @ D) / self.scale**2
            offset = len(self.residual(x.ravel())) - (3 if self.d == 3 else 1) * len(
                self.parallels
            )
            for pi, (i, j, k, l) in enumerate(self.parallels):
                A = T[j * self.d : (j + 1) * self.d] - T[i * self.d : (i + 1) * self.d]
                B = T[l * self.d : (l + 1) * self.d] - T[k * self.d : (k + 1) * self.d]
                for r in range(T.shape[1]):
                    for c in range(T.shape[1]):
                        w = (
                            (np.cross(A[:, r], B[:, c]) + np.cross(A[:, c], B[:, r]))
                            if self.d == 3
                            else A[0, r] * B[1, c]
                            - A[1, r] * B[0, c]
                            + A[0, c] * B[1, r]
                            - A[1, c] * B[0, r]
                        )
                        H[r, c] += (
                            np.dot(
                                u[
                                    offset + pi * (3 if self.d == 3 else 1) : offset
                                    + (pi + 1) * (3 if self.d == 3 else 1)
                                ],
                                np.atleast_1d(w),
                            )
                            / self.scale**2
                        )
            forms.append(H)
        # Semidefinite obstruction forms force velocity into their kernels.
        # This removes partial locks without blocking independent mobile objects.
        restrictions = []
        for H in forms:
            if H.size:
                ev = np.linalg.eigvalsh(H)
                if (np.min(ev) >= -1e-8 and np.max(ev) > 1e-8) or (
                    np.max(ev) <= 1e-8 and np.min(ev) < -1e-8
                ):
                    restrictions.append(H)
        compatible = (
            T @ null_space(np.vstack(restrictions), rcond=1e-8) if restrictions else T
        )
        locked = T.shape[1] > 0 and compatible.shape[1] == 0
        nonzero = any(np.linalg.norm(H) > 1e-8 for H in forms)
        return {
            "first_order": T.shape[1],
            "second_order": "locked"
            if locked
            else "inconclusive"
            if nonzero and T.shape[1]
            else "compatible",
            "linear_compatible_dimension": compatible.shape[1],
            "linear_compatible_tangents": compatible.T.reshape(
                -1, len(x), self.d
            ).tolist()
            if compatible.shape[1]
            else [],
            "quadratic_forms": [h.tolist() for h in forms],
            "tangents": T.T.reshape(-1, len(x), self.d).tolist() if T.shape[1] else [],
            "rank": int(x.size - T.shape[1]),
            "residual": self.error(x),
        }

    def assemble(self) -> FloatArray:
        self.current = self.project(self.initial)
        return self.current

    def drag(
        self,
        keys: Sequence[str],
        targets: Sequence[Sequence[float]],
        weights: Sequence[float] | None = None,
    ) -> DragResult:
        targets = np.array(targets, float)[:, : self.d]
        ids = [self.index[k] for k in keys]
        C = (
            np.eye(len(ids))
            if weights is None
            else np.array(weights, float).reshape(1, len(ids))
        )
        objective = np.kron(C, np.eye(self.d))

        def error_to_target(x):
            return objective @ (targets - x[ids]).ravel()

        for _ in range(16):
            m = self.mobility()
            if m["second_order"] == "locked" or m["first_order"] == 0:
                break
            T = (
                np.array(m["linear_compatible_tangents"])
                .reshape(-1, self.current.size)
                .T
            )
            rows = np.array([i * self.d + a for i in ids for a in range(self.d)])
            delta = np.linalg.lstsq(
                objective @ T[rows], error_to_target(self.current), rcond=1e-8
            )[0]
            step = T @ delta
            norm = np.linalg.norm(step)
            if norm < 1e-9 * self.scale:
                break
            step *= min(1, 0.03 * self.scale / norm)
            accepted = False
            for factor in (1, 0.5, 0.25, 0.125):
                try:
                    candidate = self.project(
                        self.current + factor * step.reshape(-1, self.d)
                    )
                except ValueError:
                    continue
                if np.linalg.norm(candidate - self.current) > 2 * np.linalg.norm(step):
                    continue
                if np.linalg.norm(error_to_target(candidate)) >= np.linalg.norm(
                    error_to_target(self.current)
                ):
                    continue
                self.current = candidate
                accepted = True
                break
            if not accepted:
                break
        return {
            "configuration": self.configuration(),
            "mobility": self.mobility(),
            "reachable": bool(
                np.linalg.norm(error_to_target(self.current)) < 1e-5 * self.scale
            ),
        }

    def reassemble(
        self,
        keys: Sequence[str],
        targets: Sequence[Sequence[float]],
        weights: Sequence[float] | None = None,
    ) -> DragResult:
        """Explicit basin search near a drag target, permitting assembly-mode changes.

        This is an opt-in discontinuous operation, never a continuation step.
        Only converged feasible configurations improving the drag objective qualify.
        """
        ids = [self.index[k] for k in keys]
        target = np.array(targets, float)[:, : self.d]
        before = self.current.copy()
        adjacency = [set() for _ in before]
        for i, j, _ in self.lengths:
            adjacency[i].add(j)
            adjacency[j].add(i)
        for i, j in self.equal:
            adjacency[i].add(j)
            adjacency[j].add(i)
        for group in self.parallels:
            for i in group:
                adjacency[i].update(group)
        scope = set(ids)
        todo = list(ids)
        while todo:
            i = todo.pop()
            if i in self.pins:
                continue
            for j in adjacency[i] - scope:
                scope.add(j)
                todo.append(j)
        active = np.array(
            [i in scope and i not in self.pins for i in range(len(before))]
        )

        C = (
            np.eye(len(ids))
            if weights is None
            else np.array(weights, float).reshape(1, len(ids))
        )

        def cost(x):
            return float(np.sum((C @ (x[ids] - target)) ** 2))

        best = before
        best_cost = cost(before)
        direct = before.copy()
        direct[ids] = target
        delta = np.mean(target - before[ids], axis=0)
        translated = before + delta
        seeds = [direct, translated]
        rng = np.random.default_rng(42)
        for spread in (0.15, 0.6, 1.5):
            for _ in range(4):
                seed = direct + rng.normal(0, self.scale * spread, before.shape)
                seed[ids] = target
                seeds.append(seed)
        for seed in seeds:
            seed[~active] = before[~active]
            for i, pos in self.pins.items():
                seed[i] = pos
            try:
                candidate = self.project(seed)
            except ValueError:
                continue
            candidate[~active] = before[~active]
            if self.error(candidate) > 1e-9:
                continue
            # Do not mistake projection uncertainty near a singular root for a new assembly.
            if np.linalg.norm(candidate - before) < 1e-4 * self.scale:
                continue
            candidate_cost = cost(candidate)
            if candidate_cost < best_cost - 1e-12 * self.scale**2:
                best = candidate
                best_cost = candidate_cost
        self.current = best
        return {
            "configuration": self.configuration(),
            "mobility": self.mobility(),
            "reachable": best_cost < (1e-5 * self.scale) ** 2,
        }

    def configuration(self, x: FloatArray | None = None) -> Configuration:
        x = self.current if x is None else x
        return {
            k: [*map(float, p), *([0.0] if self.d == 2 else [])]
            for k, p in zip(self.keys, x)
        }
