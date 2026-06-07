import { useUi, type HistoryPollInterval } from "../store/ui";
import { fmtDelta, fmtPct } from "../lib/format";

const REFRESH_OPTIONS: Array<{ label: string; value: HistoryPollInterval }> = [
  { label: "Off", value: 0 },
  { label: "5s", value: 5_000 },
  { label: "15s", value: 15_000 },
  { label: "30s", value: 30_000 },
  { label: "1m", value: 60_000 },
  { label: "5m", value: 300_000 },
];

export type CandleResolution = "auto" | "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

const CANDLE_RESOLUTIONS: Array<{ label: string; value: CandleResolution }> = [
  { label: "Auto", value: "auto" },
  { label: "1m", value: "1m" },
  { label: "5m", value: "5m" },
  { label: "15m", value: "15m" },
  { label: "1h", value: "1h" },
  { label: "4h", value: "4h" },
  { label: "1d", value: "1d" },
];

export function HistoryControls({
  deltaMs,
  onDeltaChange,
  candleResolution,
  onCandleResolutionChange,
}: {
  deltaMs: number;
  onDeltaChange: (ms: number) => void;
  candleResolution: CandleResolution;
  onCandleResolutionChange: (r: CandleResolution) => void;
}) {
  const holdThresholdPct = useUi((s) => s.holdThresholdPct);
  const setHoldThresholdPct = useUi((s) => s.setHoldThresholdPct);
  const historyPollIntervalMs = useUi((s) => s.historyPollIntervalMs);
  const setHistoryPollIntervalMs = useUi((s) => s.setHistoryPollIntervalMs);

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
        <label htmlFor="candle-res-select" className="w-12 text-slate-600">Candle</label>
        <select
          id="candle-res-select"
          data-testid="candle-res-select"
          value={candleResolution}
          onChange={(e) => onCandleResolutionChange(e.target.value as CandleResolution)}
          className="flex-1 border border-slate-300 rounded px-1 py-0.5 bg-white"
        >
          {CANDLE_RESOLUTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
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
      <div className="flex items-center gap-2">
        <label htmlFor="refresh-select" className="w-12 text-slate-600">Refresh</label>
        <select
          id="refresh-select"
          data-testid="refresh-select"
          value={historyPollIntervalMs}
          onChange={(e) => setHistoryPollIntervalMs(Number(e.target.value) as HistoryPollInterval)}
          className="flex-1 border border-slate-300 rounded px-1 py-0.5 bg-white"
        >
          {REFRESH_OPTIONS.map((o) => (
            <option key={o.label} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
