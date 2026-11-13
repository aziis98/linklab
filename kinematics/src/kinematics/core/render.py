"""Optional native PNG renderer; importing the solver does not load Matplotlib."""

from itertools import combinations

import numpy as np


def render_png(scene, configuration, path, camera=(35, 25), overlays=()):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig = plt.figure(figsize=(8, 6), facecolor="#090d16")
    ax = fig.add_subplot(projection="3d") if scene.dimension == 3 else fig.add_subplot()
    ax.set_facecolor("#090d16")
    for obj in scene.objects:
        pts = [np.array(configuration[f"{obj.id}:{name}"]) for name in obj.render_names]
        if obj.kind == "ring":
            center = np.array(configuration[f"{obj.id}:origin"])
            right = np.array(configuration[f"{obj.id}:x"]) - center
            top = np.array(configuration[f"{obj.id}:y"]) - center
            angles = np.linspace(0, 2 * np.pi, 129)
            circle = (
                center[:, None]
                + right[:, None] * np.cos(angles)
                + top[:, None] * np.sin(angles)
            )
            ax.plot(
                *circle[: scene.dimension],
                color="#64748b" if obj.fixed else "#38bdf8",
                linewidth=3,
            )
            continue
        for a, b in combinations(pts, 2):
            values = np.array([a, b]).T
            ax.plot(
                *values[: scene.dimension],
                color="#64748b" if obj.fixed else "#38bdf8",
                linewidth=3,
                marker="o",
            )
    for curve in overlays:
        p = np.asarray(curve)
        ax.plot(*p.T[: scene.dimension], color="#f59e0b", linestyle="--")
    if scene.dimension == 3:
        ax.set_proj_type("ortho")
        ax.view_init(elev=camera[1], azim=camera[0])
        ax.set_box_aspect((1, 1, 1))
    else:
        ax.set_aspect("equal")
    ax.tick_params(colors="#94a3b8")
    ax.grid(alpha=0.2)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
