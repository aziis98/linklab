# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Dead-Center Singularity (Collinear 2-Rod)
r1 = rod(left * 2, origin, id="r1")
r2 = rod(origin, right * 2, id="r2")
pin(r1.start, left * 2)
coincident(r1.end, r2.start)
pin(r2.end, right * 2)
