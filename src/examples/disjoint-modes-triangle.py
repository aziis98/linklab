# Disjoint Modes (Triangle)
y = sqrt(4 - (3/2)**2)
r1 = rod(left * 1.5, up * y, id="r1")
r2 = rod(right * 1.5, up * y, id="r2")

constraint_point_point(left * 1.5, r1.start, id="j1")
constraint_point_point(right * 1.5, r2.start, id="j2")
constraint_point_point(r1.end, r2.end, id="j3")
