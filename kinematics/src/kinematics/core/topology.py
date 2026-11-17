"""Exact geometric decomposition for small planar distance graphs.

Certificates describe algebraic construction cells, never residual-based guesses.
"""

from __future__ import annotations

import math
import time
from itertools import combinations, pairwise

import numpy as np
import sympy as s

from .engine import Engine
from .model import exact


class Unsupported(ValueError):
    pass


def circles(a, ra, b, rb):
    a = s.Matrix(a)
    b = s.Matrix(b)
    d = b - a
    d2 = s.simplify(d.dot(d))
    if d2 == 0:
        return (
            ([a] if ra == 0 else ("circle", a, ra)) if s.simplify(ra - rb) == 0 else []
        )
    t = s.simplify((ra - rb + d2) / (2 * d2))
    h2 = s.simplify(ra / d2 - t * t)
    if h2.is_negative:
        return []
    if h2.is_nonnegative is not True:
        raise Unsupported("undecidable algebraic sign")
    mid = a + t * d
    normal = s.Matrix([-d[1], d[0]])
    return [mid] if h2 == 0 else [mid + s.sqrt(h2) * normal, mid - s.sqrt(h2) * normal]


def exact_graph(engine):
    scene = engine.scene
    if scene.dimension != 2 or any(
        o.kind != "rod" or o.affine_points or set(o.points) != {"a", "b"}
        for o in scene.objects
    ):
        raise Unsupported("exact analysis currently supports planar rods with endpoint attachments")
    parent = {k: k for k in engine.keys}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k

    for c in scene.constraints:
        if c.kind == "coincident":
            parent[root(c.a)] = root(c.b)
        elif c.kind not in ("pin", "distance"):
            raise Unsupported("constraint outside exact distance family")
    roots = {k: root(k) for k in parent}
    points = {}
    fixed = {}
    edges = []
    for o in scene.objects:
        for n, p in o.points.items():
            r = roots[f"{o.id}:{n}"]
            points[r] = s.Matrix(p[:2])
            if o.fixed:
                fixed[r] = s.Matrix(p[:2])
        a, b = (roots[f"{o.id}:{n}"] for n in ("a", "b"))
        if o.rest_length is not None:
            edges.append((a, b, s.simplify(exact(o.rest_length) ** 2)))
        else:
            d = s.Matrix(o.points["a"][:2]) - s.Matrix(o.points["b"][:2])
            edges.append((a, b, s.simplify(d.dot(d))))
    for c in scene.constraints:
        if c.kind == "pin":
            r = roots[c.a]
            p = s.Matrix(c.value[:2])
            if r in fixed and fixed[r] != p:
                raise ValueError("conflicting anchors")
            fixed[r] = p
        elif c.kind == "distance":
            edges.append((roots[c.a], roots[c.b], c.value))
    return roots, points, fixed, edges


