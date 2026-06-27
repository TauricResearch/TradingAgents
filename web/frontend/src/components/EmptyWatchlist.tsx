export function EmptyWatchlist() {
  return (
    <div className="mt-24 text-center animate-fade-in">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-slate-800/60 border border-slate-700/50 mb-4">
        <svg className="w-8 h-8 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
        </svg>
      </div>
      <p className="text-base font-medium text-slate-400">Your watchlist is empty</p>
      <p className="text-sm text-slate-600 mt-1">Add tickers using the &ldquo;+ Add ticker&rdquo; box in the sidebar.</p>
    </div>
  );
}
