import { useState } from "react";
import { downloadSingleTicker } from "../lib/api";

interface Props {
  ticker: string;
  onClose: () => void;
}

type Format = "zip" | "csv" | "json";

const formats: { value: Format; label: string; desc: string }[] = [
  { value: "zip", label: "ZIP", desc: "All data bundled with raw files + summary" },
  { value: "csv", label: "CSV", desc: "Tabular run data — ideal for spreadsheets" },
  { value: "json", label: "JSON", desc: "Full structured data — ideal for analysis" },
];

export default function DownloadFormatDialog({ ticker, onClose }: Props) {
  const [selected, setSelected] = useState<Format>("zip");
  const [loading, setLoading] = useState(false);

  const handleDownload = async () => {
    setLoading(true);
    try {
      await downloadSingleTicker(ticker, selected);
      onClose();
    } catch (err) {
      console.error("Download failed:", err);
      alert("Download failed. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl w-full mx-4 max-w-sm">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/60">
          <h2 className="text-sm font-semibold text-slate-200">Download {ticker} Data</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none px-1">
            &times;
          </button>
        </div>

        <div className="px-4 py-3 space-y-2">
          {formats.map((f) => (
            <label
              key={f.value}
              className={`flex items-start gap-3 px-3 py-2.5 rounded-lg cursor-pointer border transition-colors ${
                selected === f.value
                  ? "bg-sky-500/10 border-sky-500/40"
                  : "border-transparent hover:bg-slate-700/40"
              }`}
            >
              <input
                type="radio"
                name="format"
                value={f.value}
                checked={selected === f.value}
                onChange={() => setSelected(f.value)}
                className="accent-sky-500 shrink-0 mt-0.5"
              />
              <div>
                <div className="text-sm font-medium text-slate-200">{f.label}</div>
                <div className="text-xs text-slate-500 mt-0.5">{f.desc}</div>
              </div>
            </label>
          ))}
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-slate-700/60">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleDownload}
            disabled={loading}
            className="px-3 py-1.5 text-sm bg-sky-600 text-white rounded-lg hover:bg-sky-500 disabled:opacity-40 transition-colors"
          >
            {loading ? "Preparing…" : `Download ${selected.toUpperCase()}`}
          </button>
        </div>
      </div>
    </div>
  );
}