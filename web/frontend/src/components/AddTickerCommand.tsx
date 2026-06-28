import { useState } from "react";
import { Plus, Search } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { addToWatchlist, ApiError } from "../lib/api";

function describeAddError(e: unknown, ticker: string): string {
  if (e instanceof ApiError) {
    // FastAPI wraps HTTPException detail under "detail".
    const detail = (e.body as { detail?: { error?: string } } | null)?.detail;
    if (e.status === 400 && detail?.error === "ticker_not_found") {
      return `Ticker "${ticker}" was not found on Yahoo Finance. Check the symbol and try again.`;
    }
    if (e.status === 409) {
      return `"${ticker}" is already in your watchlist.`;
    }
  }
  return `Could not add "${ticker}". Please try again.`;
}

export function AddTickerCommand() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  async function submit() {
    if (!value) return;
    const ticker = value.toUpperCase();
    try {
      await addToWatchlist(ticker, "", "");
      setValue("");
      setOpen(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    } catch (e) {
      setError(describeAddError(e, ticker));
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full text-left px-4 py-2.5 text-sm text-slate-500 hover:text-slate-300 hover:bg-slate-800/60 transition-colors flex items-center gap-2"
      >
        <Plus className="w-4 h-4" />
        Add ticker
      </button>
    );
  }

  return (
    <div className="p-3 border-t border-slate-800">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-600" />
        <input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder="Ticker symbol (e.g. NVDA)"
          className="w-full pl-8 pr-3 py-1.5 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500/30 transition-all"
        />
      </div>
      {error && <p className="text-xs text-red-400 mt-1.5 ml-1" role="alert">{error}</p>}
    </div>
  );
}
