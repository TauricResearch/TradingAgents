import { useState, useEffect, useRef } from "react";
import { downloadTickers } from "../lib/api";

interface Props {
  tickers: string[];
  onClose: () => void;
}

export default function BatchDownloadDialog({ tickers, onClose }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  const allSelected = tickers.length > 0 && selected.size === tickers.length;
  const someSelected = selected.size > 0 && selected.size < tickers.length;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(tickers));
    }
  };

  const toggleTicker = (ticker: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) {
        next.delete(ticker);
      } else {
        next.add(ticker);
      }
      return next;
    });
  };

  const handleDownload = async () => {
    if (selected.size === 0) return;
    setLoading(true);
    try {
      await downloadTickers(Array.from(selected));
      onClose();
    } catch (err) {
      console.error("Download failed:", err);
      alert("Download failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div
        ref={modalRef}
        className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl max-w-md w-full mx-4 max-h-[80vh] flex flex-col"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
          <h2 className="text-sm font-semibold text-slate-200">Download Ticker Data</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none px-1">
            &times;
          </button>
        </div>

        <div className="px-4 py-2 border-b border-slate-700/40">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={allSelected}
              ref={(el) => {
                if (el) el.indeterminate = someSelected;
              }}
              onChange={toggleAll}
              className="accent-sky-500 shrink-0"
            />
            <span className="text-sm text-slate-300 font-medium">Select all ({tickers.length})</span>
          </label>
        </div>

        <div className="overflow-y-auto flex-1 px-2 py-2 space-y-1 min-h-[120px] max-h-[300px]">
          {tickers.length === 0 && (
            <div className="text-sm text-slate-500 text-center py-8">No tickers available</div>
          )}
          {tickers.map((ticker) => (
            <label
              key={ticker}
              className="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:bg-slate-700/40 transition-colors"
            >
              <input
                type="checkbox"
                checked={selected.has(ticker)}
                onChange={() => toggleTicker(ticker)}
                className="accent-sky-500 shrink-0"
              />
              <span className="text-sm text-slate-300">{ticker}</span>
            </label>
          ))}
        </div>

        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/60">
          <span className="text-xs text-slate-500">{selected.size} selected</span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleDownload}
              disabled={selected.size === 0 || loading}
              className="px-3 py-1.5 text-sm bg-sky-600 text-white rounded-lg hover:bg-sky-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Preparing…" : `Download (${selected.size})`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}