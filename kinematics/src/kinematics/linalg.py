"""Minimal Lie-group helpers for SO(3) and SE(3).

Rotations are represented on both sides of the code by a 3-vector
("rotation vector" / axis-angle) and are converted to matrices with
Rodrigues' formula.  All Jacobians here are with respect to those
3-vectors, so entity parameterisations and constraint derivatives stay
consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "SE3",
    "hat",
    "vee",
    "so3_exp",
    "so3_log",
    "so3_left_jacobian",
    "so3_left_jacobian_inv",
    "so3_right_jacobian",
    "so3_right_jacobian_inv",
    "perp_basis",
    "rotvec_aligning",
    "smootherstep",
]

_SMALL = 1e-8

# Below this magnitude the closed forms for the Jacobians are used.  Between
# roughly 1e-8 and 1e-4, (1 - cos t)/t^2 and (t - sin t)/t^3 lose digits to
# catastrophic cancellation, while their Taylor series are good to ~1e-29.
# So the series are taken over a much wider range than one might expect.
_SMOOTH = 1e-4


def hat(w: np.ndarray) -> np.ndarray:
    """Skew-symmetric matrix of ``w`` so that ``hat(a) @ b == cross(a, b)``."""
    w = np.asarray(w, dtype=float).reshape(3)
    return np.array(
        [[0.0, -w[2], w[1]], [w[2], 0.0, -w[0]], [-w[1], w[0], 0.0]]
    )


def vee(S: np.ndarray) -> np.ndarray:
    """Inverse of :func:`hat`."""
    S = np.asarray(S, dtype=float).reshape(3, 3)
    return np.array([S[2, 1], S[0, 2], S[1, 0]])


def so3_exp(phi: np.ndarray) -> np.ndarray:
    """Rotation matrix of the rotation vector ``phi`` (Rodrigues)."""
    phi = np.asarray(phi, dtype=float).reshape(3)
    t2 = float(phi @ phi)
    t = float(np.sqrt(t2))
    K = hat(phi)
    if t < _SMOOTH:
        # Series-truncated sin(t)/t and (1 - cos t)/t^2.  The series are used
        # over a wide range because the closed form for the second coefficient
        # cancels catastrophically for small t.
        a = 1.0 - t2 / 6.0 + t2 * t2 / 120.0
        b = 0.5 - t2 / 24.0 + t2 * t2 / 720.0
    else:
        a = np.sin(t) / t
        b = (1.0 - np.cos(t)) / t2
    return np.eye(3) + a * K + b * (K @ K)


def so3_log(R: np.ndarray) -> np.ndarray:
    """Rotation vector of a rotation matrix.

    Ill-conditioned as ``tr(R) -> -1`` (a 180 degree rotation).  The
    constraints in this package use ``so3_log`` only on *relative*
    rotations, which are small when the assembly starts near a solution,
    so that regime is not exercised in practice.
    """
    R = np.asarray(R, dtype=float).reshape(3, 3)
    c = np.clip(0.5 * (np.trace(R) - 1.0), -1.0, 1.0)
    t = float(np.arccos(c))
    if t < _SMALL:
        return vee((R - R.T) / 2.0)
    return (t / (2.0 * np.sin(t))) * vee(R - R.T)


def so3_left_jacobian(phi: np.ndarray) -> np.ndarray:
    """``d( so3_exp(phi + dphi) ) / dphi`` in the form ``exp(Jl dphi) exp(phi)``.

    ``Jl = I + a K + b K^2`` with ``a = (1 - cos t)/t^2`` and
    ``b = (t - sin t)/t^3``.
    """
    phi = np.asarray(phi, dtype=float).reshape(3)
    t2 = float(phi @ phi)
    t = float(np.sqrt(t2))
    K = hat(phi)
    if t < _SMOOTH:
        a = 0.5 - t2 / 24.0 + t2 * t2 / 720.0
        b = 1.0 / 6.0 - t2 / 120.0 + t2 * t2 / 5040.0
    else:
        a = (1.0 - np.cos(t)) / t2
        b = (t - np.sin(t)) / (t2 * t)
    return np.eye(3) + a * K + b * (K @ K)


def so3_left_jacobian_inv(phi: np.ndarray) -> np.ndarray:
    """Inverse of :func:`so3_left_jacobian`."""
    phi = np.asarray(phi, dtype=float).reshape(3)
    t2 = float(phi @ phi)
    t = float(np.sqrt(t2))
    K = hat(phi)
    if t < _SMOOTH:
        c = 1.0 / 12.0 + t2 / 720.0 + t2 * t2 / 30240.0
    else:
        c = 1.0 / t2 - (1.0 + np.cos(t)) / (2.0 * t * np.sin(t))
    return np.eye(3) - 0.5 * K + c * (K @ K)


def so3_right_jacobian(phi: np.ndarray) -> np.ndarray:
    """``d( so3_exp(phi + dphi) ) / dphi`` in the form ``exp(phi) exp(Jr dphi)``."""
    return so3_left_jacobian(-np.asarray(phi, dtype=float).reshape(3))


def so3_right_jacobian_inv(phi: np.ndarray) -> np.ndarray:
    """Inverse of :func:`so3_right_jacobian`.

    Note that ``Jl^{-1}(phi) = Jr^{-1}(-phi)``, so this is the *left* inverse
    evaluated at the negated argument, not the left inverse at ``phi``.
    Getting this distinction wrong is easy and silently produces a Jacobian
    that is correct to first order but wrong at second order.
    """
    return so3_left_jacobian_inv(-np.asarray(phi, dtype=float).reshape(3))


def perp_basis(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two unit vectors spanning the plane orthogonal to ``n``.

    Used to turn a "vectors must be equal" condition (3 equations, rank 2)
    into exactly 2 independent equations.
    """
    n = np.asarray(n, dtype=float).reshape(3)
    n = n / max(float(np.linalg.norm(n)), _SMALL)
    # Pick the world axis least aligned with n to avoid a degenerate cross.
    axis = np.zeros(3)
    axis[int(np.argmin(np.abs(n)))] = 1.0
    b1 = np.cross(n, axis)
    b1 /= max(float(np.linalg.norm(b1)), _SMALL)
    b2 = np.cross(n, b1)
    b2 /= max(float(np.linalg.norm(b2)), _SMALL)
    return b1, b2


