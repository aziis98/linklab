"""Simple DSL for rod constructions with point joints in SE(3)."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

__all__ = [
    "SE3",
    "Entity",
    "Joint",
    "Model",
    "PointRef",
    "Rod",
    "Vec",
    "analyze_mobility",
    "constraint_point_point",
    "default_model",
    "down",
    "export_json",
    "joint",
    "left",
    "origin",
    "reset",
    "right",
    "rod",
    "solve",
    "up",
]

Vector3 = list[float]
Matrix3 = list[list[float]]


def _vec3(p: Any) -> Vector3:
    if isinstance(p, PointRef):
        return p.pos
    if isinstance(p, Vec):
        return [p.x, p.y, p.z]
    if isinstance(p, (int, float)):
        return [float(p), 0.0, 0.0]
    p_seq = list(p)
    if len(p_seq) == 2:
        return [float(p_seq[0]), float(p_seq[1]), 0.0]
    return [float(p_seq[0]), float(p_seq[1]), float(p_seq[2])]


class Vec:
    """3D vector with standard 2D/3D operator arithmetic."""

    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __add__(self, other: Any) -> Vec:
        ov = _vec3(other)
        return Vec(self.x + ov[0], self.y + ov[1], self.z + ov[2])

    def __radd__(self, other: Any) -> Vec:
        return self.__add__(other)

    def __sub__(self, other: Any) -> Vec:
        ov = _vec3(other)
        return Vec(self.x - ov[0], self.y - ov[1], self.z - ov[2])

    def __rsub__(self, other: Any) -> Vec:
        ov = _vec3(other)
        return Vec(ov[0] - self.x, ov[1] - self.y, ov[2] - self.z)

    def __mul__(self, scalar: float) -> Vec:
        s = float(scalar)
        return Vec(self.x * s, self.y * s, self.z * s)

    def __rmul__(self, scalar: float) -> Vec:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vec:
        s = float(scalar)
        return Vec(self.x / s, self.y / s, self.z / s)

    def __neg__(self) -> Vec:
        return Vec(-self.x, -self.y, -self.z)

    def __getitem__(self, idx: int) -> float:
        if idx == 0:
            return self.x
        if idx == 1:
            return self.y
        if idx == 2:
            return self.z
        raise IndexError("Vec index out of range")

    def __len__(self) -> int:
        return 3

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z

    def __repr__(self) -> str:
        if abs(self.z) < 1e-9:
            return f"Vec({self.x:g}, {self.y:g})"
        return f"Vec({self.x:g}, {self.y:g}, {self.z:g})"


origin = Vec(0.0, 0.0, 0.0)
right = Vec(1.0, 0.0, 0.0)
left = Vec(-1.0, 0.0, 0.0)
up = Vec(0.0, 1.0, 0.0)
down = Vec(0.0, -1.0, 0.0)


class SE3:
    """Rigid transform in SE(3) represented by translation and 3x3 rotation."""

    def __init__(
        self, pos: Sequence[float] = (0.0, 0.0, 0.0), rot: Matrix3 | None = None
    ) -> None:
        self.pos: Vector3 = _vec3(pos)
        self.rot: Matrix3 = (
            [row[:] for row in rot]
            if rot is not None
            else [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        )

    @classmethod
    def identity(cls) -> SE3:
        return cls()

    @classmethod
    def from_translation(cls, x: float, y: float, z: float = 0.0) -> SE3:
        return cls([x, y, z])

    @classmethod
    def from_endpoints(
        cls, p1: Sequence[float], p2: Sequence[float]
    ) -> tuple[SE3, float]:
        """Align local X-axis from p1 to p2, origin at midpoint."""
        v1, v2 = _vec3(p1), _vec3(p2)
        dx, dy, dz = v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-12:
            raise ValueError("Endpoints must not be coincident")

        midpoint = [(v1[0] + v2[0]) / 2.0, (v1[1] + v2[1]) / 2.0, (v1[2] + v2[2]) / 2.0]
        # Minimal rotation aligning (1, 0, 0) with d = (dx, dy, dz) / length
        d = [dx / length, dy / length, dz / length]
        c = d[0]  # dot product with (1, 0, 0)

        if c > 0.9999999:
            rot = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        elif c < -0.9999999:
            rot = [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]]
        else:
            # v = (1, 0, 0) x d = (0, -dz, dy)
            vx, vy, vz = 0.0, -d[2], d[1]
            factor = 1.0 / (1.0 + c)
            rot = [
                [
                    1.0 - factor * (vy * vy + vz * vz),
                    -vz + factor * vx * vy,
                    vy + factor * vx * vz,
                ],
                [
                    vz + factor * vx * vy,
                    1.0 - factor * (vx * vx + vz * vz),
                    -vx + factor * vy * vz,
                ],
                [
                    -vy + factor * vx * vz,
                    vx + factor * vy * vz,
                    1.0 - factor * (vx * vx + vy * vy),
                ],
            ]

        return cls(midpoint, rot), length

    def apply(self, p: Sequence[float]) -> Vector3:
        """Transform local point to world."""
        v = _vec3(p)
        r = self.rot
        return [
            self.pos[0] + r[0][0] * v[0] + r[0][1] * v[1] + r[0][2] * v[2],
            self.pos[1] + r[1][0] * v[0] + r[1][1] * v[1] + r[1][2] * v[2],
            self.pos[2] + r[2][0] * v[0] + r[2][1] * v[1] + r[2][2] * v[2],
        ]

    def to_dict(self) -> dict[str, Any]:
        return {"pos": self.pos, "rot": self.rot}


class PointRef:
    """Named reference to an endpoint of an entity for constraints."""

    def __init__(self, entity: Entity, point_name: str) -> None:
        self.entity = entity
        self.point_name = point_name

    @property
    def pos(self) -> Vector3:
        if isinstance(self.entity, Rod):
            return self.entity.point(self.point_name)
        return self.entity.pose.pos

    def __getitem__(self, idx: int) -> float:
        return self.pos[idx]

    def __len__(self) -> int:
        return len(self.pos)

    def __iter__(self):
        return iter(self.pos)

    def __add__(self, other: Any) -> Vec:
        return Vec(*self.pos) + other

    def __radd__(self, other: Any) -> Vec:
        return Vec(*self.pos) + other

    def __sub__(self, other: Any) -> Vec:
        return Vec(*self.pos) - other

    def __rsub__(self, other: Any) -> Vec:
        return other - Vec(*self.pos)

    def __repr__(self) -> str:
        return f"{self.entity.id}.{self.point_name}"


class Entity:
    def __init__(self, id: str, pose: SE3 | None = None) -> None:
        self.id = str(id)
        self.pose: SE3 = pose if pose is not None else SE3.identity()

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": "entity", "pose": self.pose.to_dict()}


class Rod(Entity):
    def __init__(self, id: str, length: float = 1.0, pose: SE3 | None = None) -> None:
        super().__init__(id, pose)
        self._length = float(length)

    @property
    def length(self) -> float:
        return self._length

    @length.setter
    def length(self, val: float) -> None:
        if val <= 0:
            raise ValueError("Length must be positive")
        self._length = float(val)

    @classmethod
    def between(cls, p1: Sequence[float], p2: Sequence[float], id: str) -> Rod:
        pose, length = SE3.from_endpoints(p1, p2)
        return cls(id=id, length=length, pose=pose)

    @property
    def a(self) -> Vector3:
        return self.pose.apply([-self.length / 2.0, 0.0, 0.0])

    @property
    def b(self) -> Vector3:
        return self.pose.apply([self.length / 2.0, 0.0, 0.0])

    @property
    def start(self) -> PointRef:
        return PointRef(self, "a")

    @property
    def end(self) -> PointRef:
        return PointRef(self, "b")

    def point(self, name: str) -> Vector3:
        if name == "a":
            return self.a
        if name == "b":
            return self.b
        if name in ("center", "origin"):
            return self.pose.apply([0.0, 0.0, 0.0])
        raise KeyError(f"Unknown point {name!r} on Rod {self.id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "rod",
            "length": self.length,
            "pose": self.pose.to_dict(),
            "p1": self.a,
            "p2": self.b,
        }


class Joint(Entity):
    """Point joint connecting two entities or pinning to ground."""

    def __init__(
        self,
        id: str,
        pos: Sequence[float],
        entity_a: str | None = None,
        point_a: str | None = None,
        entity_b: str | None = None,
        point_b: str | None = None,
    ) -> None:
        super().__init__(id, SE3.from_translation(*_vec3(pos)))
        self.entity_a = entity_a
        self.point_a = point_a
        self.entity_b = entity_b
        self.point_b = point_b

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "joint",
            "pos": self.pose.pos,
            "entity_a": self.entity_a,
            "point_a": self.point_a,
            "entity_b": self.entity_b,
            "point_b": self.point_b,
        }


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float] | None:
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for i in range(n):
        pivot = i
        for j in range(i + 1, n):
            if abs(M[j][i]) > abs(M[pivot][i]):
                pivot = j
        M[i], M[pivot] = M[pivot], M[i]
        if abs(M[i][i]) < 1e-14:
            return None
        div = M[i][i]
        for k in range(i, n + 1):
            M[i][k] /= div
        for j in range(n):
            if j != i:
                factor = M[j][i]
                for k in range(i, n + 1):
                    M[j][k] -= factor * M[i][k]
    return [M[i][n] for i in range(n)]


def _solve_gn(residual_fn, x0: Sequence[float], tol: float = 1e-5, max_iter: int = 40):
    x = [float(v) for v in x0]
    n = len(x)
    for _ in range(max_iter):
        r = residual_fn(x)
        cost = math.sqrt(sum(v * v for v in r))
        if cost < tol:
            return x, True, cost

        m = len(r)
        eps = 1e-7
        J = [[0.0] * n for _ in range(m)]
        for j in range(n):
            xp = list(x)
            xp[j] += eps
            rp = residual_fn(xp)
            for i in range(m):
                J[i][j] = (rp[i] - r[i]) / eps

        JTJ = [
            [sum(J[k][i] * J[k][j] for k in range(m)) for j in range(n)]
            for i in range(n)
        ]
        JTr = [sum(J[k][i] * r[k] for k in range(m)) for i in range(n)]
        for i in range(n):
            JTJ[i][i] += 1e-3

        dx = _solve_linear(JTJ, [-v for v in JTr])
        if not dx:
            break

        alpha = 1.0
        best_x = x
        best_cost = cost
        for _ in range(5):
            x_cand = [x[i] + alpha * dx[i] for i in range(n)]
            c_cand = math.sqrt(sum(v * v for v in residual_fn(x_cand)))
            if c_cand < best_cost:
                best_cost = c_cand
                best_x = x_cand
                break
            alpha *= 0.5

        if best_x == x:
            break
        x = best_x

    final_r = residual_fn(x)
    final_norm = math.sqrt(sum(v * v for v in final_r))
    return x, final_norm < 1e-3, final_norm


def _jacobi_svd(
    J: list[list[float]], tol: float = 1e-10, max_sweeps: int = 50
) -> tuple[list[float], list[list[float]]]:
    """Pure Python Jacobi SVD computing singular values and right singular vectors V."""
    m = len(J)
    n = len(J[0]) if m > 0 else 0
    if m == 0 or n == 0:
        return [], []
    AtA = [
        [sum(J[k][i] * J[k][j] for k in range(m)) for j in range(n)]
        for i in range(n)
    ]
    V = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        max_off = 0.0
        for p in range(n):
            for q in range(p + 1, n):
                off = abs(AtA[p][q])
                if off > max_off:
                    max_off = off
                if off < tol:
                    continue
                theta = 0.5 * math.atan2(2.0 * AtA[p][q], AtA[p][p] - AtA[q][q])
                c = math.cos(theta)
                s = math.sin(theta)
                app = AtA[p][p]
                aqq = AtA[q][q]
                apq = AtA[p][q]
                AtA[p][p] = c * c * app + s * s * aqq + 2.0 * c * s * apq
                AtA[q][q] = s * s * app + c * c * aqq - 2.0 * c * s * apq
                AtA[p][q] = 0.0
                AtA[q][p] = 0.0
                for r in range(n):
                    if r != p and r != q:
                        arp = AtA[r][p]
                        arq = AtA[r][q]
                        AtA[r][p] = c * arp + s * arq
                        AtA[p][r] = AtA[r][p]
                        AtA[r][q] = -s * arp + c * arq
                        AtA[q][r] = AtA[r][q]
                    vrp = V[r][p]
                    vrq = V[r][q]
                    V[r][p] = c * vrp + s * vrq
                    V[r][q] = -s * vrp + c * vrq
        if max_off < tol:
            break
    eigenvalues = [max(0.0, AtA[i][i]) for i in range(n)]
    singular_values = [math.sqrt(ev) for ev in eigenvalues]
    order = sorted(range(n), key=lambda i: singular_values[i], reverse=True)
    sorted_S = [singular_values[i] for i in order]
    sorted_V = [[V[r][i] for i in order] for r in range(n)]
    return sorted_S, sorted_V


class Model:
    def __init__(self, name: str = "model") -> None:
        self.name = name
        self.entities: dict[str, Entity] = {}
        self.joints: dict[str, Joint] = {}
        self._counter = 0

    def _auto_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def rod(
        self,
        p1: Sequence[float] | float | None = None,
        p2: Sequence[float] | None = None,
        *,
        id: str | None = None,
        length: float | None = None,
        pose: SE3 | None = None,
        angle: float | None = None,
    ) -> Rod:
        eid = id or self._auto_id("r")

        # Allow rod(3.0) or rod(length=3.0)
        if isinstance(p1, (int, float)) and p2 is None and length is None:
            length = float(p1)
            p1 = None

        if length is not None:
            if p1 is not None and p2 is not None:
                base_pose, _ = SE3.from_endpoints(p1, p2)
                r = Rod(id=eid, length=length, pose=base_pose)
            elif p1 is not None:
                ang = angle or 0.0
                p2_est = [
                    p1[0] + length * math.cos(ang),
                    p1[1] + length * math.sin(ang),
                ]
                base_pose, _ = SE3.from_endpoints(p1, p2_est)
                r = Rod(id=eid, length=length, pose=base_pose)
            else:
                r = Rod(id=eid, length=length, pose=pose)
        elif p1 is not None and p2 is not None:
            r = Rod.between(p1, p2, id=eid)
        else:
            raise ValueError("Provide either length or p1 & p2")

        self.entities[eid] = r
        return r

    def joint(
        self,
        a: Rod | Sequence[float] | str,
        pt_a: str | None = None,
        b: Rod | Sequence[float] | str | None = None,
        pt_b: str | None = None,
        *,
        id: str | None = None,
        at: Sequence[float] | None = None,
    ) -> Joint:
        jid = id or self._auto_id("joint")
        ent_a, p_name_a, pos_a = self._resolve_target(a, pt_a)
        ent_b, p_name_b, pos_b = (None, None, None)
        if b is not None:
            ent_b, p_name_b, pos_b = self._resolve_target(b, pt_b)

        pos = _vec3(at if at is not None else (pos_a or pos_b or [0.0, 0.0, 0.0]))
        j = Joint(
            id=jid,
            pos=pos,
            entity_a=ent_a,
            point_a=p_name_a,
            entity_b=ent_b,
            point_b=p_name_b,
        )
        self.joints[jid] = j
        return j

    def constraint_point_point(
        self,
        a: Any,
        b: Any,
        *,
        id: str | None = None,
        at: Sequence[float] | None = None,
    ) -> Joint:
        """Coincidence constraint between two points (e.g. g1.start, r1.start)."""
        return self.joint(a, None, b, None, id=id, at=at)

    def _resolve_target(
        self, target: Any, point_name: str | None = None
    ) -> tuple[str | None, str | None, Vector3 | None]:
        if isinstance(target, PointRef):
            return target.entity.id, target.point_name, target.pos
        if isinstance(target, Rod):
            pt = point_name or "a"
            return target.id, pt, target.point(pt)
        if isinstance(target, str) and target in self.entities:
            ent = self.entities[target]
            if isinstance(ent, Rod):
                pt = point_name or "a"
                return ent.id, pt, ent.point(pt)
        if isinstance(target, (list, tuple, Vec)) and len(target) in (2, 3):
            return None, None, _vec3(target)
        return str(target) if target else None, point_name, None

    def is_planar(self, tol: float = 1e-4) -> bool:
        """Check if all endpoints and joints lie in the z=0 plane."""
        for ent in self.entities.values():
            if isinstance(ent, Rod) and (abs(ent.a[2]) > tol or abs(ent.b[2]) > tol):
                return False
        for j in self.joints.values():
            if abs(j.pose.pos[2]) > tol:
                return False
        return True

    def solve(self, fixed: Sequence[str] | None = None, **kwargs) -> dict[str, Any]:
        """Solve point-joint assembly constraints using scipy.optimize.least_squares (with built-in GN fallback)."""
        fixed_set = (
            set(fixed)
            if fixed is not None
            else {
                eid
                for eid in self.entities
                if "ground" in eid.lower() or eid.lower().startswith("g")
            }
        )
        moving_rods = [
            e
            for e in self.entities.values()
            if isinstance(e, Rod) and e.id not in fixed_set
        ]

        if not moving_rods or not self.joints:
            return {
                "success": True,
                "residual_norm": 0.0,
                "message": "Nothing to solve",
            }

        x0: list[float] = []
        for r in moving_rods:
            p1, p2 = r.a, r.b
            cx, cy = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
            theta = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
            x0.extend([cx, cy, theta])

        def eval_points(x: Sequence[float]) -> dict[tuple[str, str], Vector3]:
            pts: dict[tuple[str, str], Vector3] = {}
            for idx, r in enumerate(moving_rods):
                cx, cy, theta = x[idx * 3], x[idx * 3 + 1], x[idx * 3 + 2]
                half_dx = (r.length / 2.0) * math.cos(theta)
                half_dy = (r.length / 2.0) * math.sin(theta)
                pts[(r.id, "a")] = [cx - half_dx, cy - half_dy, 0.0]
                pts[(r.id, "b")] = [cx + half_dx, cy + half_dy, 0.0]
            for eid in fixed_set:
                ent = self.entities.get(eid)
                if isinstance(ent, Rod):
                    pts[(ent.id, "a")] = ent.a
                    pts[(ent.id, "b")] = ent.b
            return pts

        def residual(x: Sequence[float]) -> list[float]:
            pts = eval_points(x)
            res: list[float] = []
            for j in self.joints.values():
                pa = pts.get((j.entity_a, j.point_a)) if j.entity_a else j.pose.pos
                pb = pts.get((j.entity_b, j.point_b)) if j.entity_b else j.pose.pos
                if pa is not None and pb is not None:
                    res.append(pa[0] - pb[0])
                    res.append(pa[1] - pb[1])
            return res

        res0 = residual(x0)
        if not res0:
            return {"success": True, "residual_norm": 0.0}

        use_scipy = False
        try:
            import numpy as np
            from scipy.optimize import least_squares

            use_scipy = True
        except ImportError:
            use_scipy = False

        if use_scipy:
            try:
                sol = least_squares(residual, np.array(x0, dtype=float), **kwargs)
                sol_x = [float(v) for v in sol.x]
                norm = float(np.linalg.norm(sol.fun))
                success = bool(sol.success) and norm < 1e-4
                msg = str(sol.message)
            except Exception as e:
                sol_x, success, norm = _solve_gn(residual, x0)
                msg = f"gn fallback: {e}"
        else:
            sol_x, success, norm = _solve_gn(residual, x0)
            msg = "solved with built-in gn"

        for idx, r in enumerate(moving_rods):
            cx, cy, theta = (
                float(sol_x[idx * 3]),
                float(sol_x[idx * 3 + 1]),
                float(sol_x[idx * 3 + 2]),
            )
            c, s = math.cos(theta), math.sin(theta)
            rot = [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
            r.pose = SE3([cx, cy, 0.0], rot)

        pts = eval_points(sol_x)
        for j in self.joints.values():
            pa = pts.get((j.entity_a, j.point_a)) if j.entity_a else None
            pb = pts.get((j.entity_b, j.point_b)) if j.entity_b else None
            pos = pa or pb
            if pos is not None:
                j.pose = SE3.from_translation(pos[0], pos[1], pos[2])

        return {
            "success": success,
            "residual_norm": norm,
            "message": msg,
        }

    def analyze_mobility(self) -> dict[str, Any]:
        """Compute first-order Jacobian kernel and second-order Taylor curvature obstruction.

        Evaluates whether tangent velocities in ker(J) satisfy the second-order acceleration
        condition J*a + w(v) = 0 where w_k(v) = ||v_i - v_j||^2.
        If ||(I - J J^+) w(v)|| > 0, the first-order free motion is obstructed by curvature
        (dead-center singularity), proving true manifold dimension is 0.
        """
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            if x not in parent:
                parent[x] = x
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        fixed_positions: dict[str, list[float]] = {}
        for eid, ent in self.entities.items():
            is_ground = "ground" in eid.lower() or eid.lower().startswith("g")
            k1 = f"rod:{eid}:a"
            k2 = f"rod:{eid}:b"
            find(k1)
            find(k2)
            if is_ground:
                fix1 = f"fixed:ground:{eid}:a"
                fix2 = f"fixed:ground:{eid}:b"
                fixed_positions[fix1] = [ent.a[0], ent.a[1]]
                fixed_positions[fix2] = [ent.b[0], ent.b[1]]
                union(k1, fix1)
                union(k2, fix2)

        for jid, j in self.joints.items():
            jk = f"joint:{jid}"
            find(jk)
            if j.entity_a:
                union(jk, f"rod:{j.entity_a}:{j.point_a or 'a'}")
            else:
                fixA = f"fixed:joint:{jid}:a"
                fixed_positions[fixA] = [j.pose.pos[0], j.pose.pos[1]]
                union(jk, fixA)
            if j.entity_b:
                union(jk, f"rod:{j.entity_b}:{j.point_b or 'a'}")
            else:
                fixB = f"fixed:joint:{jid}:b"
                fixed_positions[fixB] = [j.pose.pos[0], j.pose.pos[1]]
                union(jk, fixB)

        groups: dict[str, list[str]] = {}
        for k in list(parent.keys()):
            r = find(k)
            groups.setdefault(r, []).append(k)

        nodes: list[dict[str, Any]] = []
        rod_end_to_node: dict[str, int] = {}
        for root, keys in groups.items():
            is_fixed = any(k.startswith("fixed:") for k in keys)
            pos: list[float] | None = None
            if is_fixed:
                for k in keys:
                    if k in fixed_positions:
                        pos = fixed_positions[k]
                        break
            else:
                for k in keys:
                    if k.startswith("rod:"):
                        _, eid, pt = k.split(":")
                        pos = [self.entities[eid].point(pt)[0], self.entities[eid].point(pt)[1]]
                        break
                    elif k.startswith("joint:"):
                        _, jid = k.split(":")
                        pos = [self.joints[jid].pose.pos[0], self.joints[jid].pose.pos[1]]
                        break
            if pos is None:
                pos = [0.0, 0.0]
            nid = len(nodes)
            joint_ids = [k.split(":")[1] for k in keys if k.startswith("joint:")]
            rod_ids = list({k.split(":")[1] for k in keys if k.startswith("rod:")})
            nodes.append({
                "id": nid,
                "pos": [round(pos[0], 5), round(pos[1], 5)],
                "fixed": is_fixed,
                "joint_ids": joint_ids,
                "rod_ids": rod_ids,
                "tangents": [],
            })
            for k in keys:
                if k.startswith("rod:"):
                    rod_end_to_node[k] = nid

        edges: list[dict[str, Any]] = []
        for eid, ent in self.entities.items():
            is_ground = "ground" in eid.lower() or eid.lower().startswith("g")
            if is_ground:
                continue
            na = rod_end_to_node.get(f"rod:{eid}:a")
            nb = rod_end_to_node.get(f"rod:{eid}:b")
            if na is not None and nb is not None and na != nb:
                edges.append({"rod_id": eid, "na": na, "nb": nb, "length": ent.length})

        moving_nodes = [n["id"] for n in nodes if not n["fixed"]]
        node_to_mov = {nid: idx for idx, nid in enumerate(moving_nodes)}

        n_mov = len(moving_nodes)
        n_vars = n_mov * 2
        m_cons = len(edges)

        if n_vars == 0 or m_cons == 0:
            return {
                "dof_1st": 0,
                "dof_2nd": 0,
                "rank": 0,
                "n_vars": n_vars,
                "m_constraints": m_cons,
                "singular_values": [],
                "is_singular": False,
                "is_dead_center": False,
                "status": "rigid",
                "message": "All nodes fixed or no constraints.",
                "nodes": nodes,
                "obstructed_vectors": [],
            }

        J = [[0.0] * n_vars for _ in range(m_cons)]
        for k, e in enumerate(edges):
            na, nb = e["na"], e["nb"]
            pa = nodes[na]["pos"]
            pb = nodes[nb]["pos"]
            diff = [pa[0] - pb[0], pa[1] - pb[1]]
            if na in node_to_mov:
                idx = node_to_mov[na]
                J[k][idx * 2] = diff[0]
                J[k][idx * 2 + 1] = diff[1]
            if nb in node_to_mov:
                idx = node_to_mov[nb]
                J[k][idx * 2] = -diff[0]
                J[k][idx * 2 + 1] = -diff[1]

        singular_values: list[float] = []
        V_null: list[list[float]] = []
        U_cols: list[list[float]] = []
        rank = 0

        use_numpy = False
        try:
            import numpy as np
            use_numpy = True
        except ImportError:
            use_numpy = False

        if use_numpy:
            np_J = np.array(J, dtype=float)
            U, S, Vt = np.linalg.svd(np_J, full_matrices=True)
            singular_values = [round(float(s), 6) for s in S]
            tol = 1e-6 * max(1.0, float(S[0]) if len(S) > 0 else 1.0)
            rank = int(np.sum(S > tol))
            for i in range(rank, Vt.shape[0]):
                V_null.append([float(v) for v in Vt[i]])
            for i in range(rank):
                U_cols.append([float(U[row, i]) for row in range(m_cons)])
        else:
            S_list, V_cols = _jacobi_svd(J)
            singular_values = [round(float(s), 6) for s in S_list]
            tol = 1e-6 * max(1.0, S_list[0] if S_list else 1.0)
            rank = sum(1 for s in S_list if s > tol)
            for col_idx in range(rank, len(S_list)):
                V_null.append([V_cols[row][col_idx] for row in range(n_vars)])
            for i in range(rank):
                v_i = [V_cols[row][i] for row in range(n_vars)]
                j_vi = [sum(J[k][c] * v_i[c] for c in range(n_vars)) for k in range(m_cons)]
                u_i = [val / S_list[i] for val in j_vi]
                U_cols.append(u_i)

        dof_1st = n_vars - rank
        obstructed_info: list[dict[str, Any]] = []
        obstructed_count = 0

        for basis_idx, v in enumerate(V_null):
            v_norm = math.sqrt(sum(val * val for val in v))
            if v_norm > 1e-12:
                v = [val / v_norm for val in v]

            w = [0.0] * m_cons
            for k, e in enumerate(edges):
                na, nb = e["na"], e["nb"]
                va = (
                    v[node_to_mov[na] * 2 : node_to_mov[na] * 2 + 2]
                    if na in node_to_mov
                    else [0.0, 0.0]
                )
                vb = (
                    v[node_to_mov[nb] * 2 : node_to_mov[nb] * 2 + 2]
                    if nb in node_to_mov
                    else [0.0, 0.0]
                )
                dvx, dvy = va[0] - vb[0], va[1] - vb[1]
                w[k] = dvx * dvx + dvy * dvy

            proj = [0.0] * m_cons
            for u in U_cols:
                dot = sum(u[k] * w[k] for k in range(m_cons))
                for k in range(m_cons):
                    proj[k] += dot * u[k]

            obstruction = [w[k] - proj[k] for k in range(m_cons)]
            obs_norm = math.sqrt(sum(val * val for val in obstruction))
            is_obstructed = obs_norm > 1e-4

            if is_obstructed:
                obstructed_count += 1

            obstructed_info.append({
                "basis_idx": basis_idx,
                "obstruction_norm": round(obs_norm, 5),
                "is_obstructed": is_obstructed,
                "centripetal_vector": [round(val, 5) for val in w],
                "acceleration_mismatch": [round(val, 5) for val in obstruction],
            })

            for nid in moving_nodes:
                idx = node_to_mov[nid]
                vx = v[idx * 2]
                vy = v[idx * 2 + 1]
                nodes[nid]["tangents"].append({
                    "basis_idx": basis_idx,
                    "vector": [round(vx, 5), round(vy, 5)],
                    "obstructed": is_obstructed,
                    "obstruction_norm": round(obs_norm, 5),
                })

        dof_2nd = max(0, dof_1st - obstructed_count)
        is_dead_center = dof_1st > 0 and dof_2nd == 0
        is_singular = is_dead_center or (dof_1st > dof_2nd)

        if is_dead_center:
            status = "dead_center_singularity"
            max_obs = max((o["obstruction_norm"] for o in obstructed_info), default=0.0)
            msg = (
                f"Dead-center singularity detected: 1st-order dim(ker J)={dof_1st} "
                f"(phantom infinitesimal velocity), but 2nd-order curvature obstruction "
                f"||(I - JJ⁺)w(v)||={max_obs:.4f} proves dim(M)=0 (rigid lock)."
            )
        elif dof_2nd > 0:
            status = "mobile"
            msg = f"Mobile mechanism: {dof_2nd} degree(s) of freedom certified at 2nd order."
        else:
            status = "rigid"
            msg = "Rigid assembly: 0 degrees of freedom (kinematically locked)."

        return {
            "dof_1st": dof_1st,
            "dof_2nd": dof_2nd,
            "rank": rank,
            "n_vars": n_vars,
            "m_constraints": m_cons,
            "singular_values": singular_values,
            "is_singular": is_singular,
            "is_dead_center": is_dead_center,
            "status": status,
            "message": msg,
            "nodes": nodes,
            "obstructed_vectors": obstructed_info,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entities": [e.to_dict() for e in self.entities.values()],
            "joints": [j.to_dict() for j in self.joints.values()],
            "is_planar": self.is_planar(),
            "analysis": self.analyze_mobility(),
        }

    def export_json(self, auto_solve: bool = True) -> str:
        if auto_solve:
            try:
                self.solve()
            except Exception:
                pass
        return json.dumps(self.to_dict())


# --- Default global scene ---
_default_model = Model("scene")


def default_model() -> Model:
    return _default_model


def reset() -> None:
    global _default_model
    _default_model = Model("scene")


def rod(*args, **kwargs) -> Rod:
    return _default_model.rod(*args, **kwargs)


def joint(*args, **kwargs) -> Joint:
    return _default_model.joint(*args, **kwargs)


def constraint_point_point(*args, **kwargs) -> Joint:
    return _default_model.constraint_point_point(*args, **kwargs)


def solve(*args, **kwargs) -> dict[str, Any]:
    return _default_model.solve(*args, **kwargs)


def analyze_mobility(*args, **kwargs) -> dict[str, Any]:
    return _default_model.analyze_mobility(*args, **kwargs)


def export_json(auto_solve: bool = True) -> str:
    return _default_model.export_json(auto_solve=auto_solve)


if __name__ == "__main__":
    reset()
    r1 = rod([0, 0], [3, 0], id="ground")
    r2 = rod([0, 0], [0, 2], id="crank")
    r3 = rod([0, 2], [3.2, 2.8], id="coupler", length=4.0)
    r4 = rod([3.2, 2.8], [3, 0], id="rocker", length=3.0)
    joint(r1, "a", r2, "a", id="jA")
    joint(r2, "b", r3, "a", id="jB")
    joint(r3, "b", r4, "a", id="jC")
    joint(r4, "b", r1, "b", id="jD")

    res = solve()
    assert res["success"] is True, f"Solve failed: {res}"
    d = _default_model.to_dict()
    assert len(d["entities"]) == 4
    assert len(d["joints"]) == 4
    assert d["is_planar"] is True
    print("Self-check with scipy solve passed!")
