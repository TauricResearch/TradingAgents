/** Interactive backtesting: pick asset / timeframe / run length, watch the
 * replay pipeline run live (fetch progress, decision progress, open + closed
 * trades, PnL), cancel mid-run (the partial is saved), and reload any of the
 * auto-archived past runs. Full decision density — every bar gets a decision
 * — and full-fidelity artifacts: the equity chart + trade table come from
 * the per-run artifact files, never a downsampled copy. */
import { FlaskConical, Play, Square, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { EquityCurve } from "@/components/charts/EquityCurve";
import { DirectionBadge } from "@/components/DirectionBadge";
import { EmptyState } from "@/components/EmptyState";
import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Segment, Segmented } from "@/components/ui/segmented";
import {
  BacktestCostConfirmation,
  cancelBacktest,
  deleteBacktestRun,
  qk,
  runBacktest,
  useBacktestEquityArtifact,
  useBacktestJob,
  useBacktestRun,
  useBacktestRuns,
  useBacktestTradesArtifact,
  useSymbols,
} from "@/lib/api/queries";
import type { BacktestRunView, BacktestTrade } from "@/lib/api/types";
import { planRun } from "@/lib/backtestPlan";
import { fmtDateTime, fmtPct, fmtPnl, fmtPrice } from "@/lib/format";
import {
  useBacktestLiveStore,
  type BacktestProgress,
} from "@/stores/backtestLive";

const SYMBOL_LABELS: Record<string, string> = {
  XAUUSD: "Gold (XAUUSD)",
  "BTC-USD": "Bitcoin (BTC-USD)",
  "ETH-USD": "Ethereum (ETH-USD)",
  "SOL-USD": "Solana (SOL-USD)",
};
const TF_CHOICES = ["5m", "15m", "1h", "4h", "1d"] as const;
const DURATIONS = ["1D", "7D", "30D", "1Y"] as const;

const STATUS_BADGE: Record<string, "default" | "bear" | "neutral"> = {
  done: "default",
  cancelled: "neutral",
  interrupted: "bear",
};

