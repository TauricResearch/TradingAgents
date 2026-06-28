import { useEffect, useRef, useState } from "react";
import { Terminal, X, Trash2, Search } from "lucide-react";
import { useLogStore } from "../store/logs";
import { useLogStream } from "../hooks/useLogStream";

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-gray-400",
  INFO: "text-blue-400",
  WARNING: "text-amber-400",
  ERROR: "text-red-400",
};

const LEVEL_BG: Record<string, string> = {
  DEBUG: "bg-gray-500/10 hover:bg-gray-500/20",
  INFO: "bg-blue-500/10 hover:bg-blue-500/20",
  WARNING: "bg-amber-500/10 hover:bg-amber-500/20",
  ERROR: "bg-red-500/10 hover:bg-red-500/20",
};

const SOURCE_ACCENT: Record<string, string> = {
  server: "border-l-2 border-l-sky-500",
  client: "border-l-2 border-l-emerald-500",
};

export function LogPanel() {
  const { status } = useLogStream();
  const entries = useLogStore((s) => s.entries);
  const clear = useLogStore((s) => s.clear);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState<Set<string>>(new Set(["DEBUG", "INFO", "WARNING", "ERROR"]));
  const [autoScroll, setAutoScroll] = useState(true);
  const [confirmClear, setConfirmClear] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = entries.filter((e) => {
    if (!levelFilter.has(e.level)) return false;
    if (filter && !e.message.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (!autoScroll) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, autoScroll]);

  const handleScroll = () => {
    const el = listRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    setAutoScroll(atBottom);
  };

  const toggleLevel = (l: string) => {
    setLevelFilter((prev) => {
      const next = new Set(prev);
      next.has(l) ? next.delete(l) : next.add(l);
      return next;
    });
  };

  const handleClear = () => {
    if (confirmClear) {
      clear();
      setConfirmClear(false);
    } else {
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 2000);
    }
  };

  const allLevels: Array<"DEBUG" | "INFO" | "WARNING" | "ERROR"> = ["DEBUG", "INFO", "WARNING", "ERROR"];

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full bg-slate-800/90 px-3 py-2 text-sm text-slate-300 shadow-lg hover:bg-slate-700/90 border border-slate-700/50 transition-all duration-200"
        title={open ? "Close logs" : "Open logs"}
      >
        <Terminal size={16} />
        {status === "open" && <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" />}
        {status === "connecting" && <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />}
      </button>

      {/* Panel */}
      {open && (
        <div className="fixed bottom-16 right-4 z-50 flex h-[40vh] w-[600px] max-w-[calc(100vw-2rem)] flex-col rounded-xl bg-slate-900/95 shadow-2xl backdrop-blur-md border border-slate-700/50 animate-slide-up">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-700/50 px-4 py-2.5 shrink-0">
            <span className="text-sm font-medium text-slate-300">
              Logs
              <span className="ml-1.5 text-xs text-slate-500">({entries.length})</span>
            </span>
            <div className="flex items-center gap-1.5">
              <div className="flex items-center gap-0.5 bg-slate-800/60 rounded-lg p-0.5">
                {allLevels.map((l) => {
                  const active = levelFilter.has(l);
                  return (
                    <button
                      key={l}
                      onClick={() => toggleLevel(l)}
                      className={`text-[10px] font-medium px-1.5 py-0.5 rounded-md transition-all ${
                        active
                          ? `${LEVEL_COLORS[l]} bg-slate-700/80 shadow-sm`
                          : "text-slate-600 hover:text-slate-400"
                      }`}
                    >
                      {l}
                    </button>
                  );
                })}
              </div>
              <div className="relative">
                <Search className="absolute left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-600 pointer-events-none" />
                <input
                  type="text"
                  placeholder="Search..."
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="w-28 rounded-lg bg-slate-800 pl-6 pr-2 py-1 text-xs text-slate-300 placeholder-slate-500 border border-slate-700/50 focus:outline-none focus:border-sky-500/40 transition-colors"
                />
              </div>
              <button
                onClick={handleClear}
                className={`rounded-lg p-1.5 transition-all ${
                  confirmClear
                    ? "bg-red-500/20 text-red-400"
                    : "hover:bg-slate-700/50 text-slate-500 hover:text-slate-300"
                }`}
                title={confirmClear ? "Click again to clear" : "Clear logs"}
              >
                <Trash2 size={14} />
              </button>
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-1.5 hover:bg-slate-700/50 text-slate-500 hover:text-slate-300 transition-colors"
                title="Close"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Log list */}
          <div ref={listRef} className="flex-1 overflow-y-auto font-mono text-xs" onScroll={handleScroll}>
            {filtered.length === 0 && (
              <div className="flex h-full items-center justify-center text-slate-500 text-sm">
                {entries.length === 0 ? "No logs yet" : "No matching logs"}
              </div>
            )}
            {filtered.map((e) => (
              <div
                key={e.id}
                className={`flex gap-2 px-3 py-0.5 border-b border-slate-800/30 hover:bg-slate-800/40 transition-colors ${SOURCE_ACCENT[e.source] ?? ""}`}
              >
                <span className="w-16 shrink-0 text-slate-500">{e.ts?.split("T")[1]?.slice(0, 8) ?? ""}</span>
                <span className={`w-16 shrink-0 ${LEVEL_COLORS[e.level] ?? "text-slate-400"}`}>{e.level}</span>
                <span className="w-20 shrink-0 truncate text-slate-500">{e.logger}</span>
                <span className={`flex-1 break-all ${LEVEL_COLORS[e.level] ?? "text-slate-300"}`}>{e.message}</span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </>
  );
}
