"""Least-violation construction previews with an exact affine grab constraint."""

from itertools import combinations

import numpy as np
from scipy.linalg import null_space
from scipy.optimize import least_squares


def preview(engine, keys, targets, weights=None):
    e = engine
    before = e.current.copy()
    d = e.d
    ids = [e.index[k] for k in keys]
    weights = (
        np.ones(len(ids)) / len(ids) if weights is None else np.asarray(weights, float)
    )
    target = weights @ np.asarray(targets, float)[:, :d]
    fixed = {
        e.index[f"{o.id}:{n}"] for o in e.scene.objects if o.fixed for n in o.points
    }
    free = np.array(
        [i * d + a for i in range(len(before)) if i not in fixed for a in range(d)],
        dtype=int,
    )
    A = np.zeros((d, before.size))
    for i, w in zip(ids, weights):
        A[:, i * d : (i + 1) * d] += w * np.eye(d)
    base = before.ravel().copy()
    # The antipodal marker is a derived point, even when the preview distorts a ring.
    affine = np.zeros((d * len(e.ring_bottoms), before.size))
    for row, (bottom, center, top) in enumerate(e.ring_bottoms):
        for axis in range(d):
            affine[row * d + axis, bottom * d + axis] = 1
            affine[row * d + axis, top * d + axis] = 1
            affine[row * d + axis, center * d + axis] = -2
    matrix = np.vstack((A, affine))[:, free]
    correction = (
        np.linalg.lstsq(matrix, np.r_[target - A @ base, -affine @ base], rcond=1e-12)[
            0
        ]
        if len(free)
        else np.empty(0)
    )
    base[free] += correction
    Z = null_space(matrix, rcond=1e-12)
    # Small displacement regularization selects a nearby fit among equivalent previews.
    regularization = 1e-4 / e.scale

    def embed(z):
        result = base.copy()
        result[free] += Z @ z
        return result

    def residual(z):
        x = embed(z)
        return np.r_[e.residual(x), regularization * (x[free] - before.ravel()[free])]

    def jac(z):
        x = embed(z)
        return np.vstack((e.jac(x)[:, free] @ Z, regularization * Z))

    if Z.shape[1]:
        solution = least_squares(
            residual,
            np.zeros(Z.shape[1]),
            jac=jac,
            max_nfev=100,
            ftol=1e-8,
            xtol=1e-9,
            gtol=1e-9,
        )
        x = embed(solution.x).reshape(-1, d)
    else:
        x = base.reshape(-1, d)

    # Preview state is deliberately separate from the accepted feasible configuration.
    def point(i):
        return [*map(float, x[i]), *([0.0] if d == 2 else [])]

    def severity(error):
        return float(error / (0.03 + error))

    objects = {}
    edges = {}
    points = {k: 0.0 for k in e.keys}
    joints = []

    def mark(key, value):
        points[key] = max(points[key], value)

    for obj in e.scene.objects:
        worst = 0.0
        for a, b in combinations(obj.points, 2):
            ka, kb = f"{obj.id}:{a}", f"{obj.id}:{b}"
            i, j = e.index[ka], e.index[kb]
            length = np.linalg.norm(e.initial[i] - e.initial[j])
            error = abs(np.linalg.norm(x[i] - x[j]) - length) / max(
                length, 0.05 * e.scale
            )
            value = severity(error)
            edges[f"{ka}|{kb}"] = value
            worst = max(worst, value)
            mark(ka, value)
            mark(kb, value)
        objects[obj.id] = worst
    for c in e.scene.constraints:
        i = e.index[c.a]
        a = point(i)
        b = None
        if c.kind == "coincident":
            j = e.index[c.b]
            b = point(j)
            error = np.linalg.norm(x[i] - x[j]) / e.scale
        elif c.kind == "pin":
            b = [float(v) for v in c.value]
            error = np.linalg.norm(x[i] - np.array(b[:d])) / e.scale
        elif c.kind == "distance":
            j = e.index[c.b]
            b = point(j)
            length = float(c.value) ** 0.5
            error = abs(np.linalg.norm(x[i] - x[j]) - length) / max(
                length, 0.05 * e.scale
            )
        elif c.kind == "plane":
            p, n = (np.array(v, float) for v in c.value)
            a3 = np.array(a)
            offset = np.dot(a3 - p, n) / np.linalg.norm(n)
            b = (a3 - offset * n / np.linalg.norm(n)).tolist()
            error = abs(offset) / e.scale
        elif c.kind == "parallel":
            j = e.index[c.b]
            k, l = (e.index[v] for v in c.value)
            u = x[j] - x[i]
            v = x[l] - x[k]
            error = (
                np.linalg.norm(np.cross(u, v))
                if d == 3
                else abs(u[0] * v[1] - u[1] * v[0])
            ) / max(np.linalg.norm(u) * np.linalg.norm(v), 1e-20)
        else:
            continue
        value = severity(error)
        mark(c.a, value)
        if c.b:
            mark(c.b, value)
        joints.append(
            {
                "id": c.id,
                "kind": c.kind,
                "a": a,
                "b": b,
                "error": float(error),
                "severity": value,
            }
        )
    grab = A @ x.ravel()
    return {
        "configuration": e.configuration(x),
        "grab": [*map(float, grab), *([0.0] if d == 2 else [])],
        "target_error": float(np.linalg.norm(grab - target)),
        "objects": objects,
        "edges": edges,
        "points": points,
        "joints": joints,
    }
