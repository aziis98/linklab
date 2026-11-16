# Planar 4-Bar Linkage
l1 = 2.0
l2 = 3.0
d = 3.0

g1 = rod(origin, origin + right * d, id="g1", fixed=True)
r1 = rod(origin, up * l1, id="r1")
r2 = rod(g1.end, g1.end + up * l2, id="r2")
r3 = rod(r1.end, r2.end, id="r3")

constraint_point_point(g1.start, r1.start, id="j1")
constraint_point_point(r1.end, r3.start, id="j2")
constraint_point_point(r3.end, r2.end, id="j3")
constraint_point_point(r2.start, g1.end, id="j4")
