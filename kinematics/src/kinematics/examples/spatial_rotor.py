# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
from itertools import cycle, islice

# A triangular pyramid rotor on a spherical joint: three rotational DOFs.
scene_dimension(3)
stand = rod(down * 0.6, origin, id="stand", fixed=True)

pts = range_circle(3, radius=1.0, center=up * 1.4, u=right, v=forward)
edges = [rod(origin, p) for p in pts]
next_edges = list(islice(cycle(edges), 1, 4))
bases = [rod(p, q) for p, q in zip(pts, islice(cycle(pts), 1, 4))]

for e1, e2 in zip(edges, next_edges):
    coincident(e1.start, e2.start)

for e1, b, e2 in zip(edges, bases, next_edges):
    coincident(e1.end, b.start)
    coincident(b.end, e2.end)

pin(edges[0].start, origin, id="spherical_joint")
# Click Wander. The rotor turns freely around its fixed apex in all 3 axes.
