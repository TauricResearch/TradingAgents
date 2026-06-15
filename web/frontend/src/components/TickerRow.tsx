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
  const [showGroupInput, setShowGroupInput] = useState(false);
  const [groupInput, setGroupInput] = useState(group ?? "");

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

  const handleGroupSubmit = () => {
    const newGroup = groupInput.trim() || null;
    onGroupChange?.(ticker, newGroup);
    setShowGroupInput(false);
  };

  const gc = groupColor ?? GROUP_COLORS[0];

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => setFocused(ticker)}
      onKeyDown={handleKeyDown}
      data-focused={isFocused}
      draggable={dragHandleProps?.draggable ?? false}
      onDragStart={dragHandleProps?.onDragStart}
      onDragOver={dragHandleProps?.onDragOver}
      onDrop={onDrop}
      onDragEnd={dragHandleProps?.onDragEnd}
      className={`relative group w-full text-left px-3 py-2.5 rounded-xl flex items-center gap-2 transition-all duration-150 cursor-pointer ${
        isFocused
          ? "bg-sky-500/10 ring-1 ring-sky-500/30 shadow-[0_0_12px_rgba(56,189,248,0.08)]"
          : "hover:bg-slate-800/60"
      } ${dragHandleProps?.draggable ? "opacity-100" : ""}`}
    >
      {/* Drag handle */}
      <span
        className="shrink-0 flex flex-col gap-0.5 cursor-grab active:cursor-grabbing opacity-0 group-hover:opacity-40 hover:opacity-60 transition-opacity px-0.5"
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
          {group && (
            <span
              className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-md border cursor-pointer hover:brightness-125"
              style={{ backgroundColor: `${gc}18`, color: gc, borderColor: `${gc}40` }}
              onClick={(e) => { e.stopPropagation(); setShowGroupInput(!showGroupInput); }}
              title="Click to change group"
            >
              {group}
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
      {showGroupInput && (
        <div className="absolute top-full left-0 right-0 z-50 mt-0.5 mx-2" onClick={(e) => e.stopPropagation()}>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-2 shadow-xl">
            <input
              autoFocus
              type="text"
              value={groupInput}
              onChange={(e) => setGroupInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleGroupSubmit(); if (e.key === "Escape") setShowGroupInput(false); }}
              placeholder="Group name or empty to remove"
              className="w-full px-2 py-1 text-xs bg-slate-900 border border-slate-700 rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/50"
            />
            <div className="flex justify-end gap-1 mt-1.5">
              <button
                type="button"
                onClick={() => { setGroupInput(group ?? ""); setShowGroupInput(false); }}
                className="text-[10px] text-slate-500 hover:text-slate-300 px-2 py-0.5"
              >Cancel</button>
              <button
                type="button"
                onClick={handleGroupSubmit}
                className="text-[10px] text-sky-400 hover:text-sky-300 px-2 py-0.5 font-medium"
              >Save</button>
            </div>
          </div>
        </div>
      )}
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
