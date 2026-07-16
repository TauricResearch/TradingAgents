/** Trading Workspace: chart-first with decision-level overlays, indicator
 * panes, volume, compare mode (crosshair-synced, separate scales),
 * client-side market replay (REPLAY badge, ticks suspended), full-screen.
 * Honestly cut: no fake DOM ladder, no manual order ticket. */
import { Columns2, Maximize2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { DecisionCard } from "@/components/DecisionCard";
import { EmptyState } from "@/components/EmptyState";
import { IndicatorPicker } from "@/components/IndicatorPicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Segment, Segmented } from "@/components/ui/segmented";
import { SkeletonCard } from "@/components/ui/skeleton";
import { ChartSyncProvider } from "@/components/charts/ChartSync";
import {
  PriceChart,
  type TradeMarker,
} from "@/components/charts/PriceChart";
import {
  ReplayControls,
  useReplay,
} from "@/components/charts/ReplayController";
import { DrawingToolbar } from "@/components/charts/drawings/DrawingToolbar";
import { GridChartCell } from "./GridChartCell";
import type { ToolMode } from "@/components/charts/drawings/types";
import { useDrawingsStore } from "@/stores/drawings";
import {
  createPriceAlert,
  deletePriceAlert,
  useBars,
  useCalendar,
  useIndicators,
  useVolumeProfile,
  useIntel,
  useJournal,
  usePriceAlerts,
  useRecommendation,
  useStatus,
  useSymbols,
} from "@/lib/api/queries";
import { useQueryClient } from "@tanstack/react-query";
import type { Recommendation } from "@/lib/api/types";
import { fmtCountdown, fmtPnl, fmtPrice } from "@/lib/format";
import { computePositionPlan } from "@/lib/positionPlan";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

// the two tradable pairs (same set as the run dialog); the registry's other
// symbols (DXY, US10Y, …) are correlation inputs, not chartable workspaces
const TRADE_SYMBOLS = [
  { value: "BTC-USD", label: "BTC-USD · Bitcoin" },
  { value: "XAUUSD", label: "XAUUSD · Gold" },
] as const;

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
        const value =
          Math.abs(metric.value) < 0.01 && metric.value !== 0
            ? metric.value.toExponential(2)
            : fmtPrice(metric.value, 2);
        return (
          <div
            key={name}
            className="flex items-center justify-between rounded-[14px] bg-surface-2 px-3.5 py-2.5"
            title={`${metric.source ?? ""} ${metric.unit ?? ""}`.trim()}
          >
            <span className="text-[11px] font-semibold text-fg-subtle">
              {name.replaceAll("_", " ")}
            </span>
            <span className="font-mono text-sm font-bold tabular">
              {value}
            </span>
          </div>
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
  const navigate = useNavigate();
  const {
    timeframe,
    setTimeframe,
    setSymbol,
    indicators: selectedIndicators,
    toggleIndicator,
    showVolume,
    toggleVolume,
    showProfile,
    toggleProfile,
    compare,
    setCompare,
    gridCells,
    setGridCells,
    updateGridCell,
  } = useUiStore();
  const [toolMode, setToolMode] = useState<ToolMode>("select");
  const chartCardRef = useRef<HTMLDivElement | null>(null);
  const symbolDrawings = useDrawingsStore(
    (state) => state.bySymbol[symbol] ?? [],
  );
  const clearDrawings = useDrawingsStore((state) => state.clear);
  const toggleDrawingHidden = useDrawingsStore((state) => state.toggleHidden);
  const removeDrawing = useDrawingsStore((state) => state.remove);

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
  const volumeProfile = useVolumeProfile(symbol, activeTf, showProfile);
  const recommendation = useRecommendation(symbol);
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

  // per-symbol endpoint (G1): a later run for another symbol can no
  // longer displace this symbol's current ticket
  const recForSymbol =
    recommendation.data && recommendation.data.symbol === symbol
      ? recommendation.data
      : null;
  const recRunId =
    (recommendation.data as { run_id?: string } | undefined)?.run_id ?? null;

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
  // the server-computed next MAJOR event (countdown-capable) beats the
  // first row of the raw release list (review P1.1)
  const nextMajor = calendar.data?.next_major;
  const nextRelease = nextMajor ?? calendar.data?.releases[0];
  const isLive = (spec?.live || symbol === "BTC-USD") && !replay.active;

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      <div className="min-w-0 space-y-4">
        <Card ref={chartCardRef} className="bg-surface">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 whitespace-nowrap !text-lg !font-extrabold !normal-case !tracking-normal !text-fg">
              <label htmlFor="trade-symbol" className="sr-only">
                Trading pair
              </label>
              <select
                id="trade-symbol"
                data-testid="symbol-select"
                value={symbol}
                onChange={(event) => navigate(`/trade/${event.target.value}`)}
                className="cursor-pointer rounded-[10px] border border-border bg-transparent px-1.5 py-0.5 text-lg font-extrabold tracking-[-0.01em] text-fg hover:border-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {TRADE_SYMBOLS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              {replay.active ? null : spec && !spec.live ? (
                <Badge variant="stale">EOD data</Badge>
              ) : (
                spec?.live && <Badge variant="bull">live</Badge>
              )}
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Segmented>
                {available.map((tf) => (
                  <Segment
                    key={tf}
                    onClick={() => setTimeframe(tf)}
                    active={tf === activeTf}
                    className="font-mono"
                  >
                    {tf}
                  </Segment>
                ))}
              </Segmented>
              <IndicatorPicker
                selected={selectedIndicators}
                onToggle={toggleIndicator}
                volume={showVolume}
                onToggleVolume={toggleVolume}
                profile={showProfile}
                onToggleProfile={toggleProfile}
                timeframe={activeTf}
              />
              <Button
                size="sm"
                variant="outline"
                aria-pressed={compare}
                onClick={() => setCompare(!compare)}
                className={compare ? "border-accent bg-brand-muted text-accent" : ""}
              >
                <Columns2 size={13} /> Compare
              </Button>
              {/* multi-chart grid (P2.6): extra crosshair-synced cells */}
              <Segmented aria-label="Chart grid" data-testid="grid-switch">
                {[0, 1, 3].map((n) => (
                  <Segment
                    key={n}
                    active={gridCells.length === n}
                    onClick={() =>
                      setGridCells(
                        Array.from({ length: n }, (_, i) =>
                          gridCells[i] ?? {
                            symbol: i % 2 === 0 ? compareSymbol : symbol,
                            timeframe: i < 1 ? activeTf : "1d",
                          },
                        ),
                      )
                    }
                  >
                    {n === 0 ? "1" : n === 1 ? "2×1" : "2×2"}
                  </Segment>
                ))}
              </Segmented>
              <Button
                size="icon"
                variant="outline"
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
                    drawings={symbolDrawings}
                    onClearAll={() => clearDrawings(symbol)}
                    onToggleHidden={(id) => toggleDrawingHidden(symbol, id)}
                    onRemove={(id) => removeDrawing(symbol, id)}
                  />
                  <div className="min-w-0 grow">
                    <PriceChart
                      bars={visibleBars}
                      style="candles"
                      recommendation={recForSymbol}
                      markers={markers}
                      liveSymbol={isLive ? symbol : undefined}
                      indicators={visibleIndicators}
                      showVolume={showVolume}
                      syncId={compare || gridCells.length > 0 ? "workspace" : undefined}
                      drawingsSymbol={symbol}
                      toolMode={toolMode}
                      onToolModeChange={setToolMode}
                      height={compare ? 300 : 400}
                      volumeProfile={showProfile ? (volumeProfile.data ?? null) : null}
                    />
                  </div>
                </div>
                {compare && (
                  <div className="mt-3 border-t border-border pt-[10px]">
                    <div className="mb-1 flex items-center gap-2 text-xs text-fg-subtle">
                      <span className="font-mono font-bold">{compareSymbol}</span>
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
                {gridCells.length > 0 && (
                  <div
                    className="mt-3 grid gap-2 border-t border-border pt-[10px] md:grid-cols-2"
                    data-testid="chart-grid"
                  >
                    {gridCells.map((cell, i) => (
                      <GridChartCell
                        key={i}
                        cell={cell}
                        syncId="workspace"
                        onChange={(next) => updateGridCell(i, next)}
                      />
                    ))}
                  </div>
                )}
              </ChartSyncProvider>
            )}
            {nextRelease && !replay.active && (
              <p className="mt-[10px] text-xs text-fg-subtle" data-testid="event-strip">
                next macro event: <span className="text-fg-muted">{nextRelease.release}</span>
                {nextMajor ? (
                  <>
                    {" in "}
                    <span className="font-mono tabular text-fg-muted">
                      {fmtCountdown(nextMajor.seconds_until)}
                    </span>
                    {nextMajor.time_et && ` (${nextMajor.date} ${nextMajor.time_et} ET)`}
                  </>
                ) : (
                  <> on {nextRelease.date}</>
                )}
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
              <table className="w-full text-[13px] tabular">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-fg-subtle">
                    <th className="py-1.5 font-semibold">symbol</th>
                    <th className="py-1.5 text-right font-semibold">quantity</th>
                    <th className="py-1.5 text-right font-semibold">entry</th>
                    <th className="py-1.5 text-right font-semibold">mark</th>
                    <th className="py-1.5 text-right font-semibold">unrealized</th>
                    <th className="py-1.5 text-right font-semibold">book state</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.symbol}>
                      <td className="py-2 font-mono">{p.symbol}</td>
                      <td className="py-2 text-right">
                        {p.quantity > 0 ? "+" : ""}
                        {p.quantity}
                      </td>
                      <td className="py-2 text-right font-mono">
                        {fmtPrice(p.entry_price)}
                      </td>
                      <td className="py-2 text-right font-mono">
                        {fmtPrice(p.mark_price)}
                        {p.mark_source && p.mark_source !== "live" && (
                          <span className="ml-1 text-[10px] uppercase text-stale">
                            {p.mark_source}
                          </span>
                        )}
                      </td>
                      <td
                        className={cn(
                          "py-2 text-right font-mono",
                          p.unrealized_pnl != null &&
                            (p.unrealized_pnl >= 0 ? "text-bull" : "text-bear"),
                        )}
                        data-testid="position-unrealized"
                      >
                        {fmtPnl(p.unrealized_pnl)}
                      </td>
                      <td className="py-2 text-right">
                        <span className="inline-flex rounded-full bg-bull-muted px-2.5 py-0.5 text-[11px] font-bold text-bull">
                          reconciled
                        </span>
                      </td>
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
              <DecisionCard rec={recForSymbol} compact runId={recRunId} />
            ) : (
              <EmptyState
                kind="empty"
                title={`No decision yet for ${symbol}`}
                detail="No pipeline run has targeted this symbol."
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
        <Card>
          <CardHeader>
            <CardTitle>Position plan</CardTitle>
          </CardHeader>
          <CardContent>
            <PositionPlanPanel
              symbol={symbol}
              rec={recForSymbol}
              anchorTime={allBars.length > 0 ? allBars[allBars.length - 1]!.time : null}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Price alerts</CardTitle>
          </CardHeader>
          <CardContent>
            <PriceAlertsPanel symbol={symbol} rec={recForSymbol} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}


