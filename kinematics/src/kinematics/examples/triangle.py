# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Disjoint Modes (Triangle)
r1 = rod(Vec(-1.5, 0), Vec(0, sqrt(7) / 2), id="r1")
r2 = rod(Vec(1.5, 0), r1.end, id="r2")
pin(r1.start, Vec(-1.5, 0))
pin(r2.start, Vec(1.5, 0))
coincident(r1.end, r2.end)
