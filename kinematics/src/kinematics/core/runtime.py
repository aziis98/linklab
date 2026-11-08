"""Stateful browser/native bridge. All returned values are plain JSON data."""

import json

import numpy as np
from scipy.linalg import null_space

from .engine import Engine
from .model import build_scene
from .preview import preview
from .topology import Unsupported, analyze


class Session:
    def __init__(self):
        self.engine = None
        self.cells = []
        self.status = {}
        self.revision = 0

    def run(self, source, dimension=None, mode="numerical"):
        self.revision += 1
        self.engine = Engine(build_scene(source, dimension))
        self.engine.assemble()
        self.cells = []
        if mode == "topological":
            try:
                result = analyze(self.engine)
                self.cells = result.pop("cells")
                self.status = result
            except Unsupported as exc:
                self.status = {
                    "status": "fallback",
                    "reason": str(exc),
                    "complete": False,
                }
        else:
            self.status = {
                "status": "numerical",
                "reason": "Local motion traces only; numerical component discovery is disabled",
                "complete": False,
            }
        if not self.cells:
            self.cells = self.explore()
        self.update_orbits()
        return self.snapshot()

    def update_orbits(self):
        for cell in self.cells:
            cell["orbits"] = {
                o.id: np.mean(
                    [
                        [cfg[f"{o.id}:{n}"] for n in o.points]
                        for cfg in cell["configurations"]
                    ],
                    axis=1,
                ).tolist()
                for o in self.engine.scene.objects
            }

    def explore(self):
        e = self.engine
        initial = e.current.copy()
        m = e.mobility()
        if not m["first_order"] or m["second_order"] == "locked":
            return [
                {
                    "dimension": 0,
                    "closed": False,
                    "configurations": [e.configuration()],
                    "witness": e.configuration(),
                    "certificate": None,
                }
            ]
        if m["linear_compatible_dimension"] > 1:
            return [
                {
                    "dimension": m["linear_compatible_dimension"],
                    "closed": False,
                    "configurations": [e.configuration()],
                    "witness": e.configuration(),
                    "certificate": None,
                }
            ]
        paths = []
        for sign in (-1, 1):
            x = initial.copy()
            tangent = (
                np.array(e.mobility(x)["linear_compatible_tangents"])
                .reshape(-1, x.size)
                .T[:, 0]
                * sign
            )
            path = [e.configuration(x)]
            closed = False
            step = 0.015 * e.scale
            for _ in range(240):
                T = (
                    np.array(e.mobility(x)["linear_compatible_tangents"])
                    .reshape(-1, x.size)
                    .T
                )
                if T.shape[1] != 1:
                    break
                v = T[:, 0]
                v *= 1 if v @ tangent >= 0 else -1
                try:
                    candidate = e.project(x + step * v.reshape(-1, e.d))
                except ValueError:
                    break
                if (
                    np.linalg.norm(candidate - x) > 2 * step
                    or np.linalg.norm(candidate - x) < step * 0.1
                ):
                    break
                x = candidate
                tangent = v
                path.append(e.configuration(x))
                if (
                    len(path) > 12
                    and np.linalg.norm(x - initial) < step
                    and np.dot(
                        v, null_space(e.jac(initial.ravel()), rcond=1e-8)[:, 0] * sign
                    )
                    > 0.9
                ):
                    path.append(e.configuration(initial))
                    closed = True
                    break
            paths.append(
                {
                    "dimension": 1,
                    "closed": closed,
                    "configurations": path,
                    "witness": path[0],
                    "certificate": None,
                }
            )
            if closed:
                break
        return paths

    def snapshot(self):
        e = self.engine
        return {
            "revision": self.revision,
            "dimension": e.d,
            "objects": [
                {"id": o.id, "kind": o.kind, "fixed": o.fixed, "points": list(o.points)}
                for o in e.scene.objects
            ],
            "constraints": [
                {"id": c.id, "kind": c.kind, "a": c.a, "b": c.b}
                for c in e.scene.constraints
            ],
            "configuration": e.configuration(),
            "mobility": e.mobility(),
            "motion": {**self.status, "cells": self.cells},
        }

    def drag(self, keys, targets, weights=None):
        # Certified isolated cells have no finite motion, even at singular points.
        if self.status.get("status") == "certified":
            for c in self.cells:
                if c["dimension"] == 0 and all(
                    np.linalg.norm(np.array(self.engine.configuration()[k]) - p)
                    < 1e-7 * self.engine.scale
                    for k, p in c["witness"].items()
                ):
                    return {
                        "configuration": self.engine.configuration(),
                        "mobility": self.engine.mobility(),
                        "reachable": False,
                    }
        return self.engine.drag(keys, targets, weights)

    def reassemble(self, keys, targets, weights=None):
        if self.status.get("status") == "certified":
            raise ValueError(
                "reassembly is a numerical operation; use the certified component selector"
            )
        result = self.engine.reassemble(keys, targets, weights)
        self.cells = self.explore()
        self.update_orbits()
        return {**self.snapshot(), "reachable": result["reachable"]}

    def select(self, index):
        if self.status.get("status") != "certified":
            raise ValueError("component selection requires certified topology")
        c = self.cells[index]
        self.engine.current = self.engine.project(
            np.array([c["witness"][k][: self.engine.d] for k in self.engine.keys])
        )
        return self.snapshot()

    def dispatch(self, message):
        op = message["op"]
        if op == "snapshot":
            return self.snapshot()
        if op == "run":
            return self.run(
                message["source"],
                message.get("dimension"),
                message.get("mode", "numerical"),
            )
        if message.get("revision", self.revision) != self.revision:
            raise ValueError("stale scene request")
        if op == "drag":
            result = self.drag(
                message["keys"], message["targets"], message.get("weights")
            )
            result["preview"] = preview(
                self.engine, message["keys"], message["targets"], message.get("weights")
            )
            return result
        if op == "reassemble":
            return self.reassemble(
                message["keys"], message["targets"], message.get("weights")
            )
        if op == "select":
            return self.select(message["index"])
        if op == "reset":
            self.engine.current = self.engine.project(self.engine.initial)
            return self.snapshot()
        raise ValueError(f"unknown operation {op}")


session = Session()


def dispatch_json(message):
    return json.dumps(session.dispatch(json.loads(message)), allow_nan=False)