def rotvec_aligning(d: np.ndarray) -> np.ndarray:
    """Smallest rotation vector ``phi`` with ``so3_exp(phi) @ e_x == d``.

    Returns the minimal (single-axis) rotation, which keeps the result free
    of the axis/angle ambiguities that ``so3_log`` would introduce.  For an
    in-plane direction ``d`` the result is itself in-plane.
    """
    d = np.asarray(d, dtype=float).reshape(3)
    norm = float(np.linalg.norm(d))
    if norm < _SMALL:
        raise ValueError("cannot align a zero-length direction")
    d = d / norm
    ex = np.array([1.0, 0.0, 0.0])
    axis = np.cross(ex, d)
    s = float(ex @ d)
    n = float(np.linalg.norm(axis))
    if n < 1e-12:
        return np.zeros(3) if s > 0.0 else np.array([0.0, np.pi, 0.0])
    return (axis / n) * np.arctan2(n, s)


@dataclass(frozen=True, eq=False)
class SE3:
    """Rigid transform stored as a translation and a rotation matrix."""

    pos: np.ndarray
    rot: np.ndarray

    @staticmethod
    def identity() -> "SE3":
        return SE3(np.zeros(3), np.eye(3))

    def apply(self, p: np.ndarray) -> np.ndarray:
        """Map a point from the local frame into the world frame."""
        return self.pos + self.rot @ np.asarray(p, dtype=float)

    def compose(self, other: "SE3") -> "SE3":
        """``self * other``: apply ``other`` first, then ``self``."""
        return SE3(self.pos + self.rot @ other.pos, self.rot @ other.rot)

    def inv(self) -> "SE3":
        rt = self.rot.T
        return SE3(-rt @ self.pos, rt)

    def log(self) -> tuple[np.ndarray, np.ndarray]:
        """``(translation, rotation vector)`` of this transform."""
        return self.pos.copy(), so3_log(self.rot)

    @staticmethod
    def from_rt(rotvec: np.ndarray, pos: np.ndarray) -> "SE3":
        return SE3(np.asarray(pos, dtype=float), so3_exp(rotvec))


def smootherstep(x: np.ndarray) -> np.ndarray:
    """C2 ramp from 0 to 1, useful for parameter sweeps.

    Avoids the jerk that a linear ramp puts into a continuation solve.
    """
    x = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)