export default function BacktestPage() {
  const symbolsQuery = useSymbols();
  const runsQuery = useBacktestRuns();
  const live = useBacktestLiveStore();

  const tradeable = useMemo(
    () => (symbolsQuery.data ?? []).filter((s) => s.tradeable),
    [symbolsQuery.data],
  );
  const [symbol, setSymbol] = useState("BTC-USD");
  const spec = tradeable.find((s) => s.symbol === symbol);
  const timeframes = useMemo<string[]>(() => {
    const allowed: string[] = spec?.timeframes ?? [...TF_CHOICES];
    return TF_CHOICES.filter((tf) => allowed.includes(tf));
  }, [spec]);
  const [timeframe, setTimeframe] = useState<string>("1h");
  const [duration, setDuration] = useState<string>("7D");
  const [useLlm, setUseLlm] = useState(false);
  const [initialEquity, setInitialEquity] = useState(100_000);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [cost, setCost] = useState<BacktestCostConfirmation["estimate"] | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // keep the timeframe valid for the selected asset (Gold-on-yfinance is 1d-only)
  useEffect(() => {
    if (timeframes.length && !timeframes.includes(timeframe)) {
      setTimeframe(timeframes[0]!);
    }
  }, [timeframes, timeframe]);

  const running = live.status === "running";

  // Polling fallback: the SSE progress stream can stall while a CPU-bound
  // run holds the event loop. /api/backtest/job reports accurate live state,
  // so poll it while running and reconcile — and on mount, re-attach to a
  // run already in flight server-side (reload / second tab).
  const qc = useQueryClient();
  const jobPoll = useBacktestJob(running);
  useEffect(() => {
    const j = jobPoll.data;
    if (!j) return;
    if (
      useBacktestLiveStore.getState().status === "idle" &&
      j.status === "running" &&
      j.job_id
    ) {
      useBacktestLiveStore.getState().start(j.job_id);
    }
    const store = useBacktestLiveStore.getState();
    if (store.status !== "running") return;
    if (j.status === "idle") {
      // the in-memory job vanished (instance restarted mid-run). Grace
      // window covers a just-started run racing a stale poll response.
      // The interrupted partial is auto-saved server-side on next boot.
      if (store.startedAt && Date.now() - store.startedAt > 15_000) {
        store.setError(
          "The run was interrupted by a server restart. The partial is " +
            "saved to Saved runs on recovery — or just run it again.",
        );
      }
      return;
    }
    // ignore a stale cached snapshot from a previous run
    if (j.job_id && store.jobId && j.job_id !== store.jobId) return;
    if (j.status === "done" || j.status === "cancelled") {
      store.finish(j.status === "cancelled" ? "cancelled" : "done", j.job_id ?? null);
      void qc.invalidateQueries({ queryKey: qk.backtestRuns });
      void qc.invalidateQueries({ queryKey: qk.backtest });
    } else if (j.status === "error") {
      store.setError(j.error ?? "backtest failed");
    } else if (
      j.progress &&
      (typeof (j.progress as { decisions?: unknown }).decisions === "number" ||
        (j.progress as { phase?: unknown }).phase === "fetching")
    ) {
      store.setProgress(
        j.progress as unknown as BacktestProgress,
        (j.open_trades ?? []) as BacktestTrade[],
      );
      if (j.closed_trades) {
        store.syncClosed(
          j.closed_trades as BacktestTrade[],
          j.closed_total ?? j.closed_trades.length,
        );
      }
    }
  }, [jobPoll.data, qc]);

  const start = async (confirmCost: boolean) => {
    setError(null);
    setCost(null);
    setStarting(true);
    try {
      const { job_id } = await runBacktest({
        symbol,
        timeframe,
        duration,
        use_llm: useLlm,
        confirm_cost: confirmCost,
        initial_equity: initialEquity,
      });
      live.start(job_id);
      setSelectedRunId(null); // switch the results view to the live run
    } catch (err) {
      if (err instanceof BacktestCostConfirmation) setCost(err.estimate);
      else setError(String(err));
    } finally {
      setStarting(false);
    }
  };

  // which completed run to show: an explicitly picked one, else the run
  // that just finished, else the newest saved run
  const newestId = runsQuery.data?.runs[0]?.id ?? null;
  const effectiveRunId = running
    ? null
    : (selectedRunId ?? live.finishedRunId ?? newestId);
  const runDetail = useBacktestRun(effectiveRunId);
  const view: BacktestRunView | null = runDetail.data?.view ?? null;

  return (
    <div className="space-y-4" data-testid="backtest-page">
      <div className="flex items-center gap-2">
        <FlaskConical size={18} className="text-accent" />
        <h1 className="text-lg font-bold">Backtesting</h1>
      </div>

      <RunControls
        tradeable={tradeable.map((s) => s.symbol)}
        symbol={symbol}
        setSymbol={setSymbol}
        timeframes={timeframes}
        timeframe={timeframe}
        setTimeframe={setTimeframe}
        duration={duration}
        setDuration={setDuration}
        useLlm={useLlm}
        setUseLlm={setUseLlm}
        initialEquity={initialEquity}
        setInitialEquity={setInitialEquity}
        running={running}
        starting={starting}
        error={error}
        cost={cost}
        onRun={() => void start(false)}
        onConfirmCost={() => void start(true)}
        onCancelCost={() => setCost(null)}
      />

      {live.status === "error" && live.error && (
        <div
          className="rounded-[14px] border border-bear/40 bg-bear-muted px-4 py-2.5 text-sm text-bear"
          data-testid="backtest-error"
        >
          {live.error}
        </div>
      )}

      {running && <LivePanel />}

      {!running && view && effectiveRunId && (
        <ResultPanel
          runId={effectiveRunId}
          view={view}
          live={!selectedRunId && live.finishedRunId === effectiveRunId}
        />
      )}
      {!running && !view && (
        <EmptyState
          title="No backtest yet"
          detail="Pick an asset, timeframe and run length above, then Run."
        />
      )}

      <SavedRuns
        selectedRunId={selectedRunId}
        onSelect={setSelectedRunId}
        onLive={() => setSelectedRunId(null)}
      />
    </div>
  );
}

