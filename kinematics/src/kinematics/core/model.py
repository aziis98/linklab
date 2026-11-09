"""Serializable construction DSL. Geometry is immutable; only point embeddings move."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import functools
import inspect

import sympy as sp

Scalar = int | float | sp.Expr


@dataclass(frozen=True)
class Vec:
    x: Scalar = 0
    y: Scalar = 0
    z: Scalar = 0

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __add__(self, other):
        return Vec(*(a + b for a, b in zip(self, vec(other))))

    def __sub__(self, other):
        return Vec(*(a - b for a, b in zip(self, vec(other))))

    def __mul__(self, scalar):
        return Vec(*(a * scalar for a in self))

    __rmul__ = __mul__

    def __truediv__(self, scalar):
        return self * (sp.S.One / scalar)

    def __neg__(self):
        return self * -1


def vec(value: Vec | PointRef | Sequence[Scalar]) -> Vec:
    if isinstance(value, PointRef):
        return value.pos
    if isinstance(value, Vec):
        return value
    values = list(value)
    return Vec(*values)


def exact(value: Scalar | str) -> sp.Expr:
    result = sp.sympify(value)
    return result.xreplace({f: sp.Rational(str(f)) for f in result.atoms(sp.Float)})


def coords(value: Vec | PointRef | Sequence[Scalar]) -> tuple[sp.Expr, ...]:
    return tuple(exact(v) for v in vec(value))


@dataclass(frozen=True)
class PointRef:
    object_id: str
    name: str
    pos: Vec

    def __add__(self, other):
        return self.pos + other

    def __sub__(self, other):
        return self.pos - other

    def __iter__(self):
        return iter(self.pos)

    @property
    def key(self):
        return f"{self.object_id}:{self.name}"


class SourceInfo:
    source_span: tuple[int, int, int, int] | None = None


def get_current_source_span() -> tuple[int, int, int, int] | None:
    f = inspect.currentframe()
    if not f:
        return None
    f = f.f_back
    while f and f.f_code.co_filename != "<scene>":
        f = f.f_back
    if not f or f.f_code.co_filename != "<scene>":
        return None
    positions = list(f.f_code.co_positions())
    idx = f.f_lasti // 2
    if 0 <= idx < len(positions):
        pos = positions[idx]
        if pos[0] is not None and pos[2] is not None:
            return (
                pos[0],
                pos[1] if pos[1] is not None else pos[0],
                pos[2],
                pos[3] if pos[3] is not None else pos[2],
            )
    return None


def track_source(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        span = get_current_source_span()
        res = func(*args, **kwargs)
        if span is not None:
            if isinstance(res, SourceInfo):
                res.source_span = span
            elif isinstance(res, (tuple, list)):
                for item in res:
                    if isinstance(item, SourceInfo):
                        item.source_span = span
        return res

    return wrapper


@dataclass
class RigidObject(SourceInfo):
    id: str
    points: dict[str, tuple[Scalar, ...]]
    fixed: bool = False
    kind: str = "body"

    def point(self, name: str) -> PointRef:
        if self.kind == "ring" and name == "bottom" and name not in self.points:
            self.points[name] = tuple(
                2 * c - top for c, top in zip(self.points["origin"], self.points["y"])
            )
        return PointRef(self.id, name, Vec(*self.points[name]))

    def axis(self, name: str = "x") -> tuple[PointRef, PointRef]:
        return (
            (self.start, self.end)
            if self.kind == "rod"
            else (self.point("origin"), self.point(name))
        )

    @property
    def top(self):
        return self.point("y")

    @property
    def bottom(self):
        return self.point("bottom")

    @property
    def center(self):
        return self.point("origin")

    @property
    def start(self):
        return self.point("a")

    @property
    def end(self):
        return self.point("b")


@dataclass
class Constraint(SourceInfo):
    kind: str
    a: str
    b: str | None = None
    value: Scalar | tuple = ()
    id: str = ""


@dataclass
class Scene:
    objects: list[RigidObject] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    dimension: int | None = 2

    def __post_init__(self):
        if self.dimension not in (None, 2, 3):
            raise ValueError("dimension must be 2 or 3")

    def resolve_dimension(self, override: int | None = None) -> None:
        if override is not None:
            self.dimension = override
        if self.dimension is None:
            spatial = any(p[2] != 0 for o in self.objects for p in o.points.values())
            spatial |= any(
                c.kind == "pin" and c.value[2] != 0 for c in self.constraints
            )
            self.dimension = 3 if spatial else 2
        if self.dimension not in (2, 3):
            raise ValueError("dimension must be 2 or 3")
        if self.dimension == 2:
            if any(p[2] != 0 for o in self.objects for p in o.points.values()):
                raise ValueError("a 2D scene must lie in the XY plane")
            if any(c.kind == "pin" and c.value[2] != 0 for c in self.constraints):
                raise ValueError("a 2D anchor must lie in the XY plane")
        else:
            for obj in self.objects:
                if obj.kind == "body":
                    obj.points.setdefault("z", (0, 0, 1))

    def rod(
        self,
        a: Vec | PointRef | Sequence[Scalar],
        b: Vec | PointRef | Sequence[Scalar],
        id: str | None = None,
        fixed: bool = False,
    ) -> RigidObject:
        ident = id or f"r{len(self.objects) + 1}"
        if any(o.id == ident for o in self.objects):
            raise ValueError(f"duplicate object: {ident}")
        points = {"a": coords(a), "b": coords(b)}
        if points["a"] == points["b"]:
            raise ValueError("rod endpoints must differ")
        if self.dimension == 2 and any(p[2] != 0 for p in points.values()):
            raise ValueError("use dimension=3 for spatial geometry")
        obj = RigidObject(ident, points, fixed, "rod")
        self.objects.append(obj)
        return obj

    def body(
        self,
        points: dict[str, Vec | Sequence[Scalar]],
        id: str | None = None,
        fixed: bool = False,
    ) -> RigidObject:
        ident = id or f"body{len(self.objects) + 1}"
        if any(o.id == ident for o in self.objects):
            raise ValueError(f"duplicate object: {ident}")
        # A rigid simplex supplies an observable material frame.
        base = {"origin": (0, 0, 0), "x": (1, 0, 0), "y": (0, 1, 0)}
        if self.dimension == 3:
            base["z"] = (0, 0, 1)
        if set(points) & {"origin", "x", "y", "z"}:
            raise ValueError("material frame names are reserved: origin, x, y, z")
        base.update({k: coords(v) for k, v in points.items()})
        if self.dimension == 2 and any(p[2] != 0 for p in base.values()):
            raise ValueError("use dimension=3 for spatial geometry")
        obj = RigidObject(ident, base, fixed)
        self.objects.append(obj)
        return obj

    def ring(self, center, radius, id=None, fixed=False) -> RigidObject:
        radius = exact(radius)
        if radius <= 0:
            raise ValueError("ring radius must be positive")
        center = vec(center)
        ident = id or f"ring{len(self.objects) + 1}"
        if any(o.id == ident for o in self.objects):
            raise ValueError(f"duplicate object: {ident}")
        points = {
            "origin": coords(center),
            "x": coords(center + Vec(radius, 0, 0)),
            "y": coords(center + Vec(0, radius, 0)),
        }
        if self.dimension == 2 and any(p[2] != 0 for p in points.values()):
            raise ValueError("use dimension=3 for spatial geometry")
        obj = RigidObject(ident, points, fixed, "ring")
        self.objects.append(obj)
        return obj

    def coincident(self, a, b, id=None):
        if not isinstance(a, PointRef):
            a, b = b, a
        if not isinstance(a, PointRef):
            raise TypeError("a constraint must reference an object")
        if not isinstance(b, PointRef) and self.dimension == 2 and coords(b)[2] != 0:
            raise ValueError("use dimension=3 for spatial anchors")
        c = Constraint(
            "coincident" if isinstance(b, PointRef) else "pin",
            a.key,
            b.key if isinstance(b, PointRef) else None,
            () if isinstance(b, PointRef) else coords(b),
            id or f"j{len(self.constraints) + 1}",
        )
        self.constraints.append(c)
        return c

    def pin(self, a, pos=None, id=None):
        return self.coincident(a, a.pos if pos is None else pos, id)

    def distance(
        self, a: PointRef, b: PointRef, length: Scalar, id: str | None = None
    ) -> Constraint:
        if exact(length) < 0:
            raise ValueError("distance must be nonnegative")
        c = Constraint(
            "distance",
            a.key,
            b.key,
            exact(length) ** 2,
            id or f"d{len(self.constraints) + 1}",
        )
        self.constraints.append(c)
        return c

    def fixed(self, obj: RigidObject) -> None:
        obj.fixed = True

    def parallel(
        self,
        a: tuple[PointRef, PointRef],
        b: tuple[PointRef, PointRef],
        id: str | None = None,
    ) -> Constraint:
        c = Constraint(
            "parallel",
            a[0].key,
            a[1].key,
            (b[0].key, b[1].key),
            id or f"a{len(self.constraints) + 1}",
        )
        self.constraints.append(c)
        return c

    def to_dict(self):
        def encode(value):
            if isinstance(value, (tuple, list)):
                return [encode(v) for v in value]
            return str(value)

        return {
            "dimension": self.dimension,
            "objects": [
                {
                    "id": o.id,
                    "kind": o.kind,
                    "fixed": o.fixed,
                    "points": {n: encode(p) for n, p in o.points.items()},
                    **({"source_span": list(o.source_span)} if o.source_span else {}),
                }
                for o in self.objects
            ],
            "constraints": [
                {
                    "id": c.id,
                    "kind": c.kind,
                    "a": c.a,
                    "b": c.b,
                    "value": encode(c.value),
                    **({"source_span": list(c.source_span)} if c.source_span else {}),
                }
                for c in self.constraints
            ],
        }

    @classmethod
    def from_dict(cls, data):
        scene = cls(dimension=data["dimension"])
        for o in data["objects"]:
            obj = RigidObject(
                o["id"],
                {n: tuple(exact(v) for v in p) for n, p in o["points"].items()},
                o["fixed"],
                o["kind"],
            )
            if "source_span" in o and o["source_span"]:
                obj.source_span = tuple(o["source_span"])
            scene.objects.append(obj)

        def decode(value):
            if isinstance(value, list):
                return tuple(decode(v) for v in value)
            return exact(value)

        for c in data["constraints"]:
            value = tuple(c["value"]) if c["kind"] == "parallel" else decode(c["value"])
            constraint = Constraint(c["kind"], c["a"], c["b"], value, c["id"])
            if "source_span" in c and c["source_span"]:
                constraint.source_span = tuple(c["source_span"])
            scene.constraints.append(constraint)
        return scene

    def plane(self, target, origin=(0, 0, 0), normal=(0, 0, 1), id=None):
        """Constrain a point, rod, or body's material XY plane to a world plane."""
        if isinstance(target, PointRef):
            return self.point_on_plane(target, origin, normal, id)
        if not isinstance(target, RigidObject):
            raise TypeError("plane requires a point or rigid object")
        names = ("a", "b") if target.kind == "rod" else ("origin", "x", "y")
        return tuple(
            self.point_on_plane(
                target.point(name), origin, normal, f"{id}:{name}" if id else None
            )
            for name in names
        )

    def point_on_plane(self, point, origin, normal, id=None):
        n = coords(normal)
        if sum(v * v for v in n) == 0:
            raise ValueError("plane normal must be nonzero")
        c = Constraint(
            "plane",
            point.key,
            None,
            (coords(origin), n),
            id or f"p{len(self.constraints) + 1}",
        )
        self.constraints.append(c)
        return c


