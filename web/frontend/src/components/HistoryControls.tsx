import { useUi } from "../store/ui";
import { fmtDelta, fmtPct } from "../lib/format";

export function HistoryControls({
  deltaMs,
  onDeltaChange,
}: {
  deltaMs: number;
  onDeltaChange: (ms: number) => void;
}) {
  const holdThresholdPct = useUi((s) => s.holdThresholdPct);
  const setHoldThresholdPct = useUi((s) => s.setHoldThresholdPct);

  // Log-scale slider: position 0..1000 maps to 5m..3y exponentially.
  // pos 0   → 5m,   pos 500 → ~6mo,   pos 1000 → 3y.
  const min = 5 * 60_000;
  const max = 3 * 365 * 24 * 60 * 60_000;
  const logMin = Math.log(min);
  const logMax = Math.log(max);
  const posToDelta = (pos: number): number =>
    Math.exp(logMin + (pos / 1000) * (logMax - logMin));
  const deltaToPos = (ms: number): number =>
    ((Math.log(ms) - logMin) / (logMax - logMin)) * 1000;

  return (
    <div className="border-b border-slate-200 px-3 py-2 text-xs space-y-2">
      <div className="flex items-center gap-2">
        <label htmlFor="delta-slider" className="w-12 text-slate-600">Δ</label>
        <input
          id="delta-slider"
          data-testid="delta-slider"
          type="range"
          min={0}
          max={1000}
          value={deltaToPos(deltaMs)}
          onChange={(e) => onDeltaChange(posToDelta(Number(e.target.value)))}
          className="flex-1"
        />
        <span className="w-12 text-right font-medium text-slate-900">{fmtDelta(deltaMs)}</span>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor="hold-slider" className="w-12 text-slate-600">HOLD%</label>
        <input
          id="hold-slider"
          data-testid="hold-threshold-slider"
          type="range"
          min={0.1}
          max={5.0}
          step={0.1}
          value={holdThresholdPct}
          onChange={(e) => setHoldThresholdPct(Number(e.target.value))}
          className="flex-1"
        />
        <span className="w-12 text-right font-medium text-slate-900">{fmtPct(holdThresholdPct)}</span>
      </div>
    </div>
  );
}
