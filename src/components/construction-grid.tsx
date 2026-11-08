import { useId } from "preact/hooks";

type V = [number, number, number];
interface Props {
  ray: V;
  project: (point: V) => number[];
  scale: number;
  extent: number;
}

/** World-plane guides share the construction's orthographic projection. */
export function ConstructionGrid({ ray, project, scale, extent }: Props) {
  const id = useId();
  const step = 2 ** Math.ceil(Math.log2(24 / scale));
  const spacing = step * scale;
  const origin = project([0, 0, 0]);
  const aligned = ray.findIndex((value) => Math.abs(value) > 1 - 1e-7);
  if (aligned >= 0) {
    const plane = ["YZ", "XZ", "XY"][aligned];
    return (
      <g
        data-grid-view="planar"
        data-grid-plane={plane}
        pointer-events="none"
        aria-hidden="true"
      >
        <defs>
          <pattern
            id={id}
            x={origin[0]}
            y={origin[1]}
            width={spacing}
            height={spacing}
            patternUnits="userSpaceOnUse"
          >
            <path
              d={`M ${spacing} 0 H 0 V ${spacing}`}
              fill="none"
              stroke="var(--cad-grid)"
              stroke-width="1"
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${id})`} />
      </g>
    );
  }
  const count = Math.min(24, Math.max(2, Math.ceil((extent * 1.5) / step)));
  const radius = count * step;
  const planes = [
    { name: "XY", u: 0, v: 1 },
    { name: "XZ", u: 0, v: 2 },
    { name: "YZ", u: 1, v: 2 },
  ];
  const point = (u: number, v: number, a: number, b: number): V => {
    const result: V = [0, 0, 0];
    result[u] = a;
    result[v] = b;
    return result;
  };
  const axes = [
    { name: "X", color: "var(--danger)" },
    { name: "Y", color: "var(--ok)" },
    { name: "Z", color: "var(--accent)" },
  ];
  return (
    <g data-grid-view="spatial" pointer-events="none" aria-hidden="true">
      {planes.map(({ name, u, v }) => (
        <g
          key={name}
          data-grid-plane={name}
          stroke="var(--cad-grid)"
          stroke-width=".8"
          opacity=".65"
        >
          {Array.from({ length: count * 2 + 1 }, (_, i) => i - count)
            .filter((n) => n !== 0)
            .flatMap((n) =>
              [false, true].map((swap) => {
                const a = project(
                  point(
                    u,
                    v,
                    swap ? n * step : -radius,
                    swap ? -radius : n * step,
                  ),
                );
                const b = project(
                  point(
                    u,
                    v,
                    swap ? n * step : radius,
                    swap ? radius : n * step,
                  ),
                );
                return (
                  <line
                    key={`${n}-${swap}`}
                    x1={a[0]}
                    y1={a[1]}
                    x2={b[0]}
                    y2={b[1]}
                  />
                );
              }),
            )}
        </g>
      ))}
      {axes.map(({ name, color }, axis) => {
        const negative: V = [0, 0, 0],
          positive: V = [0, 0, 0];
        negative[axis] = -radius;
        positive[axis] = radius;
        const a = project(negative),
          b = project(positive);
        return (
          <g key={name} data-grid-axis={name}>
            <line
              x1={a[0]}
              y1={a[1]}
              x2={origin[0]}
              y2={origin[1]}
              stroke={color}
              stroke-width="1"
              opacity=".35"
            />
            <line
              x1={origin[0]}
              y1={origin[1]}
              x2={b[0]}
              y2={b[1]}
              stroke={color}
              stroke-width="1.2"
              opacity=".7"
            />
            <text x={b[0] + 5} y={b[1] - 5} fill={color} font-size="10">
              {name}
            </text>
          </g>
        );
      })}
    </g>
  );
}