/** What-if planner over the long/short chart tool (review P2.1): reads the
 * newest position drawing for this symbol, sizes it with the same fixed-risk
 * rule the backend uses, and can prefill a drawing from the AI's own levels.
 * A plan over user-chosen levels — not platform advice. */
function PositionPlanPanel({
  symbol,
  rec,
  anchorTime,
}: {
  symbol: string;
  rec: Recommendation | null;
  /** last bar time — drawing anchors must be EXACT bar times or the
   * chart's timeToCoordinate returns null and nothing renders */
  anchorTime: number | null;
}) {
  const status = useStatus();
  const drawings = useDrawingsStore((s) => s.bySymbol[symbol] ?? []);
  const [riskPct, setRiskPct] = useState("1");
  const position = [...drawings]
    .reverse()
    .find((d) => (d.kind === "long" || d.kind === "short") && d.points.length === 3);

  const adoptAiLevels = () => {
    if (!rec?.entry_price || !rec.stop_loss || !rec.take_profits?.length) return;
    if (anchorTime == null) return;
    const side = rec.action === "BUY" ? "long" : "short";
    useDrawingsStore.getState().add(symbol, {
      id: crypto.randomUUID(),
      kind: side,
      points: [
        { time: anchorTime, price: rec.entry_price },
        { time: anchorTime, price: rec.stop_loss },
        { time: anchorTime, price: rec.take_profits[0]!.price },
      ],
    });
  };

  if (!position) {
    return (
      <div className="space-y-2 text-xs text-fg-subtle" data-testid="position-plan">
        <p>
          Draw a position on the chart (long/short tool: entry → stop →
          target) to size it here.
        </p>
        {rec?.entry_price != null && rec.action !== "HOLD" && (
          <Button size="sm" variant="outline" onClick={adoptAiLevels}
                  data-testid="adopt-ai-levels">
            Adopt the AI's levels
          </Button>
        )}
      </div>
    );
  }

  const equity = status.data?.equity ?? null;
  const parsedRisk = Number.parseFloat(riskPct);
  const plan = equity != null
    ? computePositionPlan({
        side: position.kind as "long" | "short",
        entry: position.points[0]!.price,
        stop: position.points[1]!.price,
        target: position.points[2]!.price,
        equity,
        riskPct: Number.isFinite(parsedRisk) ? parsedRisk : 1,
      })
    : null;

  return (
    <div className="space-y-2 text-sm" data-testid="position-plan">
      <p className="font-mono text-xs tabular text-fg-muted">
        {position.kind.toUpperCase()} · entry {fmtPrice(position.points[0]!.price)} ·
        stop {fmtPrice(position.points[1]!.price)} · target {fmtPrice(position.points[2]!.price)}
      </p>
      <label className="flex items-center gap-2 text-xs text-fg-subtle">
        risk % of equity
        <input
          value={riskPct}
          onChange={(e) => setRiskPct(e.target.value)}
          inputMode="decimal"
          className="w-16 rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs tabular"
          data-testid="plan-risk-pct"
        />
      </label>
      {plan == null ? (
        <p className="text-xs text-fg-subtle">equity unavailable (monitor mode)</p>
      ) : !plan.valid ? (
        <p className="text-xs text-bear">{plan.reason}</p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-xs tabular">
          <dt className="text-fg-subtle">size</dt>
          <dd>{plan.quantity.toFixed(4)}{plan.capped && " (capped)"}</dd>
          <dt className="text-fg-subtle">notional</dt>
          <dd>{fmtPrice(plan.notional, 0)} ({plan.pctOfEquity.toFixed(1)}%)</dd>
          <dt className="text-fg-subtle">risk → reward</dt>
          <dd>
            <span className="text-bear">{fmtPrice(plan.riskAmount, 0)}</span>
            {" → "}
            <span className="text-bull">{fmtPrice(plan.rewardAmount, 0)}</span>
          </dd>
          <dt className="text-fg-subtle">R:R</dt>
          <dd>{plan.rr.toFixed(2)} · breakeven {Math.round(plan.breakevenWinRate * 100)}%</dd>
        </dl>
      )}
      <p className="text-[10px] text-fg-subtle">
        your plan over your levels — not a platform recommendation
      </p>
    </div>
  );
}


