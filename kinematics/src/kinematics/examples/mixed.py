# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Mixed Dimensions: a circle and an isolated point
r1 = rod(Vec(1, 1), origin, id="r1")
r2 = rod(Vec(1, -1), origin, id="r2")
r3 = rod(origin, up, id="r3")
r4 = rod(origin, up, id="r4")
pin(r1.start, Vec(1, 1))
pin(r2.start, Vec(1, -1))
pin(r3.start, origin)
coincident(r1.end, r2.end)
coincident(r2.end, r4.start)
coincident(r3.end, r4.end)
