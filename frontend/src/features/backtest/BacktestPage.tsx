/** Interactive backtesting: pick asset / timeframe / run length, watch the
 * replay pipeline run live (progress, open + closed trades, PnL), and reload
 * any of the auto-archived past runs. Deterministic by default (free, fast,
 * mechanics-only); the AI toggle runs the real pipeline (costs money, capped,
 * confirmed). */
import { FlaskConical, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { EquityCurve } from "@/components/charts/EquityCurve";
import { DirectionBadge } from "@/components/DirectionBadge";
import { EmptyState } from "@/components/EmptyState";
import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Segment, Segmented } from "@/components/ui/segmented";
import { useQueryClient } from "@tanstack/react-query";

import {
  BacktestCostConfirmation,
  qk,
  runBacktest,
  useBacktestJob,
  useBacktestRun,
  useBacktestRuns,
  useSymbols,
} from "@/lib/api/queries";
import type { BacktestRunView, BacktestTrade } from "@/lib/api/types";
import { fmtDateTime, fmtPct, fmtPnl, fmtPrice } from "@/lib/format";
import { useBacktestLiveStore, type BacktestProgress } from "@/stores/backtestLive";

const SYMBOL_LABELS: Record<string, string> = {
  XAUUSD: "Gold (XAUUSD)",
  "BTC-USD": "Bitcoin (BTC-USD)",
  "ETH-USD": "Ethereum (ETH-USD)",
  "SOL-USD": "Solana (SOL-USD)",
};
const TF_CHOICES = ["5m", "15m", "1h", "4h", "1d"] as const;
const DURATIONS = ["1D", "7D", "30D", "1Y"] as const;

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
  // run holds the event loop, freezing the bar mid-run. /api/backtest/job
  // reports accurate live state, so poll it while running and reconcile —
  // the bar keeps advancing and completion/errors are always caught even if
  // the terminal SSE frame was missed.
  const qc = useQueryClient();
  const jobPoll = useBacktestJob(running);
  useEffect(() => {
    const j = jobPoll.data;
    if (!j) return;
    const store = useBacktestLiveStore.getState();
    if (store.status !== "running") return;
    // ignore a stale cached snapshot from a previous run
    if (j.job_id && store.jobId && j.job_id !== store.jobId) return;
    if (j.status === "done" && j.result) {
      store.setDone(j.result);
      void qc.invalidateQueries({ queryKey: qk.backtestRuns });
      void qc.invalidateQueries({ queryKey: qk.backtest });
    } else if (j.status === "error") {
      store.setError(j.error ?? "backtest failed");
    } else if (j.progress) {
      store.setProgress(
        j.progress as unknown as BacktestProgress,
        (j.open_trades ?? []) as BacktestTrade[],
      );
      if (j.closed_trades) store.syncClosed(j.closed_trades as BacktestTrade[]);
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

  // which completed run to show: an explicitly picked one, else the just-
  // finished live run, else the newest saved run
  const newestId = runsQuery.data?.runs[0]?.id ?? null;
  const effectiveRunId =
    selectedRunId ?? (live.result ? null : running ? null : newestId);
  const runDetail = useBacktestRun(effectiveRunId);
  const view: BacktestRunView | null = running
    ? null
    : selectedRunId
      ? (runDetail.data?.view ?? null)
      : (live.result ?? runDetail.data?.view ?? null);

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
        running={running}
        starting={starting}
        error={error}
        cost={cost}
        onRun={() => void start(false)}
        onConfirmCost={() => void start(true)}
        onCancelCost={() => setCost(null)}
      />

      {running && live.progress && <LivePanel />}

      {view && <ResultPanel view={view} live={!selectedRunId && !!live.result} />}
      {!view && !running && (
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
  running: boolean;
  starting: boolean;
  error: string | null;
  cost: BacktestCostConfirmation["estimate"] | null;
  onRun: () => void;
  onConfirmCost: () => void;
  onCancelCost: () => void;
}) {
  const symbols = props.tradeable.length ? props.tradeable : ["BTC-USD", "XAUUSD"];
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
          <Button
            onClick={props.onRun}
            disabled={props.running || props.starting || props.cost != null}
            data-testid="backtest-run"
          >
            <Play size={13} />
            {props.running ? "Running…" : "Run backtest"}
          </Button>
        </div>

        <p className="text-xs text-fg-subtle">
          {props.useLlm ? (
            <>
              <span className="font-semibold text-fg-muted">Real pipeline:</span>{" "}
              makes live model calls — costs money and is capped to the most
              recent ~300 decisions. Measures model skill.
            </>
          ) : (
            <>
              <span className="font-semibold text-fg-muted">Deterministic:</span>{" "}
              scripted no-cost pipeline over real bars — exercises gates, sizing,
              fills and exits, <em>not</em> model skill.
            </>
          )}
        </p>

        {props.cost && (
          <div
            className="rounded-md border border-accent/40 bg-accent-muted px-3 py-2 text-xs"
            data-testid="backtest-cost-confirm"
          >
            <div className="mb-1.5">
              A real-LLM run is about{" "}
              <span className="font-bold">${props.cost.est_cost_usd.toFixed(2)}</span>{" "}
              in model calls over ~{props.cost.est_minutes} min (
              {props.cost.decisions} decisions). Proceed?
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
  const progress = useBacktestLiveStore((s) => s.progress)!;
  const openTrades = useBacktestLiveStore((s) => s.openTrades);
  const closed = useBacktestLiveStore((s) => s.closedTrades);
  const equityCurve = useBacktestLiveStore((s) => s.equityCurve);
  const pnlTone = progress.pnl >= 0 ? "bull" : "bear";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Live run</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="mb-1 flex justify-between text-xs text-fg-muted">
            <span>
              decision {progress.decisions} / {progress.total}
            </span>
            <span className="font-mono">{progress.pct.toFixed(0)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-2" data-testid="backtest-progress">
            <div
              className="h-full rounded-full bg-accent transition-[width]"
              style={{ width: `${Math.min(100, progress.pct)}%` }}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="backtest-pnl">
          <StatCard label="Equity" value={fmtPrice(progress.equity, 0)} />
          <StatCard label="P&L" value={fmtPnl(progress.pnl)} tone={pnlTone} />
          <StatCard label="Open" value={progress.open_count} />
          <StatCard label="Closed" value={progress.closed_trades} />
        </div>
        {equityCurve.length >= 2 && <EquityCurve curve={equityCurve} height={160} />}
        <TradesTable
          title="Open positions"
          testid="backtest-open-trades"
          trades={openTrades}
          open
        />
        <TradesTable
          title="Closed trades"
          testid="backtest-closed-trades"
          trades={[...closed].reverse()}
        />
      </CardContent>
    </Card>
  );
}

function ResultPanel({ view, live }: { view: BacktestRunView; live: boolean }) {
  const report = view.report ?? {};
  const ret = report.total_return;
  const trades = view.trades ?? [];
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
            </span>
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
        {view.provider !== "deterministic" && view.est_cost_usd != null && (
          <p className="text-xs text-fg-subtle">
            {view.llm_calls} model calls · est ${view.est_cost_usd.toFixed(2)}
          </p>
        )}
        {view.equity_curve && view.equity_curve.length >= 2 && (
          <EquityCurve
            curve={view.equity_curve}
            monteCarlo={view.monte_carlo}
            showDrawdown
            height={220}
          />
        )}
        <TradesTable
          title="Trades"
          testid="backtest-result-trades"
          trades={trades}
        />
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
  onSelect: (id: string) => void;
  onLive: () => void;
}) {
  const runsQuery = useBacktestRuns();
  const runs = runsQuery.data?.runs ?? [];
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
            Completed runs are auto-saved here (last {10}). None yet.
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
                      <Button size="sm" variant="ghost" onClick={() => onSelect(r.id)}>
                        View
                      </Button>
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
