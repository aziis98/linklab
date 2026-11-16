# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Hopf link: A=(cos(theta),sin(theta),0), B=(1+cos(phi),0,sin(phi)).
# Ideal cables allow shortening, but prevent stretching beyond their initial lengths.
scene_dimension(3)
A = ring(origin, 1, id="A", fixed=True)
B = ring(right, 1, id="B", normal=down)

L = right / 4
H = right * 3 / 4
p = sqrt(15) / 4
q = sqrt(7) / 4

# A's local frame is XY; B's local frame is XZ, centered at (1,0,0).
a1 = A.rel(L + up*p, label="a1")
a2 = A.rel(L - up*p, label="a2")
a3 = A.rel(H + up*q, label="a3")
a4 = A.rel(H - up*q, label="a4")

b1 = B.rel(Vec(-3/4, q), label="b1")
b2 = B.rel(Vec(-3/4, -q), label="b2")
b3 = B.rel(Vec(-1/4, -p), label="b3")
b4 = B.rel(Vec(-1/4, p), label="b4")

cable(a1, b1, id="cable1")
cable(a2, b2, id="cable2")
cable(a3, b3, id="cable3")
cable(a4, b4, id="cable4")
