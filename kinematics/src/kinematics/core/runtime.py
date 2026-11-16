"""Stateful browser/native bridge. All returned values are plain JSON data."""

import json

import numpy as np

from .engine import Engine
from .exploration import Exploration, TourPreparation
from .model import build_scene
from .preview import preview
from .topology import Unsupported, analyze
from .wander import Wander


class Session:
    def __init__(self):
        self.engine = None
        self.cells = []
        self.status = {}
        self.revision = 0
        self.exploration = None
        self.exploration_serial = 0
        self.tour_job = None
        self.wander_job = None
        self.wander_serial = 0

    def run(self, source, dimension=None, mode="numerical"):
        self.revision += 1
        self.exploration = None
        self.tour_job = None
        self.wander_job = None
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
            self.cells = self.initial_motion()
        self.update_orbits()
        return self.snapshot()

    def update_orbits(self):
        for cell in self.cells:
            cell["orbits"] = {
                o.id: [cfg[f"{o.id}:origin"] for cfg in cell["configurations"]]
                if o.kind == "ring"
                else np.mean(
                    [
                        [cfg[f"{o.id}:{n}"] for n in o.metric_names]
                        for cfg in cell["configurations"]
                    ],
                    axis=1,
                ).tolist()
                for o in self.engine.scene.objects
            }

    def initial_motion(self):
        return [
            {
                "dimension": self.engine.mobility()["linear_compatible_dimension"],
                "closed": False,
                "configurations": [self.engine.configuration()],
                "witness": self.engine.configuration(),
                "certificate": None,
            }
        ]

    def snapshot(self):
        e = self.engine
        return {
            "revision": self.revision,
            "dimension": e.d,
            "scale": e.scale,
            "objects": [
                {
                    "id": o.id,
                    "kind": o.kind,
                    "fixed": o.fixed,
                    "points": o.render_names,
                    "point_labels": o.point_labels,
                    **({"source_span": list(o.source_span)} if o.source_span else {}),
                }
                for o in e.scene.objects
            ],
            "constraints": [
                {
                    "id": c.id,
                    "kind": c.kind,
                    "a": c.a,
                    "b": c.b,
                    **({"length": float(c.value) ** 0.5} if c.kind == "cable" else {}),
                    **({"source_span": list(c.source_span)} if c.source_span else {}),
                }
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
        self.exploration = None
        self.tour_job = None
        self.wander_job = None
        result = self.engine.reassemble(keys, targets, weights)
        self.cells = self.initial_motion()
        self.update_orbits()
        return {**self.snapshot(), "reachable": result["reachable"]}

    def select(self, index):
        if self.status.get("status") != "certified":
            raise ValueError("component selection requires certified topology")
        self.exploration = None
        self.tour_job = None
        self.wander_job = None
        c = self.cells[index]
        self.engine.current = self.engine.project(
            np.array([c["witness"][k][: self.engine.d] for k in self.engine.keys])
        )
        return self.snapshot()

    def dispatch(self, message):
        op = message["op"]
        if op == "numerical_model":
            from .numerical_model import export_model

            return export_model(self)
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
        if op == "wander_start":
            live = Engine(self.engine.scene)
            live.current = self.engine.current.copy()
            if "configuration" in message:
                live.current = live.project(
                    np.array(
                        [message["configuration"][k][: live.d] for k in live.keys],
                        dtype=float,
                    )
                )
            self.wander_job = None
            job = Wander(live, **message.get("settings", {}))
            self.wander_serial += 1
            job.job_id = self.wander_serial
            self.wander_job = job
            return {
                "job_id": job.job_id,
                "frames": [{"configuration": job.engine.configuration(), "time": 0.0}],
                "status": job.status,
                "reason": job.reason,
            }
        if op.startswith("wander_"):
            if self.wander_job is None:
                raise ValueError("Wander invalidated; start a new walk")
            if message.get("job_id") != self.wander_job.job_id:
                raise ValueError("stale wander job")
            if op == "wander_step":
                if "boundary_repulsion" in message:
                    self.wander_job.set_boundary_repulsion(
                        message["boundary_repulsion"]
                    )
                return self.wander_job.advance()
            if op == "wander_cancel":
                self.wander_job = None
                return {"status": "cancelled"}
        if op == "explore_start":
            self.exploration_serial += 1
            self.tour_job = None
            self.exploration = Exploration(self.engine, **message.get("settings", {}))
            self.exploration.job_id = self.exploration_serial
            return self.exploration.snapshot()
        if (
            op.startswith("explore_")
            and op != "explore_start"
            and self.exploration is None
        ):
            raise ValueError("Exploration invalidated; start a new exploration")
        if (
            op.startswith("explore_")
            and message.get("job_id", self.exploration.job_id)
            != self.exploration.job_id
        ):
            raise ValueError("stale exploration job")
        if op == "explore_pause":
            self.exploration.pause()
            return self.exploration.snapshot()
        if op == "explore_cancel":
            self.tour_job = None
            self.exploration.cancel()
            return self.exploration.snapshot()
        if op == "explore_refine":
            self.exploration.refine(message["spacing"])
            return self.exploration.snapshot()
        if op == "explore_step":
            self.exploration.advance()
            return self.exploration.snapshot(
                message.get("node_cursor"), message.get("edge_cursor", 0)
            )
        if op == "explore_extend":
            self.exploration.seconds += 30
            self.exploration.limit += 2000
            return self.exploration.snapshot()
        if op == "explore_tour_start":
            self.exploration.attach(self.engine.current)
            self.tour_job = TourPreparation(
                self.exploration, message.get("count", 16), message.get("seed", 0)
            )
            return {
                **self.tour_job.result,
                "frames": [self.tour_job.coarse[0]],
                "duration": 45.0,
                "graph": self.exploration.snapshot(),
            }
        if op == "explore_tour_step":
            if (
                self.tour_job is None
                or self.tour_job.exploration is not self.exploration
            ):
                raise ValueError("Tour preparation invalidated")
            return self.tour_job.advance()
        if op == "explore_tour":
            return self.exploration.tour(
                message.get("count", 16), message.get("seed", 0)
            )
        if op == "adopt":
            candidate = np.array(
                [
                    message["configuration"][k][: self.engine.d]
                    for k in self.engine.keys
                ],
                dtype=float,
            )
            if not np.isfinite(candidate).all():
                raise ValueError("Configuration contains non-finite coordinates")
            # Cached animation poses are already corrected. Reprojecting a feasible
            # singular pose can drift into fictitious first-order flex directions.
            self.engine.current = (
                candidate
                if self.engine.error(candidate) <= 1e-9
                else self.engine.project(candidate)
            )
            return {
                "configuration": self.engine.configuration(),
                "mobility": self.engine.mobility(),
            }
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
            self.exploration = None
            self.tour_job = None
            self.wander_job = None
            self.engine.current = self.engine.project(self.engine.initial)
            return self.snapshot()
        raise ValueError(f"unknown operation {op}")


session = Session()


def dispatch_json(message):
    return json.dumps(session.dispatch(json.loads(message)), allow_nan=False)
