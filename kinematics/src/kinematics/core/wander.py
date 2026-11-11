"""Persistent random steering with numerical continuation on constraint manifolds."""

from __future__ import annotations

import time
from typing import TypedDict

import numpy as np

from .engine import Configuration, Engine, FloatArray
from .exploration import Exploration
from .taut import taut_chain_pins


class WanderFrame(TypedDict):
    configuration: Configuration
    time: float


class WanderBatch(TypedDict):
    frames: list[WanderFrame]
    status: str
    reason: str


class Wander:
    """Generate timed feasible poses without modifying the supplied live engine.

    Speed is normalized, object-balanced configuration distance per second.
    Steering has correlated angular velocity, rather than independent headings.
    Edges remain numerically approximated, not certified continuous paths.
    """

    def __init__(
        self,
        live: Engine,
        seed: int = 0,
        speed: float = 0.2,
        turning: float = 0.8,
    ) -> None:
        if not np.isfinite([speed, turning]).all() or speed <= 0 or turning < 0:
            raise ValueError("Wander speed must be positive and turning nonnegative")
        self.chart = Exploration(live, spacing=0.05)
        self.engine = self.chart.engine
        # A stretched linkage can be singular at every pose while an attached
        # body still rotates. Exact implied pins remove its fictitious flex modes.
        for key, position in taut_chain_pins(live.scene).items():
            self.engine.pins.setdefault(
                self.engine.index[key], np.array(position[: self.engine.d], float)
            )
        self.engine.current = self.engine.project(self.engine.current)
        self.x = self.engine.current.copy()
        self.metric = np.repeat(np.sqrt(self.chart.weights), self.engine.d)
        self.metric /= self.engine.scale
        self.inverse_metric = np.divide(
            1.0, self.metric, out=np.zeros_like(self.metric), where=self.metric > 0
        )
        self.rng = np.random.default_rng(seed)
        self.speed = speed
        self.turning = turning
        self.time = 0.0
        self.status = "running"
        self.reason = ""
        self.job_id = 0
        self.basis = self.tangent(self.x)
        if self.basis.shape[1] == 0:
            raise ValueError(
                "No continuous motion is available from this configuration"
            )
        self.direction = self.basis @ self.rng.normal(size=self.basis.shape[1])
        self.direction /= np.linalg.norm(self.direction)
        self.steering = np.zeros_like(self.direction)

    def tangent(self, x: FloatArray) -> FloatArray:
        mobility = self.engine.mobility(x)
        if mobility["second_order"] == "inconclusive":
            raise ValueError("Wander stopped at an unresolved singular configuration")
        tangent = np.array(mobility["linear_compatible_tangents"]).reshape(-1, x.size).T
        if tangent.shape[1] == 0:
            return np.empty((x.size, 0))
        basis, singular, _ = np.linalg.svd(
            self.metric[:, None] * tangent, full_matrices=False
        )
        return basis[:, singular > 1e-10]

    def step(self) -> WanderFrame:
        basis = self.basis
        # Project previous motion direction onto the current tangent space.
        heading = basis @ (basis.T @ self.direction)
        if np.linalg.norm(heading) < 0.5:
            raise ValueError(
                "Wander stopped where the local motion direction changes abruptly"
            )
        heading /= np.linalg.norm(heading)

        # Smooth angular velocity: tangent transport plus correlated random forcing (OU process).
        dt = 1 / 30
        noise = basis @ self.rng.normal(size=basis.shape[1])
        noise /= np.sqrt(max(1, basis.shape[1] - 1))
        phase = self.chart.phase(self.x)

        # Predictor-corrector loop with adaptive step-halving.
        for _ in range(8):
            # Ornstein-Uhlenbeck / AR(1) update for correlated directional steering.
            decay = np.exp(-dt / 0.8)
            steering = (
                decay * self.steering + np.sqrt(1 - decay**2) * self.turning * noise
            )
            # Confine steering to tangent space and enforce orthogonality to heading.
            steering = basis @ (basis.T @ steering)
            steering -= heading * np.dot(heading, steering)

            # Predictor step along metric-weighted direction.
            direction = heading + dt * steering
            direction /= np.linalg.norm(direction)
            displacement = self.inverse_metric * direction * (self.speed * dt)
            predictor = self.x + displacement.reshape(self.x.shape)

            try:
                # Correct candidate pose back onto the constraint manifold.
                candidate = self.chart.correct(predictor, self.x, phase)
                length = self.chart.distance(self.x, candidate)

                # Reject if projection distance exceeds tolerance or step length drifts beyond 10%.
                if (
                    self.chart.distance(candidate, predictor) > self.speed * dt * 0.15
                    or not 0.9 * self.speed * dt <= length <= 1.1 * self.speed * dt
                ):
                    dt *= 0.5
                    continue

                # Ensure local mobility (degrees of freedom) is preserved across step.
                next_basis = self.tangent(candidate)
                if next_basis.shape[1] != basis.shape[1]:
                    raise ValueError("Wander reached a change in local mobility")
            except ValueError:
                dt *= 0.5
                continue

            # Accept step and advance state.
            self.x = candidate
            self.basis = next_basis
            self.direction = direction
            self.steering = steering
            self.time += length / self.speed
            return {
                "configuration": self.engine.configuration(self.x),
                "time": self.time,
            }
        raise ValueError(
            "Wander could not continue smoothly; try another starting pose"
        )

    def advance(self, budget_ms: float = 25, max_frames: int = 32) -> WanderBatch:
        start = time.monotonic()
        frames: list[WanderFrame] = []
        while (
            self.status == "running"
            and len(frames) < max_frames
            and (time.monotonic() - start) * 1000 < budget_ms
        ):
            try:
                frames.append(self.step())
            except ValueError as exc:
                self.status = "stopped"
                self.reason = str(exc)
        return {"frames": frames, "status": self.status, "reason": self.reason}