origin = Vec()
right = Vec(1, 0, 0)
left = -right
up = Vec(0, 1, 0)
down = -up
forward = Vec(0, 0, 1)
backward = -forward


def sqrt(value):
    return sp.sqrt(exact(value))


def range_circle(
    count: int,
    radius: Scalar = 1,
    center: Vec | Sequence[Scalar] | None = None,
    u: Vec | Sequence[Scalar] | None = None,
    v: Vec | Sequence[Scalar] | None = None,
) -> list[Vec]:
    """Generates `count` points evenly spaced on a circle."""
    c = origin if center is None else vec(center)
    dir_u = right if u is None else vec(u)
    dir_v = forward if v is None else vec(v)
    r = exact(radius)
    return [
        c
        + dir_u * (r * sp.cos(2 * sp.pi * i / count))
        + dir_v * (r * sp.sin(2 * sp.pi * i / count))
        for i in range(count)
    ]


def build_scene(source: str, dimension: int | None = None) -> Scene:
    scene = Scene(dimension=dimension)

    def scene_dimension(value: int) -> None:
        if value not in (2, 3):
            raise ValueError("scene_dimension must be 2 or 3")
        scene.dimension = value

    env = {
        name: globals()[name]
        for name in (
            "Vec",
            "origin",
            "right",
            "left",
            "up",
            "down",
            "forward",
            "backward",
            "sqrt",
            "range_circle",
        )
    }
    from itertools import cycle, islice

    env["cycle"] = cycle
    env["islice"] = islice
    from .geometry import Circle, Line, Plane, Segment, Sphere, intersect

    env.update(
        Circle=Circle,
        Line=Line,
        Plane=Plane,
        Segment=Segment,
        Sphere=Sphere,
        intersect=intersect,
    )
    env.update(
        scene=scene,
        rod=track_source(scene.rod),
        ring=track_source(scene.ring),
        body=track_source(scene.body),
        pin=track_source(scene.pin),
        coincident=track_source(scene.coincident),
        constraint_point_point=track_source(scene.coincident),
        distance=track_source(scene.distance),
        fixed=scene.fixed,
        point_on_plane=track_source(scene.point_on_plane),
        plane=track_source(scene.plane),
        scene_dimension=scene_dimension,
        parallel=track_source(scene.parallel),
    )
    exec(compile(source, "<scene>", "exec"), env)  # noqa: S102 -- scene scripts intentionally execute Python
    scene.resolve_dimension(dimension)
    return scene