function RunControls(props: {
  tradeable: string[];
  symbol: string;
  setSymbol: (s: string) => void;
  timeframes: readonly string[];
  timeframe: string;
  setTimeframe: (s: string) => void;
  duration: string;
  setDuration: (s: string) => void;
  useLlm: boolean;
  setUseLlm: (b: boolean) => void;
  initialEquity: number;
  setInitialEquity: (n: number) => void;
  running: boolean;
  starting: boolean;
  error: string | null;
  cost: BacktestCostConfirmation["estimate"] | null;
  onRun: () => void;
  onConfirmCost: () => void;
  onCancelCost: () => void;
}) {
  const symbols = props.tradeable.length ? props.tradeable : ["BTC-USD", "XAUUSD"];
  const plan = planRun(props.symbol, props.timeframe, props.duration, props.useLlm);
  const freeConfirm = props.cost != null && props.cost.est_cost_usd === 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Configure run</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3.5">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <Field label="Asset">
            <select
              aria-label="Asset"
              data-testid="backtest-asset"
              value={props.symbol}
              onChange={(e) => props.setSymbol(e.target.value)}
              className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {SYMBOL_LABELS[s] ?? s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Timeframe">
            <Segmented data-testid="backtest-timeframe">
              {props.timeframes.map((tf) => (
                <Segment
                  key={tf}
                  active={props.timeframe === tf}
                  onClick={() => props.setTimeframe(tf)}
                  className="font-mono"
                >
                  {tf}
                </Segment>
              ))}
            </Segmented>
          </Field>
          <Field label="Run length">
            <Segmented data-testid="backtest-duration">
              {DURATIONS.map((d) => (
                <Segment
                  key={d}
                  active={props.duration === d}
                  onClick={() => props.setDuration(d)}
                  className="font-mono"
                >
                  {d}
                </Segment>
              ))}
            </Segmented>
          </Field>
          <Field label="Engine">
            <Segmented data-testid="backtest-llm-toggle">
              <Segment active={!props.useLlm} onClick={() => props.setUseLlm(false)}>
                Deterministic
              </Segment>
              <Segment active={props.useLlm} onClick={() => props.setUseLlm(true)}>
                Use AI (LLM)
              </Segment>
            </Segmented>
          </Field>
          <Field label="Starting equity">
            <input
              type="number"
              aria-label="Starting equity"
              data-testid="backtest-equity"
              min={1000}
              step={1000}
              value={props.initialEquity}
              onChange={(e) =>
                props.setInitialEquity(Math.max(1, Number(e.target.value) || 0))
              }
              className="h-[30px] w-28 rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs tabular"
            />
          </Field>
          <Button
            onClick={props.onRun}
            disabled={props.running || props.starting || props.cost != null}
            data-testid="backtest-run"
          >
            <Play size={13} />
            {props.running ? "Running…" : "Run backtest"}
          </Button>
        </div>

        <p className="text-xs text-fg-subtle" data-testid="backtest-plan">
          {plan && (
            <span className="font-mono">
              ≈{plan.decisions.toLocaleString()} decisions
              {plan.llmCapped && " (LLM cost cap: most recent window)"} · est ~
              {plan.estMinutes} min.{" "}
            </span>
          )}
          {props.useLlm ? (
            <>
              <span className="font-semibold text-fg-muted">Real pipeline:</span>{" "}
              makes live model calls — costs money. Measures model skill.
            </>
          ) : (
            <>
              <span className="font-semibold text-fg-muted">Deterministic:</span>{" "}
              scripted no-cost pipeline over real bars, one decision EVERY bar —
              exercises gates, sizing, fills and exits, <em>not</em> model skill.
            </>
          )}
        </p>

        {props.cost && (
          <div
            className="rounded-md border border-accent/40 bg-accent-muted px-3 py-2 text-xs"
            data-testid="backtest-cost-confirm"
          >
            <div className="mb-1.5">
              {freeConfirm ? (
                <>
                  This is a big full-density run:{" "}
                  <span className="font-bold">
                    {props.cost.decisions.toLocaleString()} decisions
                  </span>{" "}
                  over ~{props.cost.est_minutes} min (free, cancellable, saved
                  incrementally). Proceed?
                </>
              ) : (
                <>
                  A real-LLM run is about{" "}
                  <span className="font-bold">
                    ${props.cost.est_cost_usd.toFixed(2)}
                  </span>{" "}
                  in model calls over ~{props.cost.est_minutes} min (
                  {props.cost.decisions} decisions). Proceed?
                </>
              )}
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={props.onConfirmCost} data-testid="backtest-cost-ok">
                Run anyway
              </Button>
              <Button size="sm" variant="outline" onClick={props.onCancelCost}>
                Cancel
              </Button>
            </div>
          </div>
        )}
        {props.error && <p className="text-xs text-bear">{props.error}</p>}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs uppercase tracking-wide text-fg-subtle">{label}</div>
      {children}
    </div>
  );
}

