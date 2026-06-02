import { useUi } from "../store/ui";

interface Props {
  ticker: string;
  companyName: string;
  lastDecision: string | null;
  sparkline: number[];
  status: "idle" | "queued" | "running" | "done" | "errored";
}

const dotColor: Record<Props["status"], string> = {
  idle: "bg-slate-300",
  queued: "bg-amber-400",
  running: "bg-blue-500 animate-pulse",
  done: "bg-emerald-500",
  errored: "bg-rose-500",
};

export function TickerRow({ ticker, companyName, lastDecision, sparkline, status }: Props) {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const isFocused = focused === ticker;

  const sparkPath = sparkline.length > 1
    ? sparkline.map((v, i) => `${i === 0 ? "M" : "L"} ${i * 4} ${20 - v}`).join(" ")
    : "";

  return (
    <button
      onClick={() => setFocused(ticker)}
      data-focused={isFocused}
      className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-3 hover:bg-slate-50 ${
        isFocused ? "bg-blue-50 ring-1 ring-blue-200" : ""
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${dotColor[status]}`} />
      <div className="flex-1">
        <div className="text-sm font-semibold">{ticker}</div>
        <div className="text-xs text-slate-500 truncate">{companyName || lastDecision || "—"}</div>
      </div>
      <svg width="40" height="20" className="opacity-60">
        {sparkPath && <path d={sparkPath} stroke="rgb(59 130 246)" strokeWidth="1" fill="none" />}
      </svg>
    </button>
  );
}
