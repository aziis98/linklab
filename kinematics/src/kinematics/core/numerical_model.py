"""Export resolved numerical equations; consumers never interpret symbolic scenes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .runtime import Session


def export_model(session: Session) -> dict[str, object]:
    e = session.engine
    rows = []

    def linear(terms: list[tuple[int, float]], value: float = 0) -> None:
        rows.append({"linear": terms, "constant": -float(value), "quadratic": []})

    s = e.scale
    for i, j, length in e.lengths:
        terms = []
        for axis in range(e.d):
            a, b = i * e.d + axis, j * e.d + axis
            terms.extend(
                ((a, a, 1 / (2 * s * s)), (b, b, 1 / (2 * s * s)), (a, b, -1 / (s * s)))
            )
        rows.append(
            {"linear": [], "constant": -length / (2 * s * s), "quadratic": terms}
        )
    for point, weights in e.affine_points:
        for axis in range(e.d):
            terms = [(point * e.d + axis, 1 / s)]
            terms.extend(
                (i * e.d + k, -float(w[axis, k]) / s)
                for i, w in weights
                for k in range(e.d)
                if w[axis, k]
            )
            linear(terms)
    for i, j in e.equal:
        for axis in range(e.d):
            linear([(i * e.d + axis, 1 / s), (j * e.d + axis, -1 / s)])
    for i, p in list(e.pins.items()) + e.fixed_equations:
        for axis in range(e.d):
            linear([(i * e.d + axis, 1 / s)], p[axis] / s)
    for i, p, n in e.planes:
        linear(
            [(i * e.d + k, float(n[k] / (s * np.linalg.norm(n)))) for k in range(e.d)],
            np.dot(p, n) / (s * np.linalg.norm(n)),
        )
    for i, j, k, l in e.parallels:
        axes = [(1, 2), (2, 0), (0, 1)] if e.d == 3 else [(0, 1)]
        for a, b in axes:
            terms = []
            for u, v, sign in ((a, b, 1), (b, a, -1)):
                for first, c1 in ((j, 1), (i, -1)):
                    for second, c2 in ((l, 1), (k, -1)):
                        terms.append(
                            (
                                first * e.d + u,
                                second * e.d + v,
                                sign * c1 * c2 / (s * s),
                            )
                        )
            rows.append({"linear": [], "constant": 0, "quadratic": terms})
    return {
        "version": 2,
        "revision": session.revision,
        "dimension": e.d,
        "keys": e.keys,
        "initial": e.initial.ravel().tolist(),
        "current": e.current.ravel().tolist(),
        "scale": s,
        "rows": rows,
        "lengths": e.lengths,
        "cables": e.cables,
        "equal": e.equal,
        "pins": [(i, p.tolist()) for i, p in list(e.pins.items()) + e.fixed_equations],
        "planes": [(i, p.tolist(), n.tolist()) for i, p, n in e.planes],
        "parallels": e.parallels,
        "affine": [
            (p, [(i, w.tolist()) for i, w in weights]) for p, weights in e.affine_points
        ],
        "objects": [
            {
                "id": o.id,
                "fixed": o.fixed,
                "indices": [e.index[f"{o.id}:{n}"] for n in o.points],
            }
            for o in e.scene.objects
        ],
        "constraints": [
            {
                "id": c.id,
                "kind": c.kind,
                "a": e.index[c.a],
                "b": e.index[c.b] if c.b else None,
                "value": [e.index[v] for v in c.value]
                if c.kind == "parallel"
                else np.asarray(c.value, dtype=float).tolist()
                if c.value
                else [],
            }
            for c in e.scene.constraints
        ],
        "isolated": [
            [c["witness"][key][: e.d] for key in e.keys]
            for c in session.cells
            if c["dimension"] == 0
        ]
        if session.status.get("status") == "certified"
        else [],
    }
