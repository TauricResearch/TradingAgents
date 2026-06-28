import { useCallback, useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { addToWatchlist, ApiError } from "../lib/api";
import { useUi } from "../store/ui";

export function WatchlistFilter() {
  const qc = useQueryClient();
  const setFocusedTicker = useUi((s) => s.setFocusedTicker);
  const [filterTicker, setFilterTicker] = useState("");
  const [filterTickerRaw, setFilterTickerRaw] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [addingTicker, setAddingTicker] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setFilterTicker(filterTickerRaw.toUpperCase());
    }, 200);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [filterTickerRaw]);

  const handleAddFromFilter = useCallback(async () => {
    const ticker = filterTicker.trim().toUpperCase();
    if (!ticker) return;
    setAddingTicker(true);
    setAddError(null);
    try {
      await addToWatchlist(ticker, "", "");
      setFilterTicker("");
      setFilterTickerRaw("");
      setAddError(null);
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    } catch (e) {
      if (e instanceof ApiError) {
        const detail = (e.body as { detail?: { error?: string } } | null)?.detail;
        if (e.status === 400 && detail?.error === "ticker_not_found") {
          setAddError(`"${ticker}" was not found on Yahoo Finance.`);
        } else if (e.status === 409) {
          setAddError(`"${ticker}" is already in the watchlist.`);
          setFilterTicker("");
          setFilterTickerRaw("");
        } else {
          setAddError(`Could not add "${ticker}". Try again.`);
        }
      } else {
        setAddError(`Could not add "${ticker}". Try again.`);
      }
    } finally {
      setAddingTicker(false);
    }
  }, [filterTicker, qc]);

  return (
    <div className="shrink-0 px-4 py-3 border-b border-slate-800">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" />
        <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Watchlist</span>
      </div>
      <div className="relative mt-2">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-600 pointer-events-none" />
        <input
          type="text"
          value={filterTickerRaw}
          onChange={(e) => { setFilterTickerRaw(e.target.value); setAddError(null); }}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || !filterTickerRaw) return;
            setFocusedTicker(filterTicker.toUpperCase());
            handleAddFromFilter();
          }}
          placeholder="Search or add ticker…"
          className="w-full bg-slate-800/60 border border-slate-700/50 rounded-md pl-7 pr-7 py-1.5 text-xs text-slate-300 placeholder-slate-500 outline-none focus:border-slate-600 focus:bg-slate-800 focus:ring-1 focus:ring-sky-500/30 transition-colors"
        />
        {filterTickerRaw && (
          <button
            type="button"
            onClick={() => { setFilterTickerRaw(""); setFilterTicker(""); setAddError(null); }}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      {addError && <p className="text-xs text-red-400 mt-2" role="alert">{addError}</p>}
      {addingTicker && <p className="text-xs text-sky-400 mt-2">Adding {filterTicker}…</p>}
    </div>
  );
}
