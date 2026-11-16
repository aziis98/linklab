# Three radial braces at 120 degrees between concentric rings in local XY.
scene_dimension(3)
outer = ring(origin, 3, id="outer", fixed=True)
inner = ring(origin, 1.5, id="inner")

directions = range_circle(3, u=right, v=up)
for i, direction in enumerate(directions):
    outer_point = outer.rel(direction * outer.radius)
    inner_point = inner.rel(direction * inner.radius)
    bar = rod(outer_point, inner_point, id=f"brace_{i + 1}")
    coincident(outer_point, bar.start)
    coincident(bar.end, inner_point)

# The radial braces lock this configuration, despite infinitesimal motions.
