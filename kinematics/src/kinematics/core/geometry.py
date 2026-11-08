"""Construction intersections, with explicit degeneracy results."""

from dataclasses import dataclass

import numpy as np
import sympy as s

from .model import coords, exact
from .topology import circles


@dataclass(frozen=True)
class Intersection:
    kind: str
    points: tuple = ()
    origin: tuple = ()
    direction: tuple = ()
    radius: object = 0


def circle_circle(a, ra, b, rb):
    if ra < 0 or rb < 0:
        raise ValueError("radii must be nonnegative")
    if coords(a)[2] != 0 or coords(b)[2] != 0:
        raise ValueError("circle_circle currently accepts circles in the XY plane")
    hits = circles(coords(a)[:2], exact(ra) ** 2, coords(b)[:2], exact(rb) ** 2)
    if isinstance(hits, tuple):
        return Intersection("coincident", origin=tuple(hits[1]), radius=s.sqrt(hits[2]))
    return Intersection("points" if hits else "empty", tuple(tuple(p) for p in hits))


def line_line(a, u, b, v, segments=False):
    a, u, b, v = (np.array(tuple(p), float) for p in (a, u, b, v))
    if np.linalg.norm(u) == 0 or np.linalg.norm(v) == 0:
        raise ValueError("directions must be nonzero")
    M = np.column_stack((u, -v))
    ts, _, rank, _ = np.linalg.lstsq(M, b - a, rcond=None)
    if rank < 2:
        if np.linalg.norm((b - a) - u * np.dot(b - a, u) / np.dot(u, u)) > 1e-10:
            return Intersection("empty")
        if not segments:
            return Intersection("coincident", origin=tuple(a), direction=tuple(u))
        q = sorted(
            (
                float(np.dot(b - a, u) / np.dot(u, u)),
                float(np.dot(b + v - a, u) / np.dot(u, u)),
            )
        )
        lo, hi = max(0, q[0]), min(1, q[1])
        return (
            Intersection("empty")
            if lo > hi
            else Intersection(
                "points" if lo == hi else "segment",
                points=(tuple(a + lo * u), tuple(a + hi * u)),
            )
        )
    if np.linalg.norm(a + ts[0] * u - b - ts[1] * v) > 1e-10:
        return Intersection("empty")
    if segments and not all(0 <= t <= 1 for t in ts):
        return Intersection("empty")
    return Intersection("points", (tuple(a + ts[0] * u),))


def segment_segment(a, b, c, d):
    a, b, c, d = (np.array(p, float) for p in (a, b, c, d))
    return line_line(a, b - a, c, d - c, True)


def line_plane(a, u, p, n):
    a, u, p, n = (np.array(v, float) for v in (a, u, p, n))
    if np.linalg.norm(u) == 0 or np.linalg.norm(n) == 0:
        raise ValueError("direction and normal must be nonzero")
    den = np.dot(u, n)
    num = np.dot(p - a, n)
    if abs(den) < 1e-12:
        return Intersection("coincident" if abs(num) < 1e-12 else "empty")
    return Intersection("points", (tuple(a + u * num / den),))


def plane_plane(a, n, b, m):
    a, n, b, m = (np.array(v, float) for v in (a, n, b, m))
    if np.linalg.norm(n) == 0 or np.linalg.norm(m) == 0:
        raise ValueError("normals must be nonzero")
    d = np.cross(n, m)
    if np.linalg.norm(d) < 1e-12:
        return Intersection("coincident" if abs(np.dot(b - a, n)) < 1e-12 else "empty")
    p = np.linalg.lstsq(np.array([n, m]), np.array([n @ a, m @ b]), rcond=None)[0]
    return Intersection("line", origin=tuple(p), direction=tuple(d / np.linalg.norm(d)))


def line_sphere(a, u, c, r):
    a, u, c = (np.array(v, float) for v in (a, u, c))
    if r < 0 or np.dot(u, u) == 0:
        raise ValueError("invalid sphere or line")
    d = a - c
    A = u @ u
    B = 2 * (u @ d)
    C = d @ d - r * r
    disc = B * B - 4 * A * C
    if disc < -1e-12:
        return Intersection("empty")
    ts = (
        [-B / (2 * A)]
        if abs(disc) < 1e-12
        else [(-B + t * np.sqrt(disc)) / (2 * A) for t in (-1, 1)]
    )
    return Intersection("points", tuple(tuple(a + t * u) for t in ts))


