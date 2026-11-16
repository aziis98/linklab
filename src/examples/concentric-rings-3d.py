# Top and bottom braces fix the diameter; the inner ring rotates around it.
scene_dimension(3)
outer = ring(origin, 3, id="outer", fixed=True)
inner = ring(origin, 1.5, id="inner")
bar_top = rod(outer.top, inner.top)
bar_bottom = rod(outer.bottom, inner.bottom)

coincident(outer.top, bar_top.start)
coincident(bar_top.end, inner.top)

coincident(outer.bottom, bar_bottom.start)
coincident(bar_bottom.end, inner.bottom)
