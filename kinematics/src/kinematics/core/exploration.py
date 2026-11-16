"""Incremental, bounded numerical roadmaps and graph-distance tours."""

from __future__ import annotations

import heapq
import itertools
import time
from collections import deque
from typing import TypedDict

import numpy as np
from scipy.optimize import least_squares

from .engine import Configuration, Engine, FloatArray


class RoadmapNode(TypedDict):
    id: int
    configuration: Configuration
    x: FloatArray
    dimension: int
    singular: bool


class RoadmapEdge(TypedDict):
    id: int
    a: int
    b: int
    length: float
    path: list[Configuration]


class Exploration:
    def __init__(
        self,
        live,
        spacing=0.5,
        radius=2.0,
        seconds=30.0,
        limit=2000,
        seed=0,
        turn_degrees=15.0,
        correction_ratio=0.25,
    ):
        self.engine = Engine(live.scene)
        self.engine.current = live.current.copy()
        self.turn_degrees = turn_degrees
        self.correction_ratio = correction_ratio
        self.root = live.current.copy()
        self.spacing = float(spacing)
        self.radius = float(radius)
        if not 1e-5 <= self.spacing <= 1 or self.radius <= 0:
            raise ValueError("invalid exploration spacing or radius")
        if (
            not np.isfinite(
                [seconds, radius, spacing, turn_degrees, correction_ratio]
            ).all()
            or seconds <= 0
            or not 1 <= limit <= 100000
            or not 0 < turn_degrees <= 90
            or not 0 < correction_ratio <= 0.5
        ):
            raise ValueError("invalid exploration limits or continuation tolerances")
        self.seconds = seconds
        self.limit = limit
        self.used = 0.0
        self.rng = np.random.default_rng(seed)
        self.nodes: list[RoadmapNode] = []
        self.tour_start = 0
        self.refining = False
        self.boundaries = 0
        self.unresolved_nodes: set[int] = set()
        self.edges: list[RoadmapEdge] = []
        self.job_id = 0
        self.next_edge = 0
        self.removed = []
        self.layout_basis = None
        self.frontier: deque[tuple[int, FloatArray]] = deque()
        self.sample_vectors: list[FloatArray] = []
        self.status = "paused"
        self.attempts = 0
        self.unresolved = 0
        self.weights = np.zeros(len(self.root))
        moving = [o for o in live.scene.objects if not o.fixed]
        for o in moving:
            for n in o.metric_names:
                self.weights[live.index[f"{o.id}:{n}"]] = 1 / max(
                    1, len(moving) * len(o.metric_names)
                )
        self.metric = (
            np.repeat(np.sqrt(self.weights), self.engine.d) / self.engine.scale
        )
        self.add(self.root)

    def distance(self, a: FloatArray, b: FloatArray) -> float:
        return float(
            np.sqrt(np.sum(self.weights[:, None] * (a - b) ** 2)) / self.engine.scale
        )

    def add(self, x: FloatArray) -> int:
        i = len(self.nodes)
        m = self.engine.mobility(x)
        self.sample_vectors.append((x - self.root).ravel() * self.metric)
        self.nodes.append(
            {
                "id": i,
                "configuration": self.engine.configuration(x),
                "x": x.copy(),
                "dimension": m["linear_compatible_dimension"],
                "singular": m["second_order"] == "inconclusive"
                or m["first_order"] != m["linear_compatible_dimension"],
            }
        )
        T = np.array(m["linear_compatible_tangents"]).reshape(-1, x.size).T
        if T.shape[1]:
            directions = [T[:, j] * sign for j in range(T.shape[1]) for sign in (-1, 1)]
            if T.shape[1] > 1:
                directions.extend(
                    T @ self.rng.normal(size=T.shape[1])
                    for _ in range(min(24, 4 * T.shape[1]))
                )
            if m["second_order"] == "inconclusive":
                raw = np.array(m["tangents"]).reshape(-1, x.size).T
                change = raw.T @ T
                forms = [change.T @ np.array(h) @ change for h in m["quadratic_forms"]]
                forms = [
                    h / np.linalg.norm(h) for h in forms if np.linalg.norm(h) > 1e-8
                ]
                if forms:
                    probes = []
                    for direction in directions:
                        guess = T.T @ direction
                        guess /= max(np.linalg.norm(guess), 1e-20)

                        def cone(a):
                            return np.r_[[a @ h @ a for h in forms], a @ a - 1]

                        def cone_jac(a):
                            return np.vstack([*[2 * h @ a for h in forms], 2 * a])

                        solution = least_squares(
                            cone,
                            guess,
                            jac=cone_jac,
                            max_nfev=50,
                            gtol=1e-10,
                            ftol=1e-10,
                            xtol=1e-10,
                        )
                        if np.linalg.norm(cone(solution.x)) < 1e-6:
                            v = T @ solution.x
                            if all(
                                np.dot(v, old)
                                / (np.linalg.norm(v) * np.linalg.norm(old))
                                < 0.999
                                for old in probes
                            ):
                                probes.append(v)
                    directions = probes
                    self.unresolved_nodes.add(i)
            for direction in directions:
                if self.engine.cables:
                    direction = self.engine.direction(x, direction)
                    if np.linalg.norm(direction) < 1e-10:
                        continue
                self.frontier.append((i, direction))
        return i

    def next_frontier(self) -> tuple[int, FloatArray]:
        """Prefer tangent predictors farthest from the existing configuration samples.

        Score a bounded, seeded candidate pool so selection stays incremental.
        Recent directions compete with older directions across the whole frontier.
        Distances only prioritize work; they never authorize a connection.
        """
        if not any(n["dimension"] > 1 for n in self.nodes):
            return self.frontier.popleft()
        # Resolve junction exits before growing one branch; periodically service
        # old work so distant advancing fronts cannot starve closure attempts.
        singular = next(
            (
                i
                for i, (source, _) in enumerate(self.frontier)
                if self.nodes[source]["singular"]
            ),
            None,
        )
        if singular is not None:
            self.frontier.rotate(-singular)
            result = self.frontier.popleft()
            self.frontier.rotate(singular)
            return result
        if self.attempts % 8 == 7:
            return self.frontier.popleft()
        count = len(self.frontier)
        indices = np.unique(
            np.r_[
                np.arange(max(0, count - 24), count),
                self.rng.choice(count, min(count, 24), replace=False),
            ]
        )
        candidates = [self.frontier[int(i)] for i in indices]
        predictors = []
        for source, direction in candidates:
            vector = direction * self.metric
            norm = np.linalg.norm(vector)
            predictors.append(
                self.sample_vectors[source]
                + vector * (self.spacing / 2) / max(norm, 1e-20)
            )
        predictors = np.array(predictors)
        samples = np.array(self.sample_vectors)
        squared = (
            np.sum(predictors**2, axis=1)[:, None]
            + np.sum(samples**2, axis=1)[None, :]
            - 2 * predictors @ samples.T
        )
        scores = np.min(squared, axis=1)
        scores[np.linalg.norm(predictors, axis=1) > self.radius] = -1
        chosen = int(indices[int(np.argmax(scores))])
        self.frontier.rotate(-chosen)
        result = self.frontier.popleft()
        self.frontier.rotate(chosen)
        return result

    def phase(self, reference: FloatArray) -> FloatArray:
        tangent = (
            np.array(self.engine.mobility(reference)["linear_compatible_tangents"])
            .reshape(-1, reference.size)
            .T
        )
        matrix = tangent.T * np.repeat(self.weights, self.engine.d)[None, :]
        norms = np.linalg.norm(matrix, axis=1)
        return matrix[norms > 1e-12] / norms[norms > 1e-12, None]

    def correct(
        self,
        predictor: FloatArray,
        reference: FloatArray,
        phase: FloatArray | None = None,
    ) -> FloatArray:
        """Fix tangent coordinates while correcting the normal constraint error."""
        if self.engine.cables:
            return self.engine.project(predictor)
        phase = self.phase(reference) if phase is None else phase
        target = predictor.ravel()
        e = self.engine

        def residual(x):
            return np.r_[e.residual(x), phase @ (x - target) / e.scale]

        def jac(x):
            return np.vstack((e.jac(x), phase / e.scale))

        result = least_squares(
            residual, target, jac=jac, max_nfev=150, xtol=1e-12, ftol=1e-12, gtol=1e-12
        )
        x = result.x.reshape(reference.shape)
        if (
            e.error(x) > 1e-9
            or np.linalg.norm(phase @ (result.x - target)) / e.scale > 1e-8
        ):
            raise ValueError("Local chart correction did not converge")
        return x

    def connect(
        self, a: FloatArray, b: FloatArray
    ) -> tuple[list[FloatArray], float] | None:
        """Correct successive chord predictors; reject jumps and excessive correction."""
        x = a.copy()
        path = [x.copy()]
        length = 0.0
        for _ in range(64):
            remaining = self.distance(x, b)
            if remaining < 1e-8:
                return path + [b.copy()], length + remaining
            step = min(remaining, self.spacing / 4)
            predictor = x + (b - x) * step / remaining
            try:
                y = self.correct(predictor, x)
            except ValueError:
                return None
            progress = self.distance(y, b)
            if (
                self.distance(y, predictor) > step * self.correction_ratio
                or self.distance(self.root, y) > self.radius
                or progress >= remaining - 1e-10
            ):
                return None
            length += self.distance(x, y)
            path.append(y.copy())
            x = y
        return None

    def edge(self, a: int, b: int, path: list[FloatArray], length: float) -> None:
        if a == b or any({e["a"], e["b"]} == {a, b} for e in self.edges):
            return
        self.edges.append(
            {
                "id": self.next_edge,
                "a": a,
                "b": b,
                "length": length,
                "path": [self.engine.configuration(x) for x in path],
            }
        )

        self.next_edge += 1

    def advance(self, budget_ms=25):
        if self.status == "cancelled":
            raise ValueError("Exploration was cancelled")
        start = time.monotonic()
        self.status = "running"
        while self.frontier and (time.monotonic() - start) * 1000 < budget_ms:
            if (
                self.used + time.monotonic() - start >= self.seconds
                or len(self.nodes) >= self.limit
            ):
                self.status = "budget_limit"
                break
            source, v = self.next_frontier()
            a = self.nodes[source]["x"]
            norm = self.distance(a, a + v.reshape(a.shape))
            if norm < 1e-12:
                continue
            v = v.reshape(a.shape) / norm
            h = self.spacing / 2
            accepted = None
            self.attempts += 1
            phase = self.phase(a)
            if self.nodes[source]["singular"]:
                row = v.ravel() * np.repeat(self.weights, self.engine.d)
                phase = (row / max(np.linalg.norm(row), 1e-20))[None, :]
            while h >= self.spacing / 1000:
                predictor = a + h * v
                try:
                    candidate = self.correct(predictor, a, phase)
                except ValueError:
                    h *= 0.5
                    continue
                if (
                    self.distance(candidate, predictor) <= h * self.correction_ratio
                    and self.distance(a, candidate) >= h * 0.5
                ):
                    tangent = (
                        np.array(
                            self.engine.mobility(candidate)[
                                "linear_compatible_tangents"
                            ]
                        )
                        .reshape(-1, candidate.size)
                        .T
                    )
                    metric = np.repeat(np.sqrt(self.weights), self.engine.d)
                    if tangent.shape[1] == 0:
                        h *= 0.5
                        continue
                    basis = np.linalg.svd(
                        metric[:, None] * tangent, full_matrices=False
                    )[0]
                    direction = metric * v.ravel()
                    cosine = np.linalg.norm(basis.T @ direction) / max(
                        np.linalg.norm(direction), 1e-20
                    )
                    if cosine < np.cos(np.deg2rad(self.turn_degrees)):
                        h *= 0.5
                        continue
                    accepted = candidate
                    break
                h *= 0.5
            if accepted is None:
                self.unresolved += 1
                self.unresolved_nodes.add(source)
                continue
            if self.distance(self.root, accepted) > self.radius:
                self.boundaries += 1
                continue
            # Keep only new coverage or a verified nonlocal closure, never merge by proximity.
            nearby = sorted(
                (self.distance(accepted, n["x"]), n["id"]) for n in self.nodes
            )
            merge_radius = min(self.spacing / 4, h / 2)
            if nearby[0][0] < merge_radius:
                target = nearby[0][1]
                if target == source or any(
                    {e["a"], e["b"]} == {source, target} for e in self.edges
                ):
                    continue
                connection = self.connect(a, self.nodes[target]["x"])
                if connection:
                    self.edge(source, target, *connection)
                continue
            # A meeting may lie inside an already traced edge, between its samples.
            joined = False
            for old in list(self.edges):
                if source in (old["a"], old["b"]) and not self.refining:
                    continue
                positions = [
                    np.array([cfg[k][: self.engine.d] for k in self.engine.keys])
                    for cfg in old["path"]
                ]
                for k, (left, right) in enumerate(itertools.pairwise(positions)):
                    delta = right - left
                    denom = np.sum(self.weights[:, None] * delta**2)
                    if denom < 1e-20:
                        continue
                    t = float(
                        np.sum(self.weights[:, None] * (accepted - left) * delta)
                        / denom
                    )
                    if not 0.05 < t < 0.95:
                        continue
                    predictor = left + t * delta
                    if self.distance(accepted, predictor) > merge_radius:
                        continue
                    try:
                        meeting = self.correct(predictor, left)
                    except ValueError:
                        continue
                    incoming = self.connect(a, meeting)
                    first = self.connect(left, meeting)
                    last = self.connect(meeting, right)
                    if not incoming or not first or not last:
                        continue
                    junction = self.add(meeting)
                    before = positions[:k] + first[0]
                    after = last[0] + positions[k + 2 :]
                    self.edges.remove(old)
                    self.removed.append(old["id"])

                    def length(path):
                        return sum(
                            self.distance(p, q) for p, q in itertools.pairwise(path)
                        )

                    self.edge(old["a"], junction, before, length(before))
                    self.edge(junction, old["b"], after, length(after))
                    self.edge(source, junction, *incoming)
                    joined = True
                    break
                if joined:
                    break
            if joined:
                continue
            i = self.add(accepted)
            self.edge(source, i, [a, accepted], self.distance(a, accepted))
        self.used += time.monotonic() - start
        if not self.frontier and self.status == "running":
            self.status = "frontier_exhausted"
        return self.snapshot()

    def snapshot(self, node_cursor=None, edge_cursor=0):
        values = np.array([n["x"].ravel() for n in self.nodes])
        centered = values - values.mean(axis=0)
        if len(values) > 1:
            if self.layout_basis is None:
                _, _, axes = np.linalg.svd(centered, full_matrices=False)
                if len(values) >= 16:
                    self.layout_basis = axes[:3].T
                basis = axes[:3].T
            else:
                basis = self.layout_basis
            xy = centered @ basis
            if xy.shape[1] < 3:
                xy = np.pad(xy, ((0, 0), (0, 3 - xy.shape[1])))
        else:
            xy = np.zeros((1, 3))
        factor = 75 / max(float(np.max(np.abs(xy))), 1e-9)
        layout = (xy[:, :2] * factor + np.array([150, 90])).tolist()
        delta = node_cursor is not None
        return {
            "job_id": self.job_id,
            "status": self.status,
            "used": self.used,
            "seconds": self.seconds,
            "limit": self.limit,
            "spacing": self.spacing,
            "pending": len(self.frontier),
            "attempts": self.attempts,
            "unresolved": self.unresolved,
            "unresolved_nodes": sorted(self.unresolved_nodes),
            "boundaries": self.boundaries,
            "nodes": [
                {k: v for k, v in n.items() if k != "x"}
                for n in self.nodes[node_cursor or 0 :]
            ],
            "edges": [e for e in self.edges if not delta or e["id"] >= edge_cursor],
            "delta": delta,
            "node_cursor": len(self.nodes),
            "edge_cursor": self.next_edge,
            "removed_edges": self.removed,
            "layout": layout,
            "layout3d": (xy * factor / 75).tolist(),
            "complete": False,
        }

    def pause(self) -> None:
        self.status = "paused"

    def cancel(self) -> None:
        self.status = "cancelled"

    def refine(self, spacing):
        if not 1e-5 <= spacing < self.spacing:
            raise ValueError("Choose a smaller spacing to refine")
        self.spacing = spacing
        self.refining = True
        self.frontier = deque()
        for node in self.nodes:
            tangent = (
                np.array(self.engine.mobility(node["x"])["linear_compatible_tangents"])
                .reshape(-1, self.root.size)
                .T
            )
            for i in range(tangent.shape[1]):
                for sign in (-1, 1):
                    self.frontier.append((node["id"], tangent[:, i] * sign))
        self.seconds = max(self.seconds, self.used + 30)
        self.limit = max(self.limit, len(self.nodes) + 2000)
        self.status = "paused"

    def attach(self, current):
        candidates = sorted(
            (self.distance(current, n["x"]), n["id"]) for n in self.nodes
        )
        if candidates[0][0] < 1e-8:
            self.tour_start = candidates[0][1]
            return
        if self.distance(self.root, current) > self.radius:
            raise ValueError("Current pose is outside the explored region")
        for _, i in candidates[:5]:
            connection = self.connect(current, self.nodes[i]["x"])
            if connection:
                source = self.add(current)
                self.edge(source, i, *connection)
                self.tour_start = source
                return
        raise ValueError(
            "Current pose cannot be connected to the roadmap; continue exploration first"
        )

    def tour(self, count=16, seed=0):
        if not 2 <= count <= 20:
            raise ValueError("Tour target count must be between 2 and 20")
        if len(self.nodes) < 2:
            raise ValueError("Explore a mobile region before building a tour")
        adjacency = [[] for _ in self.nodes]
        for e in self.edges:
            adjacency[e["a"]].append((e["b"], e))
            adjacency[e["b"]].append((e["a"], e))

        def shortest(root):
            dist = {root: 0.0}
            previous = {}
            queue = [(0.0, root)]
            while queue:
                cost, u = heapq.heappop(queue)
                if cost != dist[u]:
                    continue
                for v, e in adjacency[u]:
                    value = cost + e["length"]
                    if value < dist.get(v, float("inf")):
                        dist[v] = value
                        previous[v] = (u, e)
                        heapq.heappush(queue, (value, v))
            return dist, previous

        rng = np.random.default_rng(seed)
        selected = [self.tour_start]
        cache = {selected[0]: shortest(selected[0])}
        # Continuation can shrink coarse requested steps to follow curved regions.
        target_spacing = min(
            self.spacing,
            float(np.median([e["length"] for e in self.edges]))
            if self.edges
            else self.spacing,
        )
        while len(selected) < min(count, len(self.nodes)):
            scores = [
                (min(cache[s][0].get(i, float("inf")) for s in selected), i)
                for i in range(len(self.nodes))
                if i not in selected
            ]
            scores = [p for p in scores if np.isfinite(p[0]) and p[0] >= target_spacing]
            if not scores:
                break
            scores.sort(reverse=True)
            candidate = scores[int(rng.integers(max(1, len(scores) // 10)))][1]
            selected.append(candidate)
            cache[candidate] = shortest(candidate)
        if len(selected) < 2:
            raise ValueError("Explore farther before choosing well-spaced tour targets")
        route = [selected[0]]
        remaining = set(selected[1:])
        while remaining:
            v = min(remaining, key=lambda v: cache[route[-1]][0][v])
            route.append(v)
            remaining.remove(v)
        route.append(route[0])
        for _ in range(4):
            for i in range(1, len(route) - 2):
                for j in range(i + 1, len(route) - 1):
                    a, b, c, d = route[i - 1], route[i], route[j], route[j + 1]
                    if (
                        cache[a][0][c] + cache[b][0][d]
                        < cache[a][0][b] + cache[c][0][d]
                    ):
                        route[i : j + 1] = reversed(route[i : j + 1])
        frames = []
        walk = []
        for a, b in itertools.pairwise(route):
            pieces = []
            v = b
            while v != a:
                u, e = cache[a][1][v]
                path = e["path"] if e["a"] == u else list(reversed(e["path"]))
                pieces.append((u, v, path))
                v = u
            for u, v, path in reversed(pieces):
                walk.append([u, v])
                frames.extend(path if not frames else path[1:])
        return {
            "targets": selected,
            "route": route,
            "walk": walk,
            "frames": frames,
            "duration": 45.0,
        }


class TourPreparation:
    """Prepare feasible, densely spaced frames in resumable batches."""

    def __init__(self, exploration, count=16, seed=0):
        self.exploration = exploration
        self.result = exploration.tour(count, seed)
        self.coarse = self.result.pop("frames")
        self.frames = [self.coarse[0]]
        self.index = 0
        self.part = 1
        self.phase_index = -1
        self.frame_phase = None
        self.positions = [
            np.array([cfg[k][: exploration.engine.d] for k in exploration.engine.keys])
            for cfg in self.coarse
        ]
        lengths = [
            exploration.distance(a, b)
            for a, b in zip(self.positions, self.positions[1:])
        ]
        step = max(sum(lengths) / 2700, 1e-8)
        self.counts = [max(1, int(np.ceil(length / step))) for length in lengths]
        self.total = sum(self.counts) + 1

    def advance(self, budget_ms=25):
        start = time.monotonic()
        new = []
        while (
            self.index < len(self.counts)
            and (time.monotonic() - start) * 1000 < budget_ms
        ):
            a, b = self.positions[self.index : self.index + 2]
            n = self.counts[self.index]
            if self.part == n:
                cfg = self.coarse[self.index + 1]
            else:
                predictor = a + (b - a) * self.part / n
                if self.phase_index != self.index:
                    self.frame_phase = self.exploration.phase(a)
                    self.phase_index = self.index
                x = self.exploration.correct(predictor, a, self.frame_phase)
                if self.exploration.distance(x, predictor) > max(
                    self.exploration.spacing / 8, self.exploration.distance(a, b) * 0.25
                ):
                    raise ValueError(
                        "Tour interval needs finer exploration before playback"
                    )
                cfg = self.exploration.engine.configuration(x)
            new.append(cfg)
            self.frames.append(cfg)
            self.part += 1
            if self.part > n:
                self.index += 1
                self.part = 1
        return {
            **self.result,
            "frames": new,
            "prepared": len(self.frames),
            "total": self.total,
            "done": self.index == len(self.counts),
        }
