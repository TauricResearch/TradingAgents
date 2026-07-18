/** Trading Workspace: chart-first with decision-level overlays, indicator
 * panes, volume, a multi-chart grid (crosshair-synced), client-side market
 * replay (REPLAY badge, ticks suspended), full-screen.
 * Honestly cut: no fake DOM ladder, no manual order ticket. */
import { Maximize2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

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
  type SeriesStyle,
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
  useJournal,
  useRecommendation,
  useChartAnnotations,
  useStatus,
  useSymbols,
} from "@/lib/api/queries";
import { useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";
import type { Bar } from "@/lib/api/types";
import { fmtCountdown, fmtPnl, fmtPrice } from "@/lib/format";
import { snapToBar } from "@/components/charts/annotationSnap";
import {
  ExplainRunPopover,
  type ExplainTarget,
} from "./ExplainRunPopover";
import {
  ChartContextMenu,
  type ContextTarget,
} from "./ChartContextMenu";
import { ReplayDecisionStrip } from "./ReplayDecisionStrip";
import { countdownExpired, useCountdown } from "@/lib/useCountdown";
import { useUiStore } from "@/stores/ui";

// tradeable pairs come from /api/symbols (server-driven, same set as the
// run dialog); the registry's other symbols (DXY, US10Y, …) are
// correlation inputs, not chartable workspaces
const TRADE_SYMBOL_LABELS: Record<string, string> = {
  "BTC-USD": "BTC-USD · Bitcoin",
  XAUUSD: "XAUUSD · Gold",
  "ETH-USD": "ETH-USD · Ethereum",
  "SOL-USD": "SOL-USD · Solana",
};
const FALLBACK_TRADE_SYMBOLS = ["BTC-USD", "XAUUSD"];

// shared stable fallback for drawings selectors — `?? []` in a zustand
// selector mints a fresh array per snapshot read, which React's
// useSyncExternalStore treats as an endlessly-changing store → infinite
// re-render (#185). This crashed /trade in production for any symbol
// without saved drawings. Same pattern as PriceChart's private constant.
const NO_DRAWINGS: never[] = [];

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
    logScale,
    toggleLogScale,
    chartStyle,
    setChartStyle,
    gridCells,
    setGridCells,
    updateGridCell,
  } = useUiStore();
  const [toolMode, setToolMode] = useState<ToolMode>("select");
  const [magnet, setMagnet] = useState(false);
  const [showAnnotations, setShowAnnotations] = useState(true);
  const [showPlan, setShowPlan] = useState(true);
  const chartCardRef = useRef<HTMLDivElement | null>(null);
  const symbolDrawings = useDrawingsStore(
    // stable empty constant: `?? []` mints a fresh array per call, which
    // useSyncExternalStore reads as an endlessly-changing snapshot →
    // React #185 infinite render (crashed the Trade page in production)
    (state) => state.bySymbol[symbol] ?? NO_DRAWINGS,
  );
  const clearDrawings = useDrawingsStore((state) => state.clear);
  const toggleDrawingHidden = useDrawingsStore((state) => state.toggleHidden);
  const removeDrawing = useDrawingsStore((state) => state.remove);
  const undoDrawing = useDrawingsStore((state) => state.undo);
  const redoDrawing = useDrawingsStore((state) => state.redo);
  // subscribe to history depth so the toolbar buttons enable/disable live
  const canUndo = useDrawingsStore((s) => (s.past[symbol]?.length ?? 0) > 0);
  const canRedo = useDrawingsStore((s) => (s.future[symbol]?.length ?? 0) > 0);

  const symbols = useSymbols();
  const spec = symbols.data?.find((s) => s.symbol === symbol);
  const available = spec?.timeframes ?? ["1d"];
  const activeTf = available.includes(timeframe)
    ? timeframe
    : available[available.length - 1]!;

  // still the default seed symbol for the multi-chart grid cells
  const compareSymbol = symbol === "BTC-USD" ? "XAUUSD" : "BTC-USD";

  const bars = useBars(symbol, activeTf, 300);
  const indicatorData = useIndicators(symbol, activeTf, selectedIndicators);
  const volumeProfile = useVolumeProfile(symbol, activeTf, showProfile);
  const recommendation = useRecommendation(symbol);
  const journal = useJournal();
  const status = useStatus();
  const calendar = useCalendar();
  const alertClient = useQueryClient();
  const [alertToast, setAlertToast] = useState<
    { text: string; alertId: string | null } | null
  >(null);

  // keep global symbol in sync with the route
  if (useUiStore.getState().symbol !== symbol) setSymbol(symbol);

  // history paging (PB.1): older bars fetched on demand, prepended to the
  // live 300-bar window. Keyed by symbol+tf so a switch resets it.
  const [olderBars, setOlderBars] = useState<Bar[]>([]);
  const [historyExhausted, setHistoryExhausted] = useState(false);
  const loadingOlderRef = useRef(false);
  useEffect(() => {
    setOlderBars([]);
    setHistoryExhausted(false);
    loadingOlderRef.current = false;
  }, [symbol, activeTf]);

  const liveBars = bars.data;
  const allBars = useMemo(() => {
    const live = liveBars ?? [];
    if (olderBars.length === 0) return live;
    // dedup at the seam (older window may overlap the live window's head)
    const liveStart = live.length ? live[0]!.time : Infinity;
    return [...olderBars.filter((b) => b.time < liveStart), ...live];
  }, [olderBars, liveBars]);

  const loadOlder = useCallback(() => {
    if (loadingOlderRef.current || historyExhausted) return;
    const earliest = (olderBars[0] ?? liveBars?.[0])?.time;
    if (earliest == null) return;
    loadingOlderRef.current = true;
    apiFetch<Bar[]>(
      `/api/bars?symbol=${encodeURIComponent(symbol)}` +
        `&timeframe=${activeTf}&limit=300&end=${earliest}`,
    )
      .then((older) => {
        const fresh = (older ?? []).filter((b) => b.time < earliest);
        if (fresh.length === 0) setHistoryExhausted(true);
        else setOlderBars((prev) => [...fresh, ...prev]);
      })
      .catch(() => setHistoryExhausted(true))
      .finally(() => {
        loadingOlderRef.current = false;
      });
  }, [symbol, activeTf, olderBars, liveBars, historyExhausted]);

  // A2: click-to-alert. Direction is inferred from the last close — an
  // alert above spot fires on a rally, below on a break. Toast holds 6s
  // with an Undo (V4 finding: 3.5s blinked out before the eye landed).
  const createChartAlert = (price: number) => {
    const lastClose = allBars.length
      ? allBars[allBars.length - 1]!.close
      : price;
    const direction = price >= lastClose ? "above" : "below";
    void createPriceAlert(alertClient, {
      symbol,
      level: price,
      direction,
      note: "from chart",
    })
      .then((created) =>
        setAlertToast({
          text: `Alert set: ${symbol} ${direction} ${fmtPrice(price)}`,
          alertId: created.id ?? null,
        }),
      )
      .catch(() =>
        setAlertToast({ text: "Could not set alert — try again", alertId: null }),
      );
    window.setTimeout(() => setAlertToast(null), 6000);
  };

  // AI decision layer (chart Phase 1): fetched before replay so replay
  // can pause on the bars where decisions happened
  const chartAnnotations = useChartAnnotations(symbol);
  const decisionBars = useMemo(() => {
    const times = allBars.map((b) => b.time);
    const byIndex = new Map<number, string>();
    for (const run of chartAnnotations.data?.runs ?? []) {
      if (run.time == null) continue;
      const t = snapToBar(times, run.time);
      if (t == null) continue;
      const idx = times.indexOf(t);
      if (idx >= 0 && !byIndex.has(idx)) byIndex.set(idx, run.run_id);
    }
    return { set: new Set(byIndex.keys()), byIndex };
  }, [chartAnnotations.data, allBars]);

  const replay = useReplay(allBars.length, decisionBars.set);
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

  const markers: TradeMarker[] = useMemo(
    () =>
      (journal.data?.entries ?? [])
        .filter((entry) => entry.symbol === symbol)
        .map((entry) => ({
          time: Math.floor(new Date(entry.closed_at).getTime() / 1000),
          direction: entry.pnl >= 0 ? "bull" : "bear",
          label: `${entry.action ?? ""} ${fmtPnl(entry.pnl)}`,
        }))
        .filter((m) => {
          if (!replay.active || cursorTime == null) return true;
          // snapped comparison, same basis as the pause logic (R4.2)
          const snapped = snapToBar(allBars.map((b) => b.time), m.time);
          return snapped != null && snapped <= cursorTime;
        }),
    [journal.data, symbol, replay.active, cursorTime, allBars],
  );

  // During replay only runs decided as-of the cursor are visible — the
  // future stays hidden (P0.2 rule).
  const visibleAnnotations = useMemo(() => {
    const data = chartAnnotations.data;
    if (!data) return null;
    if (!replay.active || cursorTime == null) return data;
    // R4.2: compare SNAPPED times — the same basis the pause-on-decision
    // logic uses. Raw run times sit mid-bar (e.g. 14:23 in the 14:00 bar),
    // so a raw comparison hid the paused decision's own zone until the
    // NEXT bar was revealed.
    const times = allBars.map((b) => b.time);
    const asOf = (t: number | null) => {
      if (t == null) return false;
      const snapped = snapToBar(times, t);
      return snapped != null && snapped <= cursorTime;
    };
    return {
      ...data,
      runs: data.runs.filter((r) => asOf(r.time)),
      fills: data.fills.filter((f) => asOf(f.closed_time)),
    };
  }, [chartAnnotations.data, replay.active, cursorTime, allBars]);

  const [explain, setExplain] = useState<ExplainTarget | null>(null);
  const [ctxMenu, setCtxMenu] = useState<ContextTarget | null>(null);
  // a symbol/timeframe switch invalidates the anchor position
  useEffect(() => {
    setExplain(null);
    setCtxMenu(null);
  }, [symbol, activeTf]);

  // ⌘Z / ⇧⌘Z drawing undo/redo (PC.2), ignored while typing in a field
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
      e.preventDefault();
      if (e.shiftKey) redoDrawing(symbol);
      else undoDrawing(symbol);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [symbol, undoDrawing, redoDrawing]);

  // open position for this symbol: entry line on the chart + the server's
  // unrealized P&L in a badge (no client math — Constraint 2)
  const openPosition = useMemo(
    () =>
      status.data?.open_positions?.find(
        (p) => p.symbol === symbol && p.quantity !== 0,
      ) ?? null,
    [status.data, symbol],
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

  // the server-computed next MAJOR event (countdown-capable) beats the
  // first row of the raw release list (review P1.1); the countdown ticks
  // locally between refetches (R2.3)
  const nextMajor = calendar.data?.next_major;
  const nextMajorRemaining = useCountdown(nextMajor?.at ?? null);
  const nextRelease = nextMajor ?? calendar.data?.releases[0];
  const isLive = (spec?.live || symbol === "BTC-USD") && !replay.active;

  return (
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
                {(symbols.data?.filter((s) => s.tradeable).map((s) => s.symbol) ??
                  FALLBACK_TRADE_SYMBOLS).map((s) => (
                  <option key={s} value={s}>
                    {TRADE_SYMBOL_LABELS[s] ?? s}
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
              <select
                aria-label="Chart style"
                value={chartStyle}
                onChange={(e) => setChartStyle(e.target.value)}
                className="h-7 rounded-md border border-border bg-surface px-1.5 text-xs text-fg"
              >
                <option value="candles">Candles</option>
                <option value="hollow">Hollow</option>
                <option value="heikin-ashi">Heikin Ashi</option>
                <option value="bars">OHLC</option>
                <option value="line">Line</option>
                <option value="area">Area</option>
                <option value="baseline">Baseline</option>
              </select>
              <Button
                size="sm"
                variant="outline"
                aria-label="Toggle the AI's active plan (entry / stop / targets)"
                aria-pressed={showPlan}
                className={showPlan ? "text-accent" : "text-fg-subtle"}
                onClick={() => setShowPlan((v) => !v)}
              >
                AI Plan
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="Toggle AI decision history"
                aria-pressed={showAnnotations}
                className={showAnnotations ? "text-accent" : "text-fg-subtle"}
                onClick={() => setShowAnnotations((v) => !v)}
              >
                AI History
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="Toggle volume profile"
                aria-pressed={showProfile}
                className={showProfile ? "text-accent" : "text-fg-subtle"}
                onClick={toggleProfile}
              >
                Profile
              </Button>
              <Button
                size="sm"
                variant="outline"
                aria-label="Toggle logarithmic price scale"
                aria-pressed={logScale}
                className={logScale ? "text-accent" : "text-fg-subtle"}
                onClick={toggleLogScale}
              >
                log
              </Button>
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
            {alertToast && (
              <div
                className="mb-2 flex items-center justify-between rounded-lg bg-accent-muted px-2.5 py-1.5 text-xs text-accent"
                data-testid="alert-toast"
                role="status"
              >
                <span>{alertToast.text}</span>
                {alertToast.alertId && (
                  <button
                    className="ml-2 font-semibold underline"
                    onClick={() => {
                      void deletePriceAlert(alertClient, alertToast.alertId!);
                      setAlertToast(null);
                    }}
                  >
                    Undo
                  </button>
                )}
              </div>
            )}
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
            {replay.active && replay.pausedOnBar != null &&
              decisionBars.byIndex.get(replay.pausedOnBar) && (
                <ReplayDecisionStrip
                  runId={decisionBars.byIndex.get(replay.pausedOnBar)!}
                  onResume={() => replay.setPlaying(true)}
                />
              )}
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
                    magnet={magnet}
                    onMagnetChange={setMagnet}
                    onUndo={() => undoDrawing(symbol)}
                    onRedo={() => redoDrawing(symbol)}
                    canUndo={canUndo}
                    canRedo={canRedo}
                  />
                  <div className="relative min-w-0 grow">
                    <PriceChart
                      bars={visibleBars}
                      style={chartStyle as SeriesStyle}
                      recommendation={recForSymbol}
                      markers={markers}
                      liveSymbol={isLive ? symbol : undefined}
                      indicators={visibleIndicators}
                      showVolume={showVolume}
                      syncId={gridCells.length > 0 ? "workspace" : undefined}
                      drawingsSymbol={symbol}
                      toolMode={toolMode}
                      onToolModeChange={setToolMode}
                      onCreateAlert={createChartAlert}
                      height={400}
                      volumeProfile={showProfile ? (volumeProfile.data ?? null) : null}
                      annotations={visibleAnnotations}
                      onExplainRun={(runId, point) =>
                        setExplain({ runId, x: point.x, y: point.y })
                      }
                      openPosition={openPosition}
                      logScale={logScale}
                      magnet={magnet}
                      legend
                      onLoadOlder={replay.active ? undefined : loadOlder}
                      showAnnotations={showAnnotations}
                      showPlan={showPlan}
                      onContextMenu={(p) => setCtxMenu(p)}
                    />
                    {openPosition?.unrealized_pnl != null && (
                      <div
                        data-testid="position-badge"
                        className={
                          "absolute right-2 top-2 z-10 rounded-lg border border-border bg-surface/90 px-2 py-1 font-mono text-xs tabular " +
                          (openPosition.unrealized_pnl >= 0
                            ? "text-bull"
                            : "text-bear")
                        }
                      >
                        {openPosition.quantity > 0 ? "long" : "short"}{" "}
                        {Math.abs(openPosition.quantity)} ·{" "}
                        {fmtPnl(openPosition.unrealized_pnl)}
                        <span className="ml-1 text-fg-subtle">paper</span>
                      </div>
                    )}
                    {explain && (
                      <ExplainRunPopover
                        target={explain}
                        fill={(() => {
                          const f = (chartAnnotations.data?.fills ?? []).find(
                            (x) => x.run_id === explain.runId,
                          );
                          return f
                            ? {
                                pnl: f.pnl,
                                won: f.won,
                                mode: f.mode,
                                inferred: f.link === "inferred",
                              }
                            : null;
                        })()}
                        onClose={() => setExplain(null)}
                      />
                    )}
                    {ctxMenu && (
                      <ChartContextMenu
                        target={ctxMenu}
                        onClose={() => setCtxMenu(null)}
                        onAlertHere={createChartAlert}
                        onExplain={(runId, x, y) =>
                          setExplain({ runId, x, y })
                        }
                      />
                    )}
                  </div>
                </div>
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
                {nextMajor && !countdownExpired(nextMajorRemaining) ? (
                  <>
                    {" in "}
                    <span className="font-mono tabular text-fg-muted">
                      {fmtCountdown(nextMajorRemaining ?? nextMajor.seconds_until)}
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
  );
}
