# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Planar 4-Bar Linkage
g = rod(origin, right * 3, id="ground", fixed=True)
a = rod(origin, up * 2, id="a")
b = rod(g.end, g.end + up * 3, id="b")
c = rod(a.end, b.end, id="c")
coincident(g.start, a.start)
coincident(g.end, b.start)
coincident(a.end, c.start)
coincident(b.end, c.end)
