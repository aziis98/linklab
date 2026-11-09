"""Exact straight-chain consequences used to stabilize numerical continuation."""

from __future__ import annotations

import heapq
from itertools import combinations

import sympy as sp

from .model import Scene, exact

ExactPoint = tuple[sp.Expr, ...]


def taut_chain_pins(scene: Scene) -> dict[str, ExactPoint]:
    """Find material points forced onto a straight chain between fixed anchors.

    The triangle inequality becomes equality when a chain's total length equals
    its anchor separation. Every point on that chain then has a fixed position.
    Floating distances only find candidates; symbolic equality authorizes pins.
    The input scene is unchanged, and these are consequences, not new user constraints.
    """
    points: dict[str, ExactPoint] = {
        f"{obj.id}:{name}": tuple(exact(v) for v in point)
        for obj in scene.objects
        for name, point in obj.points.items()
    }
    parent = {key: key for key in points}

    def root(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for constraint in scene.constraints:
        if constraint.kind == "coincident":
            parent[root(constraint.b)] = root(constraint.a)

    explicit: dict[str, ExactPoint] = {
        f"{obj.id}:{name}": points[f"{obj.id}:{name}"]
        for obj in scene.objects
        if obj.fixed
        for name in obj.points
    }
    for constraint in scene.constraints:
        if constraint.kind == "pin":
            explicit[constraint.a] = tuple(exact(v) for v in constraint.value)
    anchors: dict[str, ExactPoint] = {}
    for key, position in explicit.items():
        key = root(key)
        if key in anchors and any(
            sp.simplify(a - b) != 0 for a, b in zip(anchors[key], position)
        ):
            return {}  # Contradictions remain the live solver's responsibility.
        anchors[key] = position
    if len(anchors) < 2:
        return {}

    lengths: dict[tuple[str, str], sp.Expr] = {}

    def edge(a: str, b: str, squared: sp.Expr) -> None:
        a, b = sorted((root(a), root(b)))
        length = sp.sqrt(squared)
        if a == b or length == 0:
            return
        if (a, b) not in lengths or float(length) < float(lengths[a, b]):
            lengths[a, b] = length

    for obj in scene.objects:
        for a, b in combinations(obj.points, 2):
            ka, kb = f"{obj.id}:{a}", f"{obj.id}:{b}"
            edge(ka, kb, sum((x - y) ** 2 for x, y in zip(points[ka], points[kb])))
    for constraint in scene.constraints:
        if constraint.kind == "distance":
            edge(constraint.a, constraint.b, exact(constraint.value))
    graph: dict[str, list[tuple[str, float, sp.Expr]]] = {
        root(key): [] for key in points
    }
    for (a, b), length in lengths.items():
        graph[a].append((b, float(length), length))
        graph[b].append((a, float(length), length))

    def shortest(start: str) -> tuple[dict[str, float], dict[str, sp.Expr]]:
        distances = {start: 0.0}
        symbolic: dict[str, sp.Expr] = {start: sp.S.Zero}
        queue = [(0.0, start)]
        while queue:
            distance, a = heapq.heappop(queue)
            if distance != distances[a]:
                continue
            for b, length, expression in graph[a]:
                candidate = distance + length
                if candidate < distances.get(b, float("inf")):
                    distances[b] = candidate
                    symbolic[b] = symbolic[a] + expression
                    heapq.heappush(queue, (candidate, b))
        return distances, symbolic

    while True:
        paths = {key: shortest(key) for key in anchors}
        additions: dict[str, ExactPoint] = {}
        for a, b in combinations(anchors, 2):
            start, end = anchors[a], anchors[b]
            separation = sp.sqrt(sum((x - y) ** 2 for x, y in zip(start, end)))
            distance = float(separation)
            if not distance:
                continue
            da, ea = paths[a]
            db, eb = paths[b]
            for key in graph:
                if key in anchors or key in additions or key not in da or key not in db:
                    continue
                if abs(da[key] + db[key] - distance) > 1e-10 * max(1.0, distance):
                    continue
                if sp.simplify(ea[key] + eb[key] - separation) != 0:
                    continue
                fraction = ea[key] / separation
                additions[key] = tuple(
                    sp.simplify(x + fraction * (y - x)) for x, y in zip(start, end)
                )
        if not additions:
            break
        anchors.update(additions)
    return {
        key: anchors[root(key)]
        for key in points
        if key not in explicit and root(key) in anchors
    }
