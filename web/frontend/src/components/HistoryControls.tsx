import { useUi } from "../store/ui";
import { fmtDelta, fmtPct } from "../lib/format";

export function HistoryControls({
  deltaMs,
  onDeltaChange,
  compact,
}: {
  deltaMs: number;
  onDeltaChange: (ms: number) => void;
  compact?: boolean;
}) {
  const holdThresholdPct = useUi((s) => s.holdThresholdPct);
  const setHoldThresholdPct = useUi((s) => s.setHoldThresholdPct);

  const min = 5 * 60_000;
  const max = 3 * 365 * 24 * 60 * 60_000;
  const logMin = Math.log(min);
  const logMax = Math.log(max);
  const posToDelta = (pos: number): number =>
    Math.exp(logMin + (pos / 1000) * (logMax - logMin));
  const deltaToPos = (ms: number): number =>
    ((Math.log(ms) - logMin) / (logMax - logMin)) * 1000;

  const inputClass = "appearance-none bg-slate-700/50 rounded-full h-1.5 cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-sky-400 [&::-webkit-slider-thumb]:shadow-[0_0_6px_rgba(56,189,248,0.5)] [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-sky-400 [&::-moz-range-thumb]:border-0";

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <label htmlFor="delta-slider" className="text-slate-600 shrink-0 font-medium">Δ</label>
        <input
          id="delta-slider"
          data-testid="delta-slider"
          type="range"
          min={0}
          max={1000}
          value={deltaToPos(deltaMs)}
          onChange={(e) => onDeltaChange(posToDelta(Number(e.target.value)))}
          className={`flex-1 ${inputClass}`}
        />
        <span className="w-10 text-right font-medium text-slate-300 data-text shrink-0">{fmtDelta(deltaMs)}</span>
        <span className="text-slate-700 mx-1">|</span>
        <label htmlFor="hold-slider" className="text-slate-600 shrink-0 font-medium">HOLD%</label>
        <input
          id="hold-slider"
          data-testid="hold-threshold-slider"
          type="range"
          min={0.1}
          max={5.0}
          step={0.1}
          value={holdThresholdPct}
          onChange={(e) => setHoldThresholdPct(Number(e.target.value))}
          className={`w-16 ${inputClass}`}
        />
        <span className="w-8 text-right font-medium text-slate-300 data-text shrink-0">{fmtPct(holdThresholdPct)}</span>
      </div>
    );
  }

  return (
    <div className="border-b border-slate-800 px-3 py-2 text-xs space-y-2">
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
          className={`flex-1 ${inputClass}`}
        />
        <span className="w-12 text-right font-medium text-slate-300 data-text">{fmtDelta(deltaMs)}</span>
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
          className={`flex-1 ${inputClass}`}
        />
        <span className="w-12 text-right font-medium text-slate-300 data-text">{fmtPct(holdThresholdPct)}</span>
      </div>
    </div>
  );
}
