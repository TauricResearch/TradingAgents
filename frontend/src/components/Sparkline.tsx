/** Hand-rolled SVG sparkline — cheaper than a chart instance per row. */
export function Sparkline({
  values,
  width = 96,
  height = 24,
  ariaLabel,
}: {
  values: number[];
  width?: number;
  height?: number;
  ariaLabel?: string;
}) {
  if (values.length < 2) return <span className="text-fg-subtle">—</span>;
  let min = Infinity;
  let max = -Infinity;
  for (const v of values) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const span = max - min || 1;
  const points = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * width).toFixed(1)},${(
          height -
          2 -
          ((v - min) / span) * (height - 4)
        ).toFixed(1)}`,
    )
    .join(" ");
  const first = values[0]!;
  const last = values[values.length - 1]!;
  const up = last >= first;
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel ?? `trend ${up ? "up" : "down"}`}
      className="shrink-0"
    >
      <polyline
        points={points}
        fill="none"
        stroke={up ? "var(--bull)" : "var(--bear)"}
        strokeWidth="1.5"
      />
    </svg>
  );
}
