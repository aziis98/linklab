"""Generate numerical reference cases from the native Python drag engine."""

import json
from pathlib import Path
from time import perf_counter

from kinematics.core.numerical_model import export_model
from kinematics.core.preview import preview

from kinematics import Session


def fixtures():
    scenes = [
        (path.stem, path.read_text())
        for path in Path("kinematics/src/kinematics/examples").glob("*.py")
        if path.name != "__init__.py"
    ]
    for dimension in (2, 3):
        scenes.append(
            (
                f"parallel_{dimension}d",
                f"scene_dimension({dimension})\na=rod(origin,up)\nb=rod(right,right+up)\nparallel(a.axis(),b.axis())\npin(a.start)",
            )
        )
        scenes.append(
            (
                f"plane_{dimension}d",
                f"scene_dimension({dimension})\nr=rod(origin,up)\nplane(r,origin,right)",
            )
        )
    for name, source in scenes:
        session = Session()
        session.run(source)
        engine = session.engine
        model = export_model(session)
        key = next(
            (
                key
                for key in reversed(engine.keys)
                if engine.index[key] not in engine.pins
            ),
            engine.keys[-1],
        )
        targets = [[v + 0.01 * engine.scale for v in engine.configuration()[key]]]
        start = perf_counter()
        result = session.drag([key], targets)
        ghost = preview(engine, [key], targets)
        yield {
            "name": name,
            "model": model,
            "jacobian": engine.jac(engine.initial.ravel()).tolist(),
            "key": key,
            "targets": targets,
            "result": result,
            "preview": ghost,
            "python_ms": (perf_counter() - start) * 1000,
        }


if __name__ == "__main__":
    print(json.dumps(list(fixtures())))
