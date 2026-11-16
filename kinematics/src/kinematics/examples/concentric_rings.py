# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Two rings joined by a hinged bar: 2 planar DOFs
scene_dimension(2)
outer = ring(origin, 3, id="outer", fixed=True)
inner = ring(origin, 1.5, id="inner")
bar = rod(outer.top, inner.top, id="bar")
coincident(outer.top, bar.start, id="outer_hinge")
coincident(bar.end, inner.top, id="inner_hinge")
