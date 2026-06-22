import { useEffect, useRef, useState } from "react";
import { Terminal, X, Trash2 } from "lucide-react";
import { useLogStore } from "../store/logs";
import { useLogStream } from "../hooks/useLogStream";

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-gray-400",
  INFO: "text-blue-400",
  WARNING: "text-amber-400",
  ERROR: "text-red-400",
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

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full bg-slate-800 px-3 py-2 text-sm text-slate-300 shadow-lg hover:bg-slate-700"
        title="Logs"
      >
        <Terminal size={16} />
        {status === "open" && <span className="h-2 w-2 rounded-full bg-emerald-400" />}
        {status === "connecting" && <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />}
      </button>

      {/* Panel */}
      {open && (
        <div className="fixed bottom-16 right-4 z-50 flex h-[40vh] w-[600px] flex-col rounded-xl bg-slate-900/95 shadow-2xl backdrop-blur border border-slate-700">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-700 px-4 py-2">
            <span className="text-sm font-medium text-slate-300">Logs ({entries.length})</span>
            <div className="flex items-center gap-2">
              {(["DEBUG", "INFO", "WARNING", "ERROR"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => toggleLevel(l)}
                  className={`text-xs px-1.5 py-0.5 rounded ${levelFilter.has(l) ? `bg-slate-700 ${LEVEL_COLORS[l]}` : "text-slate-600"}`}
                >
                  {l}
                </button>
              ))}
              <input
                type="text"
                placeholder="search..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-32 rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300 placeholder-slate-500"
              />
              <button onClick={clear} className="rounded p-1 hover:bg-slate-700 text-slate-400" title="Clear">
                <Trash2 size={14} />
              </button>
              <button onClick={() => setOpen(false)} className="rounded p-1 hover:bg-slate-700 text-slate-400">
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Log list */}
          <div ref={listRef} className="flex-1 overflow-y-auto font-mono text-xs" onScroll={handleScroll}>
            {filtered.length === 0 && (
              <div className="flex h-full items-center justify-center text-slate-500">No logs</div>
            )}
            {filtered.map((e) => (
              <div key={e.id} className={`flex gap-2 px-3 py-0.5 border-b border-slate-800/50 ${SOURCE_ACCENT[e.source] ?? ""}`}>
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