function LivePanel() {
  const progress = useBacktestLiveStore((s) => s.progress);
  const openTrades = useBacktestLiveStore((s) => s.openTrades);
  const closed = useBacktestLiveStore((s) => s.closedTrades);
  const closedTotal = useBacktestLiveStore((s) => s.closedTotal);
  const equityCurve = useBacktestLiveStore((s) => s.equityCurve);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const cancel = async () => {
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelBacktest(); // retries through transient 429s internally
    } catch {
      setCancelling(false);
      setCancelError("Cancel didn't reach the server — try again.");
    }
  };

  const fetching = progress?.phase === "fetching";
  const decisions = progress?.decisions ?? 0;
  const total = progress?.total ?? 0;
  const pct = progress?.pct ?? 0;
  const equity = progress?.equity ?? 0;
  const pnl = progress?.pnl ?? 0;
  const openCount = progress?.open_count ?? openTrades.length;
  const pnlTone = pnl >= 0 ? "bull" : "bear";
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Live run</CardTitle>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void cancel()}
          disabled={cancelling}
          data-testid="backtest-cancel"
        >
          <Square size={12} />
          {cancelling ? "Cancelling…" : "Cancel (keeps partial)"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {cancelError && <p className="text-xs text-bear">{cancelError}</p>}
        {!progress && (
          <p className="text-sm text-fg-muted">Starting run…</p>
        )}
        {fetching && (
          <div data-testid="backtest-fetch">
            <div className="mb-1 flex justify-between text-xs text-fg-muted">
              <span>
                fetching bars {progress?.bars_have?.toLocaleString()} /{" "}
                {progress?.bars_needed?.toLocaleString()}
              </span>
              <span className="font-mono">{pct.toFixed(0)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full bg-neutral transition-[width]"
                style={{ width: `${Math.min(100, pct)}%` }}
              />
            </div>
          </div>
        )}
        {progress && !fetching && (
          <>
            <div>
              <div className="mb-1 flex justify-between text-xs text-fg-muted">
                <span>
                  decision {decisions.toLocaleString()} / {total.toLocaleString()}
                </span>
                <span className="font-mono">{pct.toFixed(0)}%</span>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-surface-2"
                data-testid="backtest-progress"
              >
                <div
                  className="h-full rounded-full bg-accent transition-[width]"
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="backtest-pnl">
              <StatCard label="Equity" value={fmtPrice(equity, 0)} />
              <StatCard label="P&L" value={fmtPnl(pnl)} tone={pnlTone} />
              <StatCard label="Open" value={openCount} />
              <StatCard label="Closed" value={closedTotal} />
            </div>
            {equityCurve.length >= 2 && <EquityCurve curve={equityCurve} height={160} />}
            <TradesTable
              title="Open positions"
              testid="backtest-open-trades"
              trades={openTrades}
              open
            />
            <TradesTable
              title={`Closed trades${closedTotal > closed.length ? ` (latest ${closed.length} of ${closedTotal})` : ""}`}
              testid="backtest-closed-trades"
              trades={[...closed].reverse()}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ResultPanel({
  runId,
  view,
  live,
}: {
  runId: string;
  view: BacktestRunView;
  live: boolean;
}) {
  const report = view.report ?? {};
  const ret = report.total_return;
  const status = view.status ?? "done";
  // full-fidelity artifacts: every equity point + every trade
  const equityArtifact = useBacktestEquityArtifact(runId);
  const tradesArtifact = useBacktestTradesArtifact(runId);
  const curve = useMemo(() => {
    const rows = equityArtifact.data;
    if (rows && rows.length >= 2) {
      const values = rows.map(([, v]) => v);
      return view.initial_equity != null
        ? [view.initial_equity, ...values]
        : values;
    }
    return view.equity_curve ?? []; // legacy records embedded the curve
  }, [equityArtifact.data, view]);
  const trades = tradesArtifact.data ?? view.trades ?? [];
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>
          {live ? "Result" : "Saved run"} — {view.symbol} · {view.timeframe} ·{" "}
          {view.duration}
        </CardTitle>
        <div className="flex items-center gap-2">
          {view.window && (
            <span className="text-xs text-fg-subtle">
              {view.window[0]} → {view.window[1]}
              {view.window_truncated && " (truncated by vendor)"}
            </span>
          )}
          {status !== "done" && (
            <Badge variant={STATUS_BADGE[status] ?? "neutral"} data-testid="backtest-status">
              {status}
            </Badge>
          )}
          <Badge variant={view.provider === "deterministic" ? "default" : "accent"}>
            {view.provider}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <StatCard
            label="Return"
            value={fmtPct(ret)}
            tone={ret != null ? (ret >= 0 ? "bull" : "bear") : undefined}
          />
          <StatCard label="Final equity" value={fmtPrice(view.final_equity, 0)} />
          <StatCard label="Win rate" value={fmtPct(report.win_rate)} n={view.n_trades} />
          <StatCard label="Profit factor" value={fmtNum(report.profit_factor)} />
          <StatCard label="Max DD" value={fmtPct(report.max_drawdown)} tone="bear" />
          <StatCard label="Trades" value={view.n_trades ?? 0} />
        </div>
        <p className="text-xs text-fg-subtle" data-testid="backtest-provenance">
          {view.decisions != null && (
            <>{view.decisions.toLocaleString()} decisions · one per bar (full density)</>
          )}
          {view.indicator_mode && <> · indicators: {view.indicator_mode}</>}
          {view.provider !== "deterministic" && view.est_cost_usd != null && (
            <>
              {" "}· {view.llm_calls} model calls · est ${view.est_cost_usd.toFixed(2)}
            </>
          )}
        </p>
        {curve.length >= 2 && (
          <EquityCurve
            curve={curve}
            monteCarlo={view.monte_carlo}
            showDrawdown
            height={220}
          />
        )}
        <TradesTable title="Trades" testid="backtest-result-trades" trades={trades} />
        {status === "cancelled" && (
          <p className="text-xs text-fg-subtle">
            Cancelled mid-run — metrics cover the completed portion only.
          </p>
        )}
        {status === "interrupted" && (
          <p className="text-xs text-fg-subtle">
            Interrupted by a server restart — recovered up to the last
            checkpoint; metrics are partial.
          </p>
        )}
        {view.provider === "deterministic" && (
          <p className="text-xs text-fg-subtle">
            Deterministic replay — mechanics only, not an edge measurement.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function TradesTable({
  title,
  testid,
  trades,
  open = false,
}: {
  title: string;
  testid: string;
  trades: BacktestTrade[];
  open?: boolean;
}) {
  if (!trades.length) {
    return (
      <div className="text-xs text-fg-subtle" data-testid={testid}>
        {title}: none yet.
      </div>
    );
  }
  return (
    <div>
      <div className="mb-1 text-xs font-semibold text-fg-muted">{title}</div>
      <div className="max-h-72 overflow-y-auto rounded-lg border border-border">
        <table className="w-full text-xs tabular" data-testid={testid}>
          <thead className="sticky top-0 bg-surface-2 text-fg-subtle">
            <tr>
              <th className="px-2 py-1 text-left">Side</th>
              <th className="px-2 py-1 text-right">Qty</th>
              <th className="px-2 py-1 text-right">Entry</th>
              <th className="px-2 py-1 text-right">{open ? "Mark" : "Exit"}</th>
              <th className="px-2 py-1 text-right">P&L</th>
              {!open && <th className="px-2 py-1 text-left">Why</th>}
              <th className="px-2 py-1 text-left">{open ? "Opened" : "Closed"}</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const pnl = open ? t.unrealized_pnl : t.pnl;
              return (
                <tr key={t.id} className="border-t border-border">
                  <td className="px-2 py-1">
                    <DirectionBadge value={t.side} />
                  </td>
                  <td className="px-2 py-1 text-right">{fmtNum(t.quantity, 4)}</td>
                  <td className="px-2 py-1 text-right">{fmtPrice(t.entry_price)}</td>
                  <td className="px-2 py-1 text-right">
                    {fmtPrice(open ? t.mark_price : t.exit_price)}
                  </td>
                  <td
                    className={`px-2 py-1 text-right ${
                      pnl != null ? (pnl >= 0 ? "text-bull" : "text-bear") : ""
                    }`}
                  >
                    {fmtPnl(pnl)}
                  </td>
                  {!open && <td className="px-2 py-1">{t.reason ?? "—"}</td>}
                  <td className="px-2 py-1">
                    {fmtDateTime(open ? t.opened_at : t.closed_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SavedRuns({
  selectedRunId,
  onSelect,
  onLive,
}: {
  selectedRunId: string | null;
  onSelect: (id: string | null) => void;
  onLive: () => void;
}) {
  const runsQuery = useBacktestRuns();
  const qc = useQueryClient();
  const runs = runsQuery.data?.runs ?? [];
  const remove = async (id: string) => {
    await deleteBacktestRun(qc, id);
    if (selectedRunId === id) onSelect(null);
  };
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Saved runs</CardTitle>
        {selectedRunId && (
          <Button size="sm" variant="ghost" onClick={onLive}>
            Show latest
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? (
          <p className="text-xs text-fg-subtle">
            Completed runs are auto-saved here (last 25). None yet.
          </p>
        ) : (
          <div className="overflow-x-auto" data-testid="backtest-saved-runs">
            <table className="w-full text-xs tabular">
              <thead className="text-fg-subtle">
                <tr>
                  <th className="px-2 py-1 text-left">When</th>
                  <th className="px-2 py-1 text-left">Asset</th>
                  <th className="px-2 py-1 text-left">TF</th>
                  <th className="px-2 py-1 text-left">Len</th>
                  <th className="px-2 py-1 text-left">Engine</th>
                  <th className="px-2 py-1 text-left">Status</th>
                  <th className="px-2 py-1 text-right">Return</th>
                  <th className="px-2 py-1 text-right">Trades</th>
                  <th className="px-2 py-1" />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    className={`border-t border-border ${
                      selectedRunId === r.id ? "bg-accent-muted" : ""
                    }`}
                  >
                    <td className="px-2 py-1">{fmtDateTime(r.created_at)}</td>
                    <td className="px-2 py-1">{r.symbol}</td>
                    <td className="px-2 py-1 font-mono">{r.timeframe}</td>
                    <td className="px-2 py-1 font-mono">{r.duration}</td>
                    <td className="px-2 py-1">
                      {r.provider === "deterministic" ? "det" : "AI"}
                    </td>
                    <td className="px-2 py-1">
                      {(r.status ?? "done") === "done" ? (
                        <span className="text-fg-subtle">done</span>
                      ) : (
                        <Badge variant={STATUS_BADGE[r.status ?? ""] ?? "neutral"}>
                          {r.status}
                        </Badge>
                      )}
                    </td>
                    <td
                      className={`px-2 py-1 text-right ${
                        r.total_return != null
                          ? r.total_return >= 0
                            ? "text-bull"
                            : "text-bear"
                          : ""
                      }`}
                    >
                      {fmtPct(r.total_return)}
                    </td>
                    <td className="px-2 py-1 text-right">{r.n_trades ?? 0}</td>
                    <td className="px-2 py-1 text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => onSelect(r.id)}>
                          View
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-6 w-6 text-fg-subtle hover:text-bear"
                          aria-label={`Delete run ${r.id}`}
                          data-testid={`backtest-delete-${r.id}`}
                          onClick={() => void remove(r.id)}
                        >
                          <Trash2 size={12} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function fmtNum(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : value.toFixed(digits);
}
