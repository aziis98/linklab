"""Run a scene without a browser: python -m kinematics scene.py --png scene.png."""

import argparse
import json
from pathlib import Path

from . import Session, build_scene, render_png


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", type=Path)
    parser.add_argument("--dimension", type=int, choices=(2, 3), default=None)
    parser.add_argument(
        "--solver", choices=("numerical", "topological"), default="numerical"
    )
    parser.add_argument("--png", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    source = args.scene.read_text()
    data = Session().run(source, args.dimension, args.solver)
    if args.png:
        render_png(build_scene(source, args.dimension), data["configuration"], args.png)
    text = json.dumps(data, indent=2, allow_nan=False)
    if args.json:
        args.json.write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
