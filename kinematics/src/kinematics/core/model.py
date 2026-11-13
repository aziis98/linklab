"""Serializable construction DSL. Geometry is immutable; only point embeddings move."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

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
    local: Vec | None = field(default=None, compare=False)

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


class FrameKind(StrEnum):
    FULL = "full"
    AXIAL_X = "axial_x"


@dataclass
class RigidBody(SourceInfo):
    id: str
    points: dict[str, tuple[Scalar, ...]]
    fixed: bool = False
    kind: str = "body"
    dimension: int | None = 2
    frame_kind: FrameKind = FrameKind.FULL
    relative_points: dict[str, tuple[Scalar, ...]] = field(default_factory=dict)
    affine_points: dict[str, dict[str, Scalar | tuple]] = field(default_factory=dict)

    point_labels: dict[str, str] = field(default_factory=dict)

    @property
    def material_names(self) -> list[str]:
        return [n for n in self.points if n not in self.affine_points]

    def relative_name(self, local: tuple[Scalar, ...]) -> str:
        return f"rel{len(self.relative_points)}"

    @property
    def render_names(self) -> list[str]:
        if self.kind == "rod":
            return ["a", "b"]
        if self.kind == "ring":
            return ["origin", "x", "y"]
        return self.material_names

    @property
    def metric_names(self) -> list[str]:
        if self.kind == "rod":
            return ["a", "b"] + (
                ["frame_y", "frame_z"] if "frame_z" in self.points else []
            )
        if self.kind == "ring":
            return ["origin", "x", "y"]
        return self.material_names

    def frame(self) -> tuple[sp.Matrix, sp.Matrix]:
        center = sp.Matrix(self.points["origin"])
        axes = [sp.Matrix(self.points[n]) - center for n in ("x", "y")]
        if self.dimension == 3:
            axes.append(sp.Matrix(self.points["z"]) - center)
        else:
            axes.append(sp.Matrix([0, 0, 1]))
        return center, sp.Matrix.hstack(*axes)

    def relative(
        self,
        x: Vec | Sequence[Scalar] | Scalar = 0,
        y: Scalar = 0,
        z: Scalar = 0,
        *,
        label: str | None = None,
    ) -> PointRef:
        local = coords(x if isinstance(x, (Vec, tuple, list)) else Vec(x, y, z))
        if self.dimension == 2 and local[2] != 0:
            raise ValueError("2D relative points must lie in local XY")
        center, axes = self.frame()
        if (
            self.frame_kind == FrameKind.AXIAL_X
            and self.dimension != 2
            and (local[1] != 0 or local[2] != 0)
        ):
            raise ValueError("off-axis points require rod(..., frame='full')")
        world = tuple(sp.simplify(v) for v in center + axes * sp.Matrix(local))
        for name, position in self.points.items():
            if all(sp.simplify(a - b) == 0 for a, b in zip(position, world)):
                if label is not None:
                    self.point_labels[name] = label
                return PointRef(self.id, name, Vec(*position), Vec(*local))
        if local[2] != 0 and self.kind == "ring" and "frame_z" not in self.points:
            self.points["frame_z"] = tuple(center + axes[:, 2])
        name = self.relative_name(local)
        while name in self.points:
            name += "_"
        names = self.material_names
        matrix = sp.Matrix([[*self.points[n], 1] for n in names]).T
        if self.frame_kind == FrameKind.AXIAL_X and self.dimension == 2:
            length = sp.sqrt(
                sum((a - b) ** 2 for a, b in zip(self.points["a"], self.points["b"]))
            )
            rotation = sp.Matrix([[0, -1, 0], [1, 0, 0], [0, 0, 0]])
            offset = (local[0] * sp.eye(3) + local[1] * rotation) / length
            weights = {
                n: tuple(
                    tuple(v for v in row)
                    for row in (sp.eye(3) / 2 + sign * offset).tolist()
                )
                for n, sign in (("a", -1), ("b", 1))
            }
        else:
            solution, parameters = matrix.gauss_jordan_solve(sp.Matrix([*world, 1]))
            solution = solution.subs(dict.fromkeys(parameters, 0))
            weights = {n: sp.simplify(w) for n, w in zip(names, solution) if w != 0}
        self.points[name] = world
        if label is not None:
            self.point_labels[name] = label
        self.relative_points[name] = local
        self.affine_points[name] = weights
        return PointRef(self.id, name, Vec(*world), Vec(*local))

    rel = relative

    def point(self, name: str) -> PointRef:
        if name == "bottom" and self.kind == "ring" and name not in self.points:
            return self.bottom
        return PointRef(self.id, name, Vec(*self.points[name]))

    def axis(self, name: str = "x") -> tuple[PointRef, PointRef]:
        return (
            (self.start, self.end)
            if self.kind == "rod"
            else (self.origin, self.point(name))
        )

    @property
    def origin(self) -> PointRef:
        return self.rel(0)

    @property
    def center(self) -> PointRef:
        return self.origin


@dataclass
class Rod(RigidBody):
    frame_kind: FrameKind = FrameKind.AXIAL_X

    @property
    def length(self) -> sp.Expr:
        return sp.sqrt(
            sum((a - b) ** 2 for a, b in zip(self.points["a"], self.points["b"]))
        )

    def frame(self) -> tuple[sp.Matrix, sp.Matrix]:
        a, b = sp.Matrix(self.points["a"]), sp.Matrix(self.points["b"])
        center = (a + b) / 2
        x = (b - a) / self.length
        if self.frame_kind == FrameKind.FULL:
            y = sp.Matrix(self.points["frame_y"]) - center
        else:
            y = sp.Matrix([-x[1], x[0], 0]) if self.dimension == 2 else sp.zeros(3, 1)
        return center, sp.Matrix.hstack(x, y, x.cross(y))

    @property
    def start(self) -> PointRef:
        return self.rel(-self.length / 2)

    @property
    def end(self) -> PointRef:
        return self.rel(self.length / 2)


class Ring(RigidBody):
    def relative_name(self, local: tuple[Scalar, ...]) -> str:
        return (
            "bottom" if local == (0, -self.radius, 0) else super().relative_name(local)
        )

    @property
    def radius(self) -> sp.Expr:
        return sp.sqrt(
            sum((a - b) ** 2 for a, b in zip(self.points["x"], self.points["origin"]))
        )

    def frame(self) -> tuple[sp.Matrix, sp.Matrix]:
        center = sp.Matrix(self.points["origin"])
        x, y = [(sp.Matrix(self.points[n]) - center) / self.radius for n in ("x", "y")]
        return center, sp.Matrix.hstack(x, y, x.cross(y))

    @property
    def top(self) -> PointRef:
        return self.rel(0, self.radius)

    @property
    def bottom(self) -> PointRef:
        return self.rel(0, -self.radius)


# Compatibility for library clients and serialized scenes.
RigidObject = RigidBody


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
        for obj in self.objects:
            obj.dimension = self.dimension
            if (
                self.dimension == 3
                and obj.frame_kind == FrameKind.AXIAL_X
                and any(p[1] != 0 or p[2] != 0 for p in obj.relative_points.values())
            ):
                raise ValueError("off-axis points require rod(..., frame='full') in 3D")
            if (
                self.dimension == 3
                and isinstance(obj, Rod)
                and obj.frame_kind == FrameKind.FULL
            ):
                center, axes = obj.frame()
                obj.points.setdefault("frame_z", tuple(center + axes[:, 2]))
        if self.dimension == 2:
            if any(p[2] != 0 for o in self.objects for p in o.points.values()):
                raise ValueError("a 2D scene must lie in the XY plane")
            if any(c.kind == "pin" and c.value[2] != 0 for c in self.constraints):
                raise ValueError("a 2D anchor must lie in the XY plane")
        else:
            for obj in self.objects:
                if obj.kind == "body":
                    obj.points.setdefault(
                        "z", coords(Vec(*obj.points["origin"]) + Vec(0, 0, 1))
                    )

    def rod(
        self,
        a: Vec | PointRef | Sequence[Scalar],
        b: Vec | PointRef | Sequence[Scalar],
        id: str | None = None,
        fixed: bool = False,
        frame: str = "axial",
        normal: Vec | Sequence[Scalar] | None = None,
    ) -> RigidObject:
        ident = id or f"r{len(self.objects) + 1}"
        if any(o.id == ident for o in self.objects):
            raise ValueError(f"duplicate object: {ident}")
        points = {"a": coords(a), "b": coords(b)}
        if points["a"] == points["b"]:
            raise ValueError("rod endpoints must differ")
        if self.dimension == 2 and any(p[2] != 0 for p in points.values()):
            raise ValueError("use dimension=3 for spatial geometry")
        if frame not in ("axial", "full"):
            raise ValueError("frame must be 'axial' or 'full'")
        obj = Rod(
            ident,
            points,
            fixed,
            "rod",
            self.dimension or (3 if any(p[2] != 0 for p in points.values()) else 2),
            FrameKind.AXIAL_X,
        )
        if frame == "full":
            obj.frame_kind = FrameKind.FULL
            a0, b0 = sp.Matrix(points["a"]), sp.Matrix(points["b"])
            x = (b0 - a0) / obj.length
            n = (
                sp.Matrix(coords(normal))
                if normal is not None
                else next(
                    v
                    for v in (sp.Matrix([0, 0, 1]), sp.Matrix([0, 1, 0]))
                    if x.cross(v).norm() != 0
                )
            )
            y = n.cross(x)
            if y.norm() == 0:
                raise ValueError("normal must not be parallel to the rod")
            y = y / y.norm()
            center = (a0 + b0) / 2
            points["frame_y"] = tuple(center + y)
            if obj.dimension != 2:
                points["frame_z"] = tuple(center + x.cross(y))
        self.objects.append(obj)
        return obj

    def body(
        self,
        points: dict[str, Vec | Sequence[Scalar]],
        id: str | None = None,
        fixed: bool = False,
        center: Vec | Sequence[Scalar] = (0, 0, 0),
    ) -> RigidObject:
        ident = id or f"body{len(self.objects) + 1}"
        if any(o.id == ident for o in self.objects):
            raise ValueError(f"duplicate object: {ident}")
        # A rigid simplex supplies an observable material frame.
        c = vec(center)
        base = {
            "origin": coords(c),
            "x": coords(c + Vec(1)),
            "y": coords(c + Vec(0, 1)),
        }
        if self.dimension == 3:
            base["z"] = coords(c + Vec(0, 0, 1))
        if set(points) & {"origin", "x", "y", "z"}:
            raise ValueError("material frame names are reserved: origin, x, y, z")
        base.update({k: coords(v) for k, v in points.items()})
        if self.dimension == 2 and any(p[2] != 0 for p in base.values()):
            raise ValueError("use dimension=3 for spatial geometry")
        obj = RigidBody(ident, base, fixed, dimension=self.dimension)
        self.objects.append(obj)
        return obj

    def ring(
        self, center, radius, id=None, fixed=False, normal=(0, 0, 1)
    ) -> RigidObject:
        radius = exact(radius)
        if radius <= 0:
            raise ValueError("ring radius must be positive")
        center = vec(center)
        ident = id or f"ring{len(self.objects) + 1}"
        if any(o.id == ident for o in self.objects):
            raise ValueError(f"duplicate object: {ident}")
        n = sp.Matrix(coords(normal))
        if n.norm() == 0:
            raise ValueError("ring normal must be nonzero")
        n = n / n.norm()
        seed = next(
            v
            for v in (sp.Matrix([1, 0, 0]), sp.Matrix([0, 1, 0]))
            if n.cross(v).norm() != 0
        )
        x = seed - n * seed.dot(n)
        x = x / x.norm()
        y = n.cross(x)
        points = {
            "origin": coords(center),
            "x": coords(center + Vec(*(radius * x))),
            "y": coords(center + Vec(*(radius * y))),
        }
        if self.dimension == 2 and any(p[2] != 0 for p in points.values()):
            raise ValueError("use dimension=3 for spatial geometry")
        obj = Ring(
            ident,
            points,
            fixed,
            "ring",
            self.dimension or (3 if any(p[2] != 0 for p in points.values()) else 2),
        )
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
                    "frame_kind": o.frame_kind.value,
                    "point_labels": o.point_labels,
                    "relative_points": {
                        n: encode(p) for n, p in o.relative_points.items()
                    },
                    "affine_points": {
                        n: {k: encode(w) for k, w in weights.items()}
                        for n, weights in o.affine_points.items()
                    },
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
            body_type = {"rod": Rod, "ring": Ring}.get(o["kind"], RigidBody)
            obj = body_type(
                o["id"],
                {n: tuple(exact(v) for v in p) for n, p in o["points"].items()},
                o["fixed"],
                o["kind"],
                scene.dimension,
                FrameKind(
                    o.get("frame_kind", "axial_x" if o["kind"] == "rod" else "full")
                ),
                {
                    n: tuple(exact(v) for v in p)
                    for n, p in o.get("relative_points", {}).items()
                },
                {
                    n: {
                        k: tuple(tuple(exact(v) for v in row) for row in w)
                        if isinstance(w, list)
                        else exact(w)
                        for k, w in weights.items()
                    }
                    for n, weights in o.get("affine_points", {}).items()
                },
            )
            obj.point_labels = dict(o.get("point_labels", {}))
            if (
                obj.kind == "ring"
                and "bottom" in obj.points
                and "bottom" not in obj.affine_points
            ):
                obj.affine_points["bottom"] = {"origin": 2, "y": -1}
            if o.get("source_span"):
                obj.source_span = tuple(o["source_span"])
            scene.objects.append(obj)

        def decode(value):
            if isinstance(value, list):
                return tuple(decode(v) for v in value)
            return exact(value)

        for c in data["constraints"]:
            value = tuple(c["value"]) if c["kind"] == "parallel" else decode(c["value"])
            constraint = Constraint(c["kind"], c["a"], c["b"], value, c["id"])
            if c.get("source_span"):
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
