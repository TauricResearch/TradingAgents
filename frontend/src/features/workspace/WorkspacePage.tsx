/** Trading Workspace: chart-first with decision-level overlays, symbol
 * internals, positions. Honestly cut: no fake DOM ladder (only an
 * imbalance scalar exists), no manual order ticket (the loop is
 * autonomous; operator controls are pause/kill). */
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { DecisionCard } from "@/components/DecisionCard";
import { EmptyState } from "@/components/EmptyState";
import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import { PriceChart, type SeriesStyle, type TradeMarker } from "@/components/charts/PriceChart";
import {
  useBars,
  useCalendar,
  useIntel,
  useJournal,
  useOverview,
  useRecommendation,
  useStatus,
  useSymbols,
} from "@/lib/api/queries";
import { fmtPnl, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

const STYLES: { id: SeriesStyle; label: string }[] = [
  { id: "candles", label: "Candles" },
  { id: "heikin-ashi", label: "Heikin Ashi" },
  { id: "line", label: "Line" },
  { id: "area", label: "Area" },
];

function InternalsPanel({ symbol }: { symbol: string }) {
  const intel = useIntel();
  if (intel.isPending) return <SkeletonCard lines={4} />;
  if (!intel.data) return <EmptyState kind="error" title="Internals unavailable" />;
  const metrics = new Map(intel.data.metrics.map((m) => [m.name, m]));
  const wanted =
    symbol === "BTC-USD"
      ? ["FUNDING_RATE", "OPEN_INTEREST", "MARK_PRICE", "ORDERBOOK_IMBALANCE", "FEAR_GREED"]
      : ["DXY", "US10Y_NOMINAL", "XAU_XAG_CORR", "US10Y_REAL"];
  const available = wanted.filter((name) => metrics.has(name));
  return (
    <div className="space-y-2">
      {available.length === 0 && (
        <EmptyState
          kind="waiting"
          title="No internals yet"
          detail={intel.data.missing_feeds.join("; ") || "feeds warming up"}
        />
      )}
      {available.map((name) => {
        const metric = metrics.get(name)!;
        return (
          <StatCard
            key={name}
            label={name.replaceAll("_", " ")}
            value={
              Math.abs(metric.value) < 0.01
                ? metric.value.toExponential(2)
                : fmtPrice(metric.value, 2)
            }
            sub={`${metric.source ?? ""} ${metric.unit ?? ""}`}
          />
        );
      })}
      {intel.data.missing_feeds.length > 0 && available.length > 0 && (
        <p className="text-xs text-stale">
          degraded: {intel.data.missing_feeds.map((f) => f.split(":")[0]).join(", ")}
        </p>
      )}
    </div>
  );
}

export default function WorkspacePage() {
  const params = useParams<{ symbol: string }>();
  const symbol = params.symbol ?? "BTC-USD";
  const { timeframe, setTimeframe, setSymbol } = useUiStore();
  const [style, setStyle] = useState<SeriesStyle>("candles");

  const symbols = useSymbols();
  const spec = symbols.data?.find((s) => s.symbol === symbol);
  const available = spec?.timeframes ?? ["1d"];
  const activeTf = available.includes(timeframe) ? timeframe : available[available.length - 1]!;

  const bars = useBars(symbol, activeTf, 300);
  const recommendation = useRecommendation();
  const overview = useOverview();
  const journal = useJournal();
  const status = useStatus();
  const calendar = useCalendar();

  // keep global symbol in sync with the route
  if (useUiStore.getState().symbol !== symbol) setSymbol(symbol);

  const recForSymbol =
    recommendation.data && recommendation.data.symbol === symbol
      ? recommendation.data
      : null;

  const markers: TradeMarker[] = useMemo(
    () =>
      (journal.data?.entries ?? [])
        .filter((entry) => entry.symbol === symbol)
        .map((entry) => ({
          time: Math.floor(new Date(entry.closed_at).getTime() / 1000),
          direction: entry.pnl >= 0 ? "bull" : "bear",
          label: `${entry.action ?? ""} ${fmtPnl(entry.pnl)}`,
        })),
    [journal.data, symbol],
  );

  const positions = (status.data?.open_positions ?? []).filter(
    (p) => p.symbol === symbol,
  );
  const nextRelease = calendar.data?.releases[0];

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
      <div className="min-w-0 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {symbol}
              {spec && !spec.live && <Badge variant="stale">EOD data</Badge>}
              {spec?.live && <Badge variant="bull">live</Badge>}
            </CardTitle>
            <div className="flex flex-wrap items-center gap-1 text-xs">
              {available.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  aria-pressed={tf === activeTf}
                  className={cn(
                    "rounded px-2 py-0.5 font-mono",
                    tf === activeTf
                      ? "bg-accent-muted text-accent"
                      : "text-fg-subtle hover:text-fg",
                  )}
                >
                  {tf}
                </button>
              ))}
              <span className="mx-1 text-border-strong">|</span>
              {STYLES.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setStyle(s.id)}
                  aria-pressed={style === s.id}
                  className={cn(
                    "rounded px-2 py-0.5",
                    style === s.id
                      ? "bg-accent-muted text-accent"
                      : "text-fg-subtle hover:text-fg",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            {bars.isPending ? (
              <SkeletonCard lines={8} />
            ) : bars.isError ? (
              <EmptyState
                kind="error"
                title="Chart data unavailable"
                detail={String(bars.error)}
              />
            ) : (
              <PriceChart
                bars={bars.data}
                style={style}
                recommendation={recForSymbol}
                markers={markers}
                liveSymbol={spec?.live || symbol === "BTC-USD" ? symbol : undefined}
              />
            )}
            {nextRelease && (
              <p className="mt-2 text-xs text-fg-subtle">
                next macro event: {nextRelease.release} on {nextRelease.date}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Open positions — {symbol}</CardTitle>
          </CardHeader>
          <CardContent>
            {positions.length === 0 ? (
              <EmptyState
                kind="empty"
                title="No open position"
                detail={
                  status.data?.attached
                    ? "The loop will enter when a recommendation clears every gate."
                    : "Monitor mode — no execution router attached."
                }
              />
            ) : (
              <table className="w-full text-sm tabular">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-fg-subtle">
                    <th className="py-1 font-medium">symbol</th>
                    <th className="py-1 text-right font-medium">quantity</th>
                    <th className="py-1 text-right font-medium">book state</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.symbol}>
                      <td className="py-1 font-mono">{p.symbol}</td>
                      <td className="py-1 text-right">
                        {p.quantity > 0 ? "+" : ""}
                        {p.quantity}
                      </td>
                      <td className="py-1 text-right text-bull">reconciled</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Decision</CardTitle>
          </CardHeader>
          <CardContent>
            {recommendation.isPending ? (
              <SkeletonCard lines={4} />
            ) : recForSymbol ? (
              <DecisionCard
                rec={recForSymbol}
                compact
                runId={overview.data?.run_id ?? null}
              />
            ) : (
              <EmptyState
                kind="empty"
                title={`No current decision for ${symbol}`}
                detail="The latest run targeted a different symbol."
              />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Market internals</CardTitle>
          </CardHeader>
          <CardContent>
            <InternalsPanel symbol={symbol} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
