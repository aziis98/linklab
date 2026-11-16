# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# Spatial arm moving in the XZ plane
scene_dimension(3)
base = rod(left, right, id="base", fixed=True)
arm = rod(origin, Vec(1, 0, 1), id="arm")
pin(arm.start, origin)
plane(arm, origin, up)
# Drag the background to orbit; Shift-drag to pan. Object drags use the view plane.
