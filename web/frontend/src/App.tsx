import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist } from "./lib/api";
import { useUi } from "./store/ui";

export default function App() {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const { data: watchlist } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });

  useEffect(() => {
    if (!focused && watchlist && watchlist.length > 0) setFocused(watchlist[0].ticker);
  }, [watchlist, focused, setFocused]);

  return (
    <div className="min-h-screen p-6 text-[hsl(var(--foreground))]">
      <h1 className="text-xl font-semibold mb-4">TradingAgents</h1>
      <p className="text-sm text-[hsl(var(--muted-foreground))]">
        Focused ticker: <code>{focused ?? "(none)"}</code>. Components arrive in the next tasks.
      </p>
    </div>
  );
}
