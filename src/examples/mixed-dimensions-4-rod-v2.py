# Mixed Dimensions: a circle and an isolated point
q = origin
p = up
r1 = rod(Vec(1, 1), q, id="r1")
r2 = rod(Vec(1, -1), q, id="r2")
r3 = rod(origin, p, id="r3")
r4 = rod(q, p, id="r4")
pin(r1.start, Vec(1, 1))
pin(r2.start, Vec(1, -1))
pin(r3.start, origin)
coincident(r1.end, r2.end)
coincident(r2.end, r4.start)
coincident(r3.end, r4.end)
