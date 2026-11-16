"""Rank-aware active-set least squares for upper-bound constraints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from .engine import Engine, MobilityResult
from scipy.linalg import null_space


def _constrained_fit(
    c: NDArray[np.float64],
    target: NDArray[np.float64],
    a: NDArray[np.float64],
    bounds: NDArray[np.float64],
    active: list[int],
) -> tuple[NDArray[np.float64], list[int]]:
    n = c.shape[1]
    x = np.zeros(n)
    for _ in range(100):
        aa = a[active] if active else np.empty((0, n))
        p = (
            np.linalg.lstsq(aa, bounds[active], rcond=1e-10)[0]
            if active
            else np.zeros(n)
        )
        if active and np.max(np.abs(aa @ p - bounds[active])) > 1e-8:
            raise ValueError("Incompatible active cable bounds")
        z = null_space(aa, rcond=1e-10)
        x = p + z @ np.linalg.lstsq(c @ z, target - c @ p, rcond=1e-10)[0]
        violation = a @ x - bounds
        if violation.size and np.max(violation) > 1e-10:
            index = int(np.argmax(violation))
            if index in active:
                raise ValueError("Cable active set did not converge")
            active.append(index)
            continue
        if active:
            gradient = c.T @ (c @ x - target)
            multipliers = np.linalg.lstsq(aa.T, -gradient, rcond=1e-10)[0]
            if np.min(multipliers) < -1e-10:
                active.pop(int(np.argmin(multipliers)))
                continue
        return x, active
    raise ValueError("Cable active set exceeded iteration budget")


def constrained_fit(
    c: NDArray[np.float64],
    target: NDArray[np.float64],
    a: NDArray[np.float64],
    bounds: NDArray[np.float64],
    working_set: list[int] | None = None,
) -> NDArray[np.float64]:
    active = list(working_set) if working_set is not None else []
    active = [i for i in active if 0 <= i < len(bounds)]
    had_warm_start = bool(active)
    try:
        x, active = _constrained_fit(c, target, a, bounds, active)
    except ValueError:
        if not had_warm_start:
            raise
        x, active = _constrained_fit(c, target, a, bounds, [])
    if working_set is not None:
        working_set[:] = active
    return x


def cable_mobility(
    engine: Engine,
    x: NDArray[np.float64],
    result: MobilityResult,
    jacobian: NDArray[np.float64],
    raw_tangent: NDArray[np.float64],
) -> MobilityResult:
    _, a = engine.cable_rows(x)
    active = np.array(
        [
            index
            for index, (i, j, length) in enumerate(engine.cables)
            if (np.sqrt(length) - np.linalg.norm(x[i] - x[j])) / engine.scale <= 1e-8
        ],
        dtype=int,
    )
    t = np.array(result["linear_compatible_tangents"]).reshape(-1, x.size).T
    result["motion_kind"] = "cone"
    result["active_cables"] = active.tolist()
    if not len(active) or not t.shape[1]:
        return result
    aa = a[active]
    # Eliminate equality multipliers before the sign-constrained stress search.
    reduced = aa @ raw_tangent
    k = len(active)
    matrix = np.vstack((reduced.T, np.ones(k)))
    rhs = np.r_[np.zeros(raw_tangent.shape[1]), 1.0]
    p = np.linalg.lstsq(matrix, rhs, rcond=1e-10)[0]
    if np.linalg.norm(matrix @ p - rhs) > 1e-8:
        return result
    z = null_space(matrix, rcond=1e-10)
    try:
        mu = p + z @ constrained_fit(z, -p, -z, p)
    except ValueError:
        return result
    if np.min(mu) < -1e-8 or np.linalg.norm(matrix @ mu - rhs) > 1e-8:
        return result
    lam = np.linalg.lstsq(jacobian.T, -aa.T @ mu, rcond=1e-10)[0]
    if np.linalg.norm(jacobian.T @ lam + aa.T @ mu) > 1e-8:
        return result
    forced = aa[mu > 1e-8]
    t = t @ null_space(forced @ t, rcond=1e-8)
    h = np.zeros((t.shape[1], t.shape[1]))
    # Exact quadratic Hessians, assembled directly in the retained tangent basis.
    for row, (i, j, _) in enumerate(engine.lengths):
        d = t[i * engine.d : (i + 1) * engine.d] - t[j * engine.d : (j + 1) * engine.d]
        h += lam[row] * (d.T @ d) / engine.scale**2
    for weight, (i, j, _) in zip(mu, (engine.cables[index] for index in active)):
        d = t[i * engine.d : (i + 1) * engine.d] - t[j * engine.d : (j + 1) * engine.d]
        h += weight * (d.T @ d) / engine.scale**2
    offset = jacobian.shape[0] - (3 if engine.d == 3 else 1) * len(engine.parallels)
    for index, (i, j, k, l) in enumerate(engine.parallels):
        a = t[j * engine.d : (j + 1) * engine.d] - t[i * engine.d : (i + 1) * engine.d]
        b = t[l * engine.d : (l + 1) * engine.d] - t[k * engine.d : (k + 1) * engine.d]
        axes = [(1, 2), (2, 0), (0, 1)] if engine.d == 3 else [(0, 1)]
        for axis, (u, v) in enumerate(axes):
            h += (
                lam[offset + index * len(axes) + axis]
                * (
                    np.outer(a[u], b[v])
                    + np.outer(b[v], a[u])
                    - np.outer(a[v], b[u])
                    - np.outer(b[u], a[v])
                )
                / engine.scale**2
            )
    h = (h + h.T) / 2
    if h.size:
        values = np.linalg.eigvalsh(h)
        if np.min(values) >= -1e-8 and np.max(values) > 1e-8:
            t = t @ null_space(h, rcond=1e-8)
    result["linear_compatible_dimension"] = t.shape[1]
    result["linear_compatible_tangents"] = t.T.reshape(-1, len(x), engine.d).tolist()
    if not t.shape[1]:
        result["second_order"] = "locked"
        result["motion_kind"] = "locked"
    return result
