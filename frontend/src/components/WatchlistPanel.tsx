/** Watchlist over the persisted CRUD API: live/EOD price per symbol,
 * 30-day sparkline, add/remove. Symbols validate against /api/symbols —
 * the panel can only watch what the data layer can actually serve. */
import { useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "./EmptyState";
import { Sparkline } from "./Sparkline";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { SkeletonCard } from "./ui/skeleton";
import {
  deleteWatchlist,
  upsertWatchlist,
  useBars,
  useOverview,
  useSymbols,
  useWatchlists,
} from "@/lib/api/queries";
import { fmtPrice } from "@/lib/format";
import { useTick } from "@/stores/ticker";

function WatchRow({ symbol, onRemove }: { symbol: string; onRemove: () => void }) {
  const tick = useTick(symbol);
  const overview = useOverview();
  const spark = useBars(symbol, "1d", 30);
  const fallback = overview.data?.symbol === symbol ? overview.data.last_close : null;
  const price = tick?.last ?? fallback;
  return (
    <li className="flex items-center gap-2 border-b border-border/50 py-1.5">
      <span
        aria-hidden="true"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[10px] bg-surface-2 text-[10px] font-bold text-fg-muted"
      >
        {symbol.slice(0, 2).toUpperCase()}
      </span>
      <Link
        to={`/trade/${symbol}`}
        className="w-20 shrink-0 font-mono text-sm hover:text-accent"
      >
        {symbol}
      </Link>
      <span className="w-24 shrink-0 text-right font-mono text-sm tabular">
        {fmtPrice(price)}
      </span>
      <span className="w-10 shrink-0 text-[10px] text-fg-subtle">
        {tick ? "live" : price != null ? "EOD" : "—"}
      </span>
      <span className="grow">
        {spark.data && spark.data.length > 1 ? (
          <Sparkline
            values={spark.data.map((b) => b.close)}
            width={90}
            height={20}
            ariaLabel={`${symbol} 30-day trend`}
          />
        ) : spark.isError ? (
          <span className="text-[10px] text-stale">no data</span>
        ) : null}
      </span>
      <Button
        size="icon"
        variant="ghost"
        className="h-6 w-6"
        aria-label={`remove ${symbol}`}
        onClick={onRemove}
      >
        <X size={12} />
      </Button>
    </li>
  );
}

const LIST_NAME = "default";

export function WatchlistPanel() {
  const watchlists = useWatchlists();
  const symbols = useSymbols();
  const client = useQueryClient();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (watchlists.isPending) return <SkeletonCard lines={3} />;

  const list = watchlists.data?.find((w) => w.name === LIST_NAME);
  const watched = list?.symbols ?? [];
  const known = (symbols.data ?? []).map((s) => s.symbol);

  const add = async () => {
    const symbol = draft.trim().toUpperCase();
    if (!symbol) return;
    if (!known.includes(symbol)) {
      setError(`Unknown symbol. Available: ${known.join(", ")}`);
      return;
    }
    if (watched.includes(symbol)) {
      setError("Already watching.");
      return;
    }
    setError(null);
    setDraft("");
    await upsertWatchlist(client, {
      name: LIST_NAME,
      symbols: [...watched, symbol],
    });
  };

  const remove = async (symbol: string) => {
    const remaining = watched.filter((s) => s !== symbol);
    if (remaining.length === 0) await deleteWatchlist(client, LIST_NAME);
    else await upsertWatchlist(client, { name: LIST_NAME, symbols: remaining });
  };

  return (
    <div data-testid="watchlist-panel">
      {watched.length === 0 ? (
        <EmptyState
          kind="empty"
          title="Nothing watched yet"
          detail={`Add any served symbol: ${known.join(", ") || "loading…"}`}
        />
      ) : (
        <ul>
          {watched.map((symbol) => (
            <WatchRow
              key={symbol}
              symbol={symbol}
              onRemove={() => void remove(symbol)}
            />
          ))}
        </ul>
      )}
      <form
        className="mt-2 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void add();
        }}
      >
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Add symbol (e.g. DXY)"
          aria-label="Add symbol to watchlist"
          className="h-7 text-xs"
        />
        <Button size="sm" type="submit" variant="outline">
          <Plus size={12} /> Add
        </Button>
      </form>
      {error && <p className="mt-1 text-xs text-bear">{error}</p>}
    </div>
  );
}
