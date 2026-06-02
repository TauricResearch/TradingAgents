import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { addToWatchlist } from "../lib/api";

export function AddTickerCommand() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  async function submit() {
    if (!value) return;
    try {
      await addToWatchlist(value.toUpperCase(), "", "");
      setValue("");
      setOpen(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    } catch (e) {
      setError("Could not add (maybe already in watchlist?)");
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full text-left px-3 py-2 text-sm text-slate-500 hover:bg-slate-50 rounded-lg"
      >
        + Add ticker
      </button>
    );
  }

  return (
    <div className="p-2">
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Ticker symbol (e.g. NVDA)"
        className="w-full px-2 py-1 text-sm border border-slate-200 rounded"
      />
      {error && <p className="text-xs text-rose-500 mt-1">{error}</p>}
    </div>
  );
}
