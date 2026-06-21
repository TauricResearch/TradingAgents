import { useState } from "react";
import { useUi } from "../store/ui";
import { useQuery } from "@tanstack/react-query";
import { getAccuracyLeaderboard } from "../lib/api";

interface Props {
  ticker: string;
  companyName: string;
  lastDecision: string | null;
  sparkline: number[];
  status: "idle" | "queued" | "running" | "done" | "errored";
  price?: number;
  changePct?: number | null;
  stale?: boolean;
  onRemove?: (ticker: string) => void | Promise<void>;
  group?: string | null;
  groupColor?: string;
  onGroupChange?: (ticker: string, group: string | null) => void;
  onDrop?: (e: React.DragEvent) => void;
  dragHandleProps?: {
    draggable: boolean;
    onDragStart: (e: React.DragEvent) => void;
    onDragOver?: (e: React.DragEvent) => void;
    onDragEnd?: (e: React.DragEvent) => void;
  };
}

const dotColor: Record<Props["status"], string> = {
  idle: "bg-slate-600",
  queued: "bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.4)]",
  running: "bg-sky-400 animate-pulse shadow-[0_0_8px_rgba(56,189,248,0.5)]",
  done: "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)]",
  errored: "bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]",
};

const GROUP_COLORS = ["#38bdf8", "#fb923c", "#a78bfa", "#34d399", "#f472b6", "#fbbf24", "#f87171", "#2dd4bf"];

export function TickerRow({ ticker, companyName, lastDecision, sparkline, status, price, changePct, stale, onRemove, group, groupColor, onGroupChange, onDrop, dragHandleProps }: Props) {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const isFocused = focused === ticker;
  const [pending, setPending] = useState(false);
  const [isDragOver, setDragOver] = useState(false);

  const { data: leaderboardData } = useQuery({
    queryKey: ["ticker-agent", "leaderboard"],
    queryFn: getAccuracyLeaderboard,
    refetchInterval: 30000,
    staleTime: 10000,
  });
  const tickerAccuracy = leaderboardData?.scores?.[ticker];
  const accuracyPct = tickerAccuracy?.accuracy_pct;

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

  const gc = groupColor ?? GROUP_COLORS[0];

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    // Only hide when actually leaving this element (not entering a child)
    if (e.currentTarget === e.target || !e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragOver(false);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => setFocused(ticker)}
      onKeyDown={handleKeyDown}
      data-focused={isFocused}
      draggable={dragHandleProps?.draggable ?? false}
      onDragStart={dragHandleProps?.onDragStart}
      onDragOver={(e) => {
        e.preventDefault();
        dragHandleProps?.onDragOver?.(e);
        setDragOver(true);
      }}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragOver(false);
        onDrop?.(e);
      }}
      onDragEnd={(e) => {
        setDragOver(false);
        dragHandleProps?.onDragEnd?.(e);
      }}
      className={`relative group w-full text-left px-3 py-2.5 rounded-xl flex items-center gap-2 transition-colors duration-150 cursor-pointer ${
        isFocused
          ? "bg-sky-500/10 ring-1 ring-sky-500/30 shadow-[0_0_12px_rgba(56,189,248,0.08)]"
          : isDragOver
            ? "bg-sky-500/5"
            : "hover:bg-slate-800/60"
      } ${dragHandleProps?.draggable ? "opacity-100" : ""} ${isDragOver ? "shadow-[inset_0_2px_0_0_rgba(56,189,248,0.4)]" : ""}`}
    >
      {/* Drag handle */}
      <span
        className="shrink-0 flex flex-col gap-0.5 cursor-grab active:cursor-grabbing opacity-30 md:group-hover:opacity-70 hover:opacity-100 transition-opacity px-0.5"
        onMouseDown={(e) => e.stopPropagation()}
        aria-label={`Drag ${ticker} to reorder`}
      >
        <svg width="8" height="14" viewBox="0 0 8 14" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-slate-500">
          <circle cx="2" cy="2" r="1" fill="currentColor" stroke="none" />
          <circle cx="6" cy="2" r="1" fill="currentColor" stroke="none" />
          <circle cx="2" cy="7" r="1" fill="currentColor" stroke="none" />
          <circle cx="6" cy="7" r="1" fill="currentColor" stroke="none" />
          <circle cx="2" cy="12" r="1" fill="currentColor" stroke="none" />
          <circle cx="6" cy="12" r="1" fill="currentColor" stroke="none" />
        </svg>
      </span>
      <span className={`h-2 w-2 rounded-full shrink-0 ${dotColor[status]}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1.5">
          <span className="text-sm font-semibold text-slate-100">{ticker}</span>
          {accuracyPct !== null && accuracyPct !== undefined && (
            <span className={`tag text-[10px] px-1 py-0.5 ${
              accuracyPct >= 70 ? "tag-buy" :
              accuracyPct >= 40 ? "tag-hold" :
              "tag-sell"
            }`}>
              {accuracyPct.toFixed(0)}%
            </span>
          )}
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
          {!stale && showChange ? (
            <span className={`text-xs data-text font-medium ${changeColor}`}>
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          ) : !stale ? (
            <span className="text-xs data-text font-medium text-slate-500">N/A</span>
          ) : null}
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
          className="md:opacity-0 md:group-hover:opacity-100 text-slate-500 hover:text-red-400 text-sm px-2 py-2 shrink-0 transition-opacity"
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
