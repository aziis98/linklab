# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Spatial linked pendulum: a circular joint orbit plus a freely swinging rod.
scene_dimension(3)
a = rod(left, up, id="a")
b = rod(right, up, id="b")
c = rod(up, up * 2, id="c")
pin(a.start)
pin(b.start)
coincident(a.end, b.end)
coincident(a.end, c.start)
# Three DOFs: one for the shared joint, two for the direction of c. Try Wander.
