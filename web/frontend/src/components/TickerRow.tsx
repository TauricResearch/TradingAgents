import { useState } from "react";
import { useUi } from "../store/ui";

interface Props {
  ticker: string;
  companyName: string;
  lastDecision: string | null;
  sparkline: number[];
  status: "idle" | "queued" | "running" | "done" | "errored";
  price?: number;
  changePct?: number;
  /** True when the price feed has flagged the symbol as stale (delisted,
   *  invalid, or unreachable). Surfaces a clear "unavailable" indicator
   *  so the user knows the price/change shown is unreliable. */
  stale?: boolean;
  onRemove?: (ticker: string) => void | Promise<void>;
}

const dotColor: Record<Props["status"], string> = {
  idle: "bg-slate-600",
  queued: "bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.4)]",
  running: "bg-sky-400 animate-pulse shadow-[0_0_8px_rgba(56,189,248,0.5)]",
  done: "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)]",
  errored: "bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]",
};

export function TickerRow({ ticker, companyName, lastDecision, sparkline, status, price, changePct, stale, onRemove }: Props) {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const isFocused = focused === ticker;
  const [pending, setPending] = useState(false);

  const sparkPath = sparkline.length > 1
    ? sparkline.map((v, i) => `${i === 0 ? "M" : "L"} ${i * 4} ${20 - v}`).join(" ")
    : "";

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setFocused(ticker);
    }
  };

  const showChange = changePct != null && !isNaN(changePct);
  const changeColor = showChange ? (changePct >= 0 ? "text-emerald-600" : "text-rose-600") : "text-slate-400";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => setFocused(ticker)}
      onKeyDown={handleKeyDown}
      data-focused={isFocused}
      className={`group w-full text-left px-3 py-2.5 rounded-xl flex items-center gap-3 transition-all duration-150 cursor-pointer ${
        isFocused
          ? "bg-sky-500/10 ring-1 ring-sky-500/30 shadow-[0_0_12px_rgba(56,189,248,0.08)]"
          : "hover:bg-slate-800/60"
      }`}
    >
      <span className={`h-2 w-2 rounded-full shrink-0 ${dotColor[status]}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-slate-100">{ticker}</span>
          {stale ? (
            <span
              data-testid={`ticker-row-${ticker}-unavailable`}
              className="text-[10px] uppercase tracking-wider font-medium text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-md px-1.5 py-0.5"
            >
              unavailable
            </span>
          ) : price != null && !isNaN(price) ? (
            <span className="text-xs data-text text-slate-400">
              ${price.toFixed(2)}
            </span>
          ) : null}
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-xs text-slate-600 truncate">
            {stale ? "Price data unavailable" : companyName || lastDecision || "—"}
          </span>
          {!stale && showChange && (
            <span className={`text-xs data-text font-medium ${changeColor}`}>
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          )}
        </div>
      </div>
      <svg width="40" height="20" className="opacity-40 shrink-0" aria-hidden="true">
        {sparkPath && <path d={sparkPath} stroke={isFocused ? "#38bdf8" : "#475569"} strokeWidth="1.5" fill="none" />}
      </svg>
      {!pending ? (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setPending(true); }}
          aria-label={`Remove ${ticker} from watchlist`}
          className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 text-sm px-1 shrink-0 transition-opacity"
        >
          ×
        </button>
      ) : (
        <span className="flex items-center gap-1 text-xs shrink-0" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={async (e) => { e.stopPropagation(); await onRemove?.(ticker); }}
            className="text-red-400 hover:text-red-300 hover:underline"
          >Remove</button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setPending(false); }}
            className="text-slate-500 hover:text-slate-400 hover:underline"
          >Cancel</button>
        </span>
      )}
    </div>
  );
}
