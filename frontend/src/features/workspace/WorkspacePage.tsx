/** Trading Workspace: chart-first with decision-level overlays, indicator
 * panes, volume, compare mode (crosshair-synced, separate scales),
 * client-side market replay (REPLAY badge, ticks suspended), full-screen.
 * Honestly cut: no fake DOM ladder, no manual order ticket. */
import { Columns2, Maximize2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { DecisionCard } from "@/components/DecisionCard";
import { EmptyState } from "@/components/EmptyState";
import { IndicatorPicker } from "@/components/IndicatorPicker";
import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import { ChartSyncProvider } from "@/components/charts/ChartSync";
import {
  PriceChart,
  type SeriesStyle,
  type TradeMarker,
} from "@/components/charts/PriceChart";
import {
  ReplayControls,
  useReplay,
} from "@/components/charts/ReplayController";
import { DrawingToolbar } from "@/components/charts/drawings/DrawingToolbar";
import type { ToolMode } from "@/components/charts/drawings/types";
import { useDrawingsStore } from "@/stores/drawings";
import {
  useBars,
  useCalendar,
  useIndicators,
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
  { id: "bars", label: "OHLC" },
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
              Math.abs(metric.value) < 0.01 && metric.value !== 0
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
  const {
    timeframe,
    setTimeframe,
    setSymbol,
    indicators: selectedIndicators,
    toggleIndicator,
    showVolume,
    toggleVolume,
    compare,
    setCompare,
  } = useUiStore();
  const [style, setStyle] = useState<SeriesStyle>("candles");
  const [toolMode, setToolMode] = useState<ToolMode>("select");
  const chartCardRef = useRef<HTMLDivElement | null>(null);
  const drawingCount = useDrawingsStore(
    (state) => (state.bySymbol[symbol] ?? []).length,
  );
  const clearDrawings = useDrawingsStore((state) => state.clear);

  const symbols = useSymbols();
  const spec = symbols.data?.find((s) => s.symbol === symbol);
  const available = spec?.timeframes ?? ["1d"];
  const activeTf = available.includes(timeframe)
    ? timeframe
    : available[available.length - 1]!;

  const compareSymbol = symbol === "BTC-USD" ? "XAUUSD" : "BTC-USD";
  const compareSpec = symbols.data?.find((s) => s.symbol === compareSymbol);
  const compareTf = (compareSpec?.timeframes ?? ["1d"]).includes(activeTf)
    ? activeTf
    : "1d";

  const bars = useBars(symbol, activeTf, 300);
  const compareBars = useBars(compareSymbol, compareTf, 300);
  const indicatorData = useIndicators(symbol, activeTf, selectedIndicators);
  const recommendation = useRecommendation();
  const overview = useOverview();
  const journal = useJournal();
  const status = useStatus();
  const calendar = useCalendar();

  // keep global symbol in sync with the route
  if (useUiStore.getState().symbol !== symbol) setSymbol(symbol);

  const allBars = useMemo(() => bars.data ?? [], [bars.data]);
  const replay = useReplay(allBars.length);
  const visibleBars = replay.active
    ? allBars.slice(0, replay.cursor)
    : allBars;
  const cursorTime = visibleBars[visibleBars.length - 1]?.time ?? null;
  const cursorLabel =
    replay.active && cursorTime
      ? new Date(cursorTime * 1000).toLocaleDateString()
      : null;

  // indicators sliced to the replay cursor (presentation filter)
  const visibleIndicators = useMemo(() => {
    if (!indicatorData.data) return undefined;
    if (!replay.active || cursorTime == null) return indicatorData.data;
    return Object.fromEntries(
      Object.entries(indicatorData.data).map(([name, block]) => [
        name,
        {
          ...block,
          series: Object.fromEntries(
            Object.entries(block.series).map(([line, points]) => [
              line,
              points.filter((p) => p.time <= cursorTime),
            ]),
          ),
        },
      ]),
    );
  }, [indicatorData.data, replay.active, cursorTime]);

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
        }))
        .filter((m) => !replay.active || cursorTime == null || m.time <= cursorTime),
    [journal.data, symbol, replay.active, cursorTime],
  );

  // full-screen: button + `f` shortcut (dispatched as a window event)
  const toggleFullscreen = () => {
    const el = chartCardRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen();
  };
  useEffect(() => {
    const handler = () => toggleFullscreen();
    window.addEventListener("pro:fullscreen", handler);
    return () => window.removeEventListener("pro:fullscreen", handler);
  }, []);

  const positions = (status.data?.open_positions ?? []).filter(
    (p) => p.symbol === symbol,
  );
  const nextRelease = calendar.data?.releases[0];
  const isLive = (spec?.live || symbol === "BTC-USD") && !replay.active;

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
      <div className="min-w-0 space-y-4">
        <Card ref={chartCardRef} className="bg-surface">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {symbol}
              {replay.active ? null : spec && !spec.live ? (
                <Badge variant="stale">EOD data</Badge>
              ) : (
                spec?.live && <Badge variant="bull">live</Badge>
              )}
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
              <span className="mx-1 text-border-strong">|</span>
              <IndicatorPicker
                selected={selectedIndicators}
                onToggle={toggleIndicator}
                volume={showVolume}
                onToggleVolume={toggleVolume}
              />
              <Button
                size="sm"
                variant="ghost"
                aria-pressed={compare}
                onClick={() => setCompare(!compare)}
              >
                <Columns2 size={13} /> Compare
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Full screen (f)"
                onClick={toggleFullscreen}
              >
                <Maximize2 size={13} />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="mb-2 flex items-center justify-between no-print">
              <ReplayControls
                replay={replay}
                totalBars={allBars.length}
                cursorLabel={cursorLabel}
              />
              {replay.active && (
                <span className="text-xs text-stale">
                  replayed history — live ticks suspended
                </span>
              )}
            </div>
            {bars.isPending ? (
              <SkeletonCard lines={8} />
            ) : bars.isError ? (
              <EmptyState
                kind="error"
                title="Chart data unavailable"
                detail={String(bars.error)}
              />
            ) : (
              <ChartSyncProvider>
                <div className="flex gap-2">
                  <DrawingToolbar
                    mode={toolMode}
                    onModeChange={setToolMode}
                    count={drawingCount}
                    onClearAll={() => clearDrawings(symbol)}
                  />
                  <div className="min-w-0 grow">
                    <PriceChart
                      bars={visibleBars}
                      style={style}
                      recommendation={recForSymbol}
                      markers={markers}
                      liveSymbol={isLive ? symbol : undefined}
                      indicators={visibleIndicators}
                      showVolume={showVolume}
                      syncId={compare ? "workspace" : undefined}
                      drawingsSymbol={symbol}
                      toolMode={toolMode}
                      onToolModeChange={setToolMode}
                      height={compare ? 300 : 420}
                    />
                  </div>
                </div>
                {compare && (
                  <div className="mt-3 border-t border-border pt-2">
                    <div className="mb-1 flex items-center gap-2 text-xs text-fg-subtle">
                      <span className="font-mono">{compareSymbol}</span>
                      <span>({compareTf}) — crosshair synced, own price scale</span>
                    </div>
                    {compareBars.data ? (
                      <PriceChart
                        bars={
                          replay.active && cursorTime != null
                            ? compareBars.data.filter((b) => b.time <= cursorTime)
                            : compareBars.data
                        }
                        style="line"
                        syncId="workspace"
                        height={180}
                      />
                    ) : (
                      <SkeletonCard lines={3} />
                    )}
                  </div>
                )}
              </ChartSyncProvider>
            )}
            {nextRelease && !replay.active && (
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
