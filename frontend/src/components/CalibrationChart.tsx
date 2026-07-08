/** Reliability diagram: predicted confidence vs realized hit rate.
 * Buckets under n=10 render hollow — never imply certainty from three
 * trades. Hand-rolled SVG: ~80 lines beats a 400KB chart lib. */
import type { AgentPerf } from "@/lib/api/types";

interface Bucket {
  midpoint: number; // 0..1 predicted
  hitRate: number | null;
  n: number;
}

export function calibrationBuckets(perf: AgentPerf): Bucket[] {
  const edges = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0001];
  const buckets = edges.slice(0, -1).map((lo, i) => ({
    lo,
    hi: edges[i + 1]!,
    correct: 0,
    scored: 0,
  }));
  Object.values(perf).forEach((agent) => {
    if (agent.scored === 0 || agent.hit_rate == null) return;
    const predicted = agent.avg_confidence / 100;
    const bucket = buckets.find((b) => predicted >= b.lo && predicted < b.hi);
    if (!bucket) return;
    bucket.scored += agent.scored;
    bucket.correct += agent.hit_rate * agent.scored;
  });
  return buckets.map((b) => ({
    midpoint: (b.lo + Math.min(b.hi, 1)) / 2,
    hitRate: b.scored > 0 ? b.correct / b.scored : null,
    n: b.scored,
  }));
}

export function CalibrationChart({ perf }: { perf: AgentPerf }) {
  const buckets = calibrationBuckets(perf);
  const hasData = buckets.some((b) => b.n > 0);
  const W = 280;
  const H = 220;
  const PAD = 32;
  const x = (v: number) => PAD + ((v - 0.5) / 0.5) * (W - PAD - 8);
  const y = (v: number) => H - PAD - v * (H - PAD - 8);

  if (!hasData) {
    return (
      <p className="py-6 text-center text-sm text-fg-subtle">
        Needs scored outcomes — the diagram appears once closed trades
        accumulate. No number is shown until it means something.
      </p>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full max-w-sm"
      role="img"
      aria-label="confidence calibration: predicted confidence versus realized hit rate"
      data-testid="calibration-chart"
    >
      {/* axes */}
      <line x1={PAD} y1={H - PAD} x2={W - 8} y2={H - PAD} stroke="var(--border-strong)" />
      <line x1={PAD} y1={8} x2={PAD} y2={H - PAD} stroke="var(--border-strong)" />
      {/* perfect-calibration diagonal (0.5..1 both axes) */}
      <line
        x1={x(0.5)}
        y1={y(0.5)}
        x2={x(1)}
        y2={y(1)}
        stroke="var(--fg-subtle)"
        strokeDasharray="4 3"
      />
      {[0.5, 0.75, 1].map((tick) => (
        <g key={tick} className="text-[9px]" fill="var(--fg-subtle)">
          <text x={x(tick)} y={H - PAD + 12} textAnchor="middle">
            {Math.round(tick * 100)}
          </text>
          <text x={PAD - 6} y={y(tick) + 3} textAnchor="end">
            {Math.round(tick * 100)}
          </text>
        </g>
      ))}
      <text
        x={(W + PAD) / 2}
        y={H - 4}
        textAnchor="middle"
        fill="var(--fg-muted)"
        className="text-[9px]"
      >
        predicted confidence %
      </text>
      <text
        x={10}
        y={(H - PAD) / 2}
        textAnchor="middle"
        fill="var(--fg-muted)"
        className="text-[9px]"
        transform={`rotate(-90 10 ${(H - PAD) / 2})`}
      >
        realized hit rate %
      </text>
      {buckets.map(
        (bucket, i) =>
          bucket.hitRate != null && (
            <g key={i}>
              <circle
                cx={x(bucket.midpoint)}
                cy={y(Math.max(0.5, Math.min(1, bucket.hitRate)))}
                r={Math.min(4 + Math.sqrt(bucket.n), 12)}
                fill={bucket.n >= 10 ? "var(--accent)" : "transparent"}
                stroke="var(--accent)"
                strokeWidth={1.5}
                opacity={0.9}
              >
                <title>
                  {`predicted ~${Math.round(bucket.midpoint * 100)}%, realized ${Math.round(
                    bucket.hitRate * 100,
                  )}% (n=${bucket.n}${bucket.n < 10 ? ", insufficient sample" : ""})`}
                </title>
              </circle>
            </g>
          ),
      )}
    </svg>
  );
}
