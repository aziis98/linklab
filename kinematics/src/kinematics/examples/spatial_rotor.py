# ruff: noqa: F821 -- evaluated inside the scene DSL namespace
# A tetrahedral rotor on a spherical joint: three rotational DOFs.
scene_dimension(3)
stand = rod(down * 0.6, origin, id="stand", fixed=True)
rotor = body({}, id="rotor")
pin(rotor.point("origin"), origin, id="spherical_joint")
# Click Wander. The rotor turns freely around its fixed corner in all 3 axes.
