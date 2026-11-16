# Dead-Center Singularity (Collinear 2-Rod)
l = 2.0
r1 = rod(left * l, origin, id="r1")
r2 = rod(origin, right * l, id="r2")

constraint_point_point(left * l, r1.start, id="j1")
constraint_point_point(r1.end, r2.start, id="j2")
constraint_point_point(r2.end, right * l, id="j3")
