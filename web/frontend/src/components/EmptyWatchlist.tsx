import { LineChart } from "lucide-react";

export function EmptyWatchlist() {
  return (
    <div className="mt-24 text-center animate-fade-in">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-slate-800/60 border border-slate-700/50 mb-4">
        <LineChart className="w-8 h-8 text-slate-500" />
      </div>
      <p className="text-base font-medium text-slate-400">Your watchlist is empty</p>
      <p className="text-sm text-slate-600 mt-1 max-w-sm mx-auto">
        Search for a ticker in the sidebar and press Enter to add it.
      </p>
    </div>
  );
}