def line_circle(a, u, c, r, normal=None):
    if len(a) == 2:
        return line_sphere(a, u, c, r)
    if normal is None:
        raise ValueError("a spatial circle requires a plane normal")
    hit = line_plane(a, u, c, normal)
    if hit.kind == "coincident":
        return line_sphere(a, u, c, r)
    if hit.points and abs(np.linalg.norm(np.array(hit.points[0]) - c) - r) < 1e-10:
        return hit
    return Intersection("empty")


def sphere_sphere(a, r, b, R):
    a, b = (np.array(v, float) for v in (a, b))
    d = b - a
    length = np.linalg.norm(d)
    if min(r, R) < 0:
        raise ValueError("radii must be nonnegative")
    if length < 1e-12:
        return Intersection("coincident" if r == R else "empty")
    if length > r + R + 1e-12 or length < abs(r - R) - 1e-12:
        return Intersection("empty")
    k = (r * r - R * R + length * length) / (2 * length)
    p = a + k * d / length
    radius = np.sqrt(max(0, r * r - k * k))
    return (
        Intersection("points", (tuple(p),))
        if radius < 1e-12
        else Intersection(
            "circle", origin=tuple(p), direction=tuple(d / length), radius=float(radius)
        )
    )


def plane_sphere(p, n, c, r):
    p, n, c = (np.array(v, float) for v in (p, n, c))
    length = np.linalg.norm(n)
    if length == 0 or r < 0:
        raise ValueError("invalid plane or sphere")
    n = n / length
    distance = np.dot(c - p, n)
    center = c - distance * n
    if abs(distance) > r + 1e-12:
        return Intersection("empty")
    radius = np.sqrt(max(0, r * r - distance * distance))
    return (
        Intersection("points", (tuple(center),))
        if radius < 1e-12
        else Intersection(
            "circle", origin=tuple(center), direction=tuple(n), radius=float(radius)
        )
    )


@dataclass(frozen=True)
class Line:
    origin: tuple[float, ...]
    direction: tuple[float, ...]


@dataclass(frozen=True)
class Segment:
    start: tuple[float, ...]
    end: tuple[float, ...]


@dataclass(frozen=True)
class Circle:
    center: tuple[float, ...]
    radius: float
    normal: tuple[float, float, float] = (0, 0, 1)


@dataclass(frozen=True)
class Plane:
    origin: tuple[float, float, float]
    normal: tuple[float, float, float]


@dataclass(frozen=True)
class Sphere:
    center: tuple[float, float, float]
    radius: float


Geometry = Line | Segment | Circle | Plane | Sphere


def intersect(a: Geometry, b: Geometry) -> Intersection:
    """Intersect immutable construction primitives; unsupported pairs fail explicitly."""
    if isinstance(a, Line) and isinstance(b, Line):
        return line_line(a.origin, a.direction, b.origin, b.direction)
    if isinstance(a, Segment) and isinstance(b, Segment):
        return segment_segment(a.start, a.end, b.start, b.end)
    if isinstance(a, Circle) and isinstance(b, Circle):
        if a.normal != (0, 0, 1) or b.normal != (0, 0, 1):
            raise NotImplementedError("circle-circle currently supports the XY plane")
        return circle_circle(a.center, a.radius, b.center, b.radius)
    if isinstance(a, Plane) and isinstance(b, Plane):
        return plane_plane(a.origin, a.normal, b.origin, b.normal)
    if isinstance(a, Sphere) and isinstance(b, Sphere):
        return sphere_sphere(a.center, a.radius, b.center, b.radius)
    if isinstance(a, Line) and isinstance(b, Circle):
        return line_circle(a.origin, a.direction, b.center, b.radius, b.normal)
    if isinstance(a, Line) and isinstance(b, Plane):
        return line_plane(a.origin, a.direction, b.origin, b.normal)
    if isinstance(a, Line) and isinstance(b, Sphere):
        return line_sphere(a.origin, a.direction, b.center, b.radius)
    if isinstance(a, Plane) and isinstance(b, Sphere):
        return plane_sphere(a.origin, a.normal, b.center, b.radius)
    if (isinstance(b, Line) and isinstance(a, (Circle, Plane, Sphere))) or (
        isinstance(b, Plane) and isinstance(a, Sphere)
    ):
        return intersect(b, a)
    raise NotImplementedError(
        f"unsupported intersection: {type(a).__name__} / {type(b).__name__}"
    )