def analyze(engine: Engine):
    roots, points, fixed, edges = exact_graph(engine)
    cells = []
    deadline = time.monotonic() + 10
    incidence = {}

    def budget():
        if time.monotonic() > deadline or len(cells) > 10000:
            raise Unsupported("exact decomposition resource limit reached")

    def check(placed):
        return all(
            s.simplify((placed[a] - placed[b]).dot(placed[a] - placed[b]) - r) == 0
            for a, b, r in edges
            if a in placed and b in placed
        )

    def config(placed):
        return {k: [float(v) for v in placed[r]] + [0.0] for k, r in roots.items()}

    def add_circle(placed, node, center, radius2):
        if radius2 == 0:
            recurse({**placed, node: center})
            return
        configs = []
        for angle in np.linspace(0, 2 * math.pi, 97):
            p = dict(placed)
            p[node] = center + s.Matrix([math.cos(angle), math.sin(angle)]) * s.sqrt(
                radius2
            )
            configs.append(config(p))
        witness = dict(placed)
        witness[node] = center + s.Matrix([s.sqrt(radius2), 0])
        cells.append(
            {
                "dimension": 1,
                "closed": True,
                "configurations": configs,
                "witness": config(witness),
                "certificate": {
                    "kind": "circle",
                    "center": [str(v) for v in center],
                    "radius_squared": str(radius2),
                },
            }
        )

    def recurse(placed):
        budget()
        if not check(placed):
            return
        missing = [k for k in points if k not in placed]
        if not missing:
            cells.append(
                {
                    "dimension": 0,
                    "closed": False,
                    "configurations": [config(placed)],
                    "witness": config(placed),
                    "certificate": {
                        "kind": "exact_point",
                        "coordinates": {
                            k: [str(v) for v in p] for k, p in placed.items()
                        },
                    },
                }
            )
            return
        for node in missing:
            known = [
                (b if a == node else a, r)
                for a, b, r in edges
                if (a == node and b in placed) or (b == node and a in placed)
            ]
            if len(known) >= 2:
                for (a, ra), (b, rb) in combinations(known, 2):
                    hits = circles(placed[a], ra, placed[b], rb)
                    if isinstance(hits, tuple):
                        continue
                    for hit in hits:
                        recurse({**placed, node: hit})
                    return
                if len(missing) == 1 and len(known) == 2:
                    add_circle(placed, node, placed[known[0][0]], known[0][1])
                    return
                raise Unsupported(
                    "coincident construction with unresolved downstream geometry"
                )
            if len(missing) == 1 and len(known) == 1:
                add_circle(placed, node, placed[known[0][0]], known[0][1])
                return
        if len(missing) == 2:
            fourbar(placed, missing)
            return
        raise Unsupported("distance graph requires higher-dimensional decomposition")

    def fourbar(placed, missing):
        prefix = f"construction_{len(cells)}_"
        u, v = missing

        def anchors(node):
            return [
                (b if a == node else a, r)
                for a, b, r in edges
                if (a == node and b in placed) or (b == node and a in placed)
            ]

        au, av = anchors(u), anchors(v)
        links = [r for a, b, r in edges if {a, b} == {u, v}]
        if len(au) != 1 or len(av) != 1 or len(links) != 1:
            raise Unsupported("not a simple four-bar closure")
        A, R = au[0]
        B, S = av[0]
        L = links[0]
        A = placed[A]
        B = placed[B]
        if A == B:
            raise Unsupported("coincident four-bar ground anchors")
        t = s.Symbol("t", real=True)
        U = A + s.sqrt(R) * s.Matrix([(1 - t * t) / (1 + t * t), 2 * t / (1 + t * t)])
        diff = B - U
        d2 = s.factor(diff.dot(diff))
        disc = s.factor(4 * L * d2 - (L - S + d2) ** 2)
        numerator = s.fraction(s.cancel(disc))[0]
        try:
            roots_t = s.Poly(numerator, t).real_roots()
        except (s.PolynomialError, NotImplementedError):
            raise Unsupported(
                "critical polynomial requires unsupported algebraic root isolation"
            )
        roots_t = list(dict.fromkeys(roots_t))
        for root in roots_t:
            separation = s.simplify(d2.subs(t, root))
            if separation.is_zero is not False:
                raise Unsupported(
                    "coincident or unresolved closure centers at a critical value"
                )
        angles = [-math.pi] + [2 * math.atan(float(r)) for r in roots_t] + [math.pi]
        wrap = A + s.Matrix([-s.sqrt(R), 0])
        dw = B - wrap
        dw2 = s.simplify(dw.dot(dw))
        if dw2 == 0:
            raise Unsupported("four-bar closure with coincident centers at chart seam")
        wrap_disc = s.simplify(4 * L * dw2 - (L - S + dw2) ** 2)

        def endpoint(index, sign):
            if index in (0, len(angles) - 1):
                return prefix + ("seam" if wrap_disc == 0 else f"seam_{sign}")
            return prefix + f"root_{index - 1}"

        covered = set()
        for interval, (lo, hi) in enumerate(pairwise(angles)):
            budget()
            mid = (lo + hi) / 2
            # Certify the sign using an exact rational sample in this root-free interval.
            sample = s.Rational(str(math.tan(mid / 2)))
            if interval > 0 and not bool(sample > roots_t[interval - 1]):
                raise Unsupported("critical interval exceeds display precision")
            if interval < len(roots_t) and not bool(sample < roots_t[interval]):
                raise Unsupported("critical interval exceeds display precision")
            if s.sign(disc.subs(t, sample)) != 1:
                continue
            covered.update((interval, interval + 1))
            for sign in (-1, 1):
                configs = []
                for theta in np.linspace(lo + 1e-7, hi - 1e-7, 65):
                    q = np.array(A, float).ravel() + math.sqrt(float(R)) * np.array(
                        [math.cos(theta), math.sin(theta)]
                    )
                    b = np.array(B, float).ravel()
                    d = b - q
                    d2f = d @ d
                    if d2f < 1e-14:
                        raise Unsupported("four-bar closure with coincident centers")
                    k = (float(L - S) + d2f) / (2 * d2f)
                    h = max(0, float(L) / d2f - k * k)
                    w = q + k * d + sign * math.sqrt(h) * np.array([-d[1], d[0]])
                    configs.append(config({**placed, u: s.Matrix(q), v: s.Matrix(w)}))
                cells.append(
                    {
                        "dimension": 1,
                        "closed": endpoint(interval, sign)
                        == endpoint(interval + 1, sign),
                        "configurations": configs,
                        "witness": configs[len(configs) // 2],
                        "certificate": {
                            "kind": "fourbar_arc",
                            "critical_polynomial": str(numerator),
                            "angle_interval": [lo, hi],
                            "critical_values": [str(r) for r in roots_t],
                            "exact_sample": str(sample),
                            "sheet": sign,
                            "endpoints": [
                                endpoint(interval, sign),
                                endpoint(interval + 1, sign),
                            ],
                        },
                    }
                )
                for end in (endpoint(interval, sign), endpoint(interval + 1, sign)):
                    incidence.setdefault(end, []).append(len(cells) - 1)
        if wrap_disc == 0 and 0 not in covered and len(angles) - 1 not in covered:
            p = s.simplify(wrap + (L - S + dw2) * dw / (2 * dw2))
            witness = config({**placed, u: wrap, v: p})
            cells.append(
                {
                    "dimension": 0,
                    "closed": False,
                    "configurations": [witness],
                    "witness": witness,
                    "certificate": {"kind": "isolated_fourbar_chart_seam"},
                }
            )
        for index, root_t in enumerate(roots_t, 1):
            if index in covered:
                continue
            q = s.simplify(U.subs(t, root_t))
            d = B - q
            d2_exact = s.simplify(d.dot(d))
            if d2_exact == 0:
                raise Unsupported("coincident centers at critical value")
            p = s.simplify(q + (L - S + d2_exact) * d / (2 * d2_exact))
            witness = config({**placed, u: q, v: p})
            cells.append(
                {
                    "dimension": 0,
                    "closed": False,
                    "configurations": [witness],
                    "witness": witness,
                    "certificate": {
                        "kind": "isolated_fourbar_critical_point",
                        "parameter": str(root_t),
                    },
                }
            )

    recurse(fixed)
    links = [indices for indices in incidence.values()]
    parent = list(range(len(cells)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for indices in links:
        for i in indices[1:]:
            parent[find(i)] = find(indices[0])
    components = []
    for root in sorted({find(i) for i in range(len(cells))}):
        members = [i for i in range(len(cells)) if find(i) == root]
        components.append(
            {"dimension": max(cells[i]["dimension"] for i in members), "cells": members}
        )
    for i, c in enumerate(components):
        for k in c["cells"]:
            cells[k]["component"] = i
    return {
        "status": "certified",
        "reason": "Exact geometric cells with algebraic critical values and endpoint incidence",
        "cells": cells,
        "components": components,
        "incidence": incidence,
        "complete": True,
    }