/** Notify-only user price alerts (G4) with one-click presets from the
 * current ticket's own levels — set an alert on the AI's invalidation
 * price in one tap. */
function PriceAlertsPanel({
  symbol,
  rec,
}: {
  symbol: string;
  rec: Recommendation | null;
}) {
  const client = useQueryClient();
  const alerts = usePriceAlerts();
  const [level, setLevel] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [error, setError] = useState<string | null>(null);

  const mine = (alerts.data ?? []).filter(
    (a) => a.symbol === symbol && a.active,
  );
  const presets = rec
    ? ([
        ["ENTRY", rec.entry_price],
        ["STOP", rec.stop_loss],
        ["TP1", rec.take_profits?.[0]?.price],
      ] as const).filter(([, price]) => price != null)
    : [];

  const submit = async (lvl: number, dir: "above" | "below", note = "") => {
    setError(null);
    try {
      await createPriceAlert(client, { symbol, level: lvl, direction: dir, note });
      setLevel("");
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="space-y-2 text-sm" data-testid="price-alerts">
      {mine.length === 0 ? (
        <p className="text-xs text-fg-subtle">
          No alerts for {symbol}. Alerts notify (bell, Telegram when
          configured) — they never trade.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {mine.map((alert) => (
            <li
              key={alert.id}
              className="flex items-center justify-between gap-2 rounded-[12px] bg-surface-2 px-3 py-[7px] text-[12.5px]"
            >
              <span className="font-mono font-bold tabular">
                {alert.direction === "above" ? "≥" : "≤"} {fmtPrice(alert.level)}
              </span>
              <span className="grow truncate text-xs text-fg-subtle">
                {alert.note}
              </span>
              <button
                onClick={() => void deletePriceAlert(client, alert.id)}
                aria-label={`Delete alert at ${alert.level}`}
                className="flex size-[22px] shrink-0 items-center justify-center rounded-[7px] text-fg-subtle hover:bg-bear-muted hover:text-bear"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="flex items-center gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          const lvl = Number(level);
          if (Number.isFinite(lvl) && lvl > 0) void submit(lvl, direction);
        }}
      >
        <input
          type="number"
          step="any"
          min="0"
          placeholder="price level"
          value={level}
          onChange={(event) => setLevel(event.target.value)}
          aria-label="Alert price level"
          data-testid="price-alert-level"
          className="w-24 rounded-lg border border-border bg-surface-2 px-2 py-1 text-xs tabular outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={() => setDirection(direction === "above" ? "below" : "above")}
          aria-label="Toggle direction"
          className="rounded-lg border border-border px-2 py-1 text-xs font-semibold"
        >
          {direction === "above" ? "↑ above" : "↓ below"}
        </button>
        <Button size="sm" type="submit" data-testid="price-alert-create">
          Alert
        </Button>
      </form>
      {presets.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {presets.map(([label, price]) => (
            <button
              key={label}
              onClick={() =>
                void submit(
                  price!,
                  rec && rec.entry_price != null && price! >= rec.entry_price
                    ? "above"
                    : "below",
                  `${label} from run ${rec?.id ?? ""}`.trim(),
                )
              }
              className="rounded-full border border-accent/40 bg-accent-muted px-2 py-0.5 text-[11px] font-semibold text-accent"
            >
              alert @ {label} {fmtPrice(price)}
            </button>
          ))}
        </div>
      )}
      {error && <p className="text-xs text-bear">{error}</p>}
    </div>
  );
}
