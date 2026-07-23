/** Parameter optimization (track T3): grid-search a strategy's parameters,
 * then read the honest verdict. The selected "best" always ships with the
 * overfitting guards — deflated Sharpe (deflated for the number of trials
 * tried) and PBO (probability of backtest overfitting) — so a config that
 * only won because we searched hard is flagged, never silently promoted.
 *
 * The grid builder is deliberately literal: for each declared parameter you
 * type the exact values to try (comma-separated). Only parameters you fill
 * are swept; the rest keep the strategy's defaults. Trial count = the product
 * of the value counts, shown live so a runaway grid is obvious before launch. */
import { Sparkles, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Segment, Segmented } from "@/components/ui/segmented";
import {
  OptimizeCostConfirmation,
  qk,
  runOptimization,
  useBacktestOptimization,
  useBacktestOptimizations,
  useBacktestOptimizeJob,
  useBacktestStrategies,
} from "@/lib/api/queries";
import type { BacktestStrategy } from "@/lib/api/types";
import { fmtDateTime } from "@/lib/format";

const TF_CHOICES = ["5m", "15m", "1h", "4h", "1d"] as const;
const DURATIONS = ["1D", "7D", "30D", "1Y"] as const;
const OBJECTIVES = [
  "sharpe",
  "sortino",
  "total_return",
  "profit_factor",
  "expectancy_r",
] as const;
const OBJECTIVE_LABELS: Record<string, string> = {
  sharpe: "Sharpe",
  sortino: "Sortino",
  total_return: "Total return",
  profit_factor: "Profit factor",
  expectancy_r: "Expectancy (R)",
};
const STRATEGY_LABELS: Record<string, string> = {
  rules_v1: "Rules (deterministic)",
  trend_following_v1: "Trend following (Donchian)",
};

type GridText = Record<string, string>;

/** Parse the per-parameter comma-separated text into a param_grid the backend
 * accepts: numbers for int/float params, strings for categorical. Empty /
 * unparseable entries are dropped; a param with no valid values is omitted. */
export function buildGrid(
  strategy: BacktestStrategy | undefined,
  text: GridText,
): Record<string, Array<string | number>> {
  const grid: Record<string, Array<string | number>> = {};
  if (!strategy) return grid;
  for (const param of strategy.params) {
    const raw = (text[param.name] ?? "").trim();
    if (!raw) continue;
    const parts = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const values: Array<string | number> = [];
    for (const part of parts) {
      if (param.kind === "categorical") {
        values.push(part);
      } else {
        const n = Number(part);
        if (!Number.isNaN(n)) values.push(param.kind === "int" ? Math.round(n) : n);
      }
    }
    // de-dupe while preserving order (repeated values would run twice)
    const seen = new Set<string>();
    const unique = values.filter((v) => {
      const key = String(v);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    if (unique.length) grid[param.name] = unique;
  }
  return grid;
}

export default function OptimizePanel() {
  const strategiesQuery = useBacktestStrategies();
  // only registered native strategies are optimizable — the AI pipeline has
  // no declared search space, so drop pipeline_llm from the picker
  const strategies = useMemo(
    () =>
      (strategiesQuery.data?.strategies ?? []).filter(
        (s) => s.id !== "pipeline_llm" && s.params.length > 0,
      ),
    [strategiesQuery.data],
  );

  const [symbol, setSymbol] = useState("BTC-USD");
  const [timeframe, setTimeframe] = useState("1h");
  const [duration, setDuration] = useState("30D");
  const [strategyId, setStrategyId] = useState("trend_following_v1");
  const [objective, setObjective] = useState<string>("sharpe");
  const [gridText, setGridText] = useState<GridText>({});
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [cost, setCost] = useState<OptimizeCostConfirmation["estimate"] | null>(null);
  const [liveJobId, setLiveJobId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const strategy = strategies.find((s) => s.id === strategyId);
  // seed a helpful starting grid (the default value) whenever the strategy
  // changes, so the fields aren't blank
  useEffect(() => {
    if (!strategy) return;
    const seed: GridText = {};
    for (const p of strategy.params) {
      if (p.default != null) seed[p.name] = String(p.default);
    }
    setGridText(seed);
  }, [strategy]);
  // keep the strategy valid as the list resolves
  useEffect(() => {
    if (strategies.length && !strategies.some((s) => s.id === strategyId)) {
      setStrategyId(strategies[0]!.id);
    }
  }, [strategies, strategyId]);

  const grid = useMemo(() => buildGrid(strategy, gridText), [strategy, gridText]);
  const nTrials = useMemo(
    () => Object.values(grid).reduce((acc, vs) => acc * vs.length, 1),
    [grid],
  );
  const sweptCount = Object.keys(grid).length;

  const optsQuery = useBacktestOptimizations();
  const opts = optsQuery.data?.optimizations ?? [];
  const qc = useQueryClient();

  // poll the optimization job while one we launched is in flight
  const jobPoll = useBacktestOptimizeJob(liveJobId != null);
  const job = jobPoll.data;
  useEffect(() => {
    if (!job || !liveJobId) return;
    if (job.job_id && job.job_id !== liveJobId) return;
    if (job.status === "done" || job.status === "cancelled") {
      setLiveJobId(null);
      setSelectedId(job.job_id ?? null);
      void qc.invalidateQueries({ queryKey: qk.backtestOptimizations });
    } else if (job.status === "error") {
      setLiveJobId(null);
      setError(job.error ?? "optimization failed");
    }
  }, [job, liveJobId, qc]);

  const launch = async (confirmCost: boolean) => {
    setError(null);
    setCost(null);
    if (sweptCount === 0) {
      setError("Fill in values for at least one parameter to sweep.");
      return;
    }
    setStarting(true);
    try {
      const { job_id } = await runOptimization({
        symbol,
        timeframe,
        duration,
        strategy_id: strategyId,
        param_grid: grid,
        objective,
        confirm_cost: confirmCost,
      });
      setLiveJobId(job_id);
      setSelectedId(job_id);
    } catch (err) {
      if (err instanceof OptimizeCostConfirmation) setCost(err.estimate);
      else setError(String(err));
    } finally {
      setStarting(false);
    }
  };

  const running = liveJobId != null;
  const progress = job?.progress as
    | { trials_done?: number; n_trials?: number; pct?: number; best_objective?: number; phase?: string }
    | undefined;
  // show the picked optimization, else the newest saved one
  const effectiveId = selectedId ?? opts[0]?.id ?? null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-center gap-2">
          <Sparkles size={16} className="text-accent" />
          <CardTitle>Optimize parameters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3.5">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
            <Field label="Asset">
              <select
                aria-label="Optimize asset"
                data-testid="optimize-asset"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs"
              >
                {["BTC-USD", "ETH-USD", "SOL-USD", "XAUUSD"].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Timeframe">
              <Segmented data-testid="optimize-timeframe">
                {TF_CHOICES.map((tf) => (
                  <Segment
                    key={tf}
                    active={timeframe === tf}
                    onClick={() => setTimeframe(tf)}
                    className="font-mono"
                  >
                    {tf}
                  </Segment>
                ))}
              </Segmented>
            </Field>
            <Field label="Run length">
              <Segmented data-testid="optimize-duration">
                {DURATIONS.map((d) => (
                  <Segment
                    key={d}
                    active={duration === d}
                    onClick={() => setDuration(d)}
                    className="font-mono"
                  >
                    {d}
                  </Segment>
                ))}
              </Segmented>
            </Field>
            <Field label="Strategy">
              <select
                aria-label="Optimize strategy"
                data-testid="optimize-strategy"
                value={strategyId}
                onChange={(e) => setStrategyId(e.target.value)}
                className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs"
              >
                {(strategies.length ? strategies.map((s) => s.id) : [strategyId]).map(
                  (id) => (
                    <option key={id} value={id}>
                      {STRATEGY_LABELS[id] ?? id}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label="Objective">
              <select
                aria-label="Optimize objective"
                data-testid="optimize-objective"
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs"
              >
                {OBJECTIVES.map((o) => (
                  <option key={o} value={o}>
                    {OBJECTIVE_LABELS[o]}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {strategy && (
            <div className="space-y-2">
              <div className="text-xs uppercase tracking-wide text-fg-subtle">
                Grid — comma-separated values per parameter (blank = keep default)
              </div>
              <div className="flex flex-wrap gap-3">
                {strategy.params.map((param) => (
                  <div key={param.name} className="min-w-[9rem]">
                    <label
                      className="mb-1 block text-xs text-fg-muted"
                      htmlFor={`optimize-grid-${param.name}`}
                    >
                      {param.name.replace(/_/g, " ")}
                      {param.kind !== "categorical" &&
                        param.low != null &&
                        param.high != null && (
                          <span className="text-fg-subtle">
                            {" "}
                            ({param.low}–{param.high})
                          </span>
                        )}
                    </label>
                    <input
                      id={`optimize-grid-${param.name}`}
                      data-testid={`optimize-grid-${param.name}`}
                      value={gridText[param.name] ?? ""}
                      onChange={(e) =>
                        setGridText({ ...gridText, [param.name]: e.target.value })
                      }
                      placeholder={
                        param.kind === "categorical"
                          ? param.choices.map(String).join(",")
                          : "e.g. 15,20,25"
                      }
                      className="h-[30px] w-40 rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs tabular"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-3">
            <Button
              onClick={() => void launch(false)}
              disabled={running || starting || cost != null || nTrials < 1}
              data-testid="optimize-run"
            >
              <Play size={13} />
              {running ? "Optimizing…" : "Run optimization"}
            </Button>
            <span className="text-xs text-fg-subtle" data-testid="optimize-trials">
              {sweptCount === 0
                ? "no parameters swept yet"
                : `${nTrials.toLocaleString()} trial${nTrials === 1 ? "" : "s"} · ${sweptCount} parameter${sweptCount === 1 ? "" : "s"}`}
            </span>
          </div>

          {cost && (
            <div
              className="rounded-md border border-accent/40 bg-accent-muted px-3 py-2 text-xs"
              data-testid="optimize-cost-confirm"
            >
              <div className="mb-1.5">
                This grid is{" "}
                <span className="font-bold">{cost.trials.toLocaleString()} backtests</span>{" "}
                (~{cost.est_minutes} min, free, runs serially). Proceed?
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => void launch(true)} data-testid="optimize-cost-ok">
                  Run anyway
                </Button>
                <Button size="sm" variant="outline" onClick={() => setCost(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
          {error && <p className="text-xs text-bear" data-testid="optimize-error">{error}</p>}

          {running && (
            <div data-testid="optimize-progress-panel">
              <div className="mb-1 flex justify-between text-xs text-fg-muted">
                <span>
                  {progress?.phase === "fetching"
                    ? "fetching bars"
                    : `trial ${progress?.trials_done ?? 0} / ${progress?.n_trials ?? nTrials}`}
                  {progress?.best_objective != null &&
                    ` · best ${OBJECTIVE_LABELS[objective]} ${progress.best_objective.toFixed(2)}`}
                </span>
                <span className="font-mono">{(progress?.pct ?? 0).toFixed(0)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full bg-accent transition-[width]"
                  style={{ width: `${Math.min(100, progress?.pct ?? 0)}%` }}
                  data-testid="optimize-progress"
                />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {!running && effectiveId && <ResultCard optId={effectiveId} />}

      {opts.length > 0 && (
        <SavedOptimizations
          opts={opts}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      )}
    </div>
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

/** A red verdict is the point of this whole feature — it means the best
 * config didn't survive the overfitting guards, so don't trust it. */
export function verdictTone(pbo: number | null | undefined, dsr: number | null | undefined) {
  if (pbo == null || dsr == null) return "neutral" as const;
  return pbo > 0.5 || dsr < 0.6 ? ("bear" as const) : ("default" as const);
}

function ResultCard({ optId }: { optId: string }) {
  const query = useBacktestOptimization(optId);
  const view = query.data?.view;
  if (!view) return null;
  const tone = verdictTone(view.pbo, view.deflated_sharpe);
  const trials = [...view.trials].sort((a, b) => b.objective - a.objective);
  const bestKey = JSON.stringify(view.best_params);
  const paramNames = Object.keys(view.param_grid);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>
          Best of {view.n_trials} — {view.symbol} · {view.timeframe} · {view.duration}
        </CardTitle>
        <div className="flex items-center gap-2">
          {view.window && (
            <span className="text-xs text-fg-subtle">
              {view.window[0]} → {view.window[1]}
              {view.window_truncated && " (truncated)"}
            </span>
          )}
          <Badge variant="accent">{view.strategy_id}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className={`rounded-[14px] border px-4 py-2.5 text-sm ${
            tone === "bear"
              ? "border-bear/40 bg-bear-muted text-bear"
              : tone === "default"
                ? "border-bull/40 bg-bull-muted text-bull"
                : "border-border bg-surface-2 text-fg-muted"
          }`}
          data-testid="optimize-verdict"
        >
          {view.verdict}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label={`Best ${OBJECTIVE_LABELS[view.objective] ?? view.objective}`}>
            {view.best_objective.toFixed(3)}
          </Stat>
          <Stat label="Deflated Sharpe" tone={tone}>
            {view.deflated_sharpe != null ? view.deflated_sharpe.toFixed(3) : "—"}
          </Stat>
          <Stat label="PBO" tone={tone}>
            {view.pbo != null ? `${(view.pbo * 100).toFixed(0)}%` : "—"}
          </Stat>
          <Stat label="Trials">{view.n_trials}</Stat>
        </div>

        {view.guard_note && (
          <p className="text-xs text-fg-subtle">Guards: {view.guard_note}</p>
        )}

        <div>
          <div className="mb-1 text-xs font-semibold text-fg-muted">
            Trials (ranked by {OBJECTIVE_LABELS[view.objective] ?? view.objective})
          </div>
          <div className="max-h-72 overflow-y-auto rounded-lg border border-border">
            <table className="w-full text-xs tabular" data-testid="optimize-trials-table">
              <thead className="sticky top-0 bg-surface-2 text-fg-subtle">
                <tr>
                  <th className="px-2 py-1 text-left">#</th>
                  {paramNames.map((name) => (
                    <th key={name} className="px-2 py-1 text-right">
                      {name.replace(/_/g, " ")}
                    </th>
                  ))}
                  <th className="px-2 py-1 text-right">
                    {OBJECTIVE_LABELS[view.objective] ?? view.objective}
                  </th>
                </tr>
              </thead>
              <tbody>
                {trials.map((t, i) => {
                  const isBest = JSON.stringify(t.params) === bestKey;
                  return (
                    <tr
                      key={i}
                      className={`border-t border-border ${isBest ? "bg-accent-muted font-semibold" : ""}`}
                    >
                      <td className="px-2 py-1">{i + 1}</td>
                      {paramNames.map((name) => (
                        <td key={name} className="px-2 py-1 text-right font-mono">
                          {String(t.params[name] ?? "—")}
                        </td>
                      ))}
                      <td className="px-2 py-1 text-right font-mono">
                        {t.objective.toFixed(3)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <p className="text-xs text-fg-subtle">
          The guards deflate the winner for the {view.n_trials}-way search: a high
          PBO or a deflated Sharpe below ~0.6 means the ranking is likely noise —
          re-test out-of-sample before trusting it.
        </p>
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  children,
  tone,
}: {
  label: string;
  children: React.ReactNode;
  tone?: "bear" | "default" | "neutral";
}) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-2">
      <div className="text-xs text-fg-subtle">{label}</div>
      <div
        className={`text-sm font-semibold tabular ${
          tone === "bear" ? "text-bear" : tone === "default" ? "text-bull" : ""
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function SavedOptimizations({
  opts,
  selectedId,
  onSelect,
}: {
  opts: Array<{
    id: string;
    created_at?: string | null;
    symbol?: string | null;
    timeframe?: string | null;
    strategy_id?: string | null;
    objective?: string | null;
    n_trials?: number | null;
    pbo?: number | null;
    deflated_sharpe?: number | null;
  }>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved optimizations</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto" data-testid="optimize-saved">
          <table className="w-full text-xs tabular">
            <thead className="text-fg-subtle">
              <tr>
                <th className="px-2 py-1 text-left">When</th>
                <th className="px-2 py-1 text-left">Asset</th>
                <th className="px-2 py-1 text-left">Strategy</th>
                <th className="px-2 py-1 text-left">Objective</th>
                <th className="px-2 py-1 text-right">Trials</th>
                <th className="px-2 py-1 text-right">Deflated SR</th>
                <th className="px-2 py-1 text-right">PBO</th>
                <th className="px-2 py-1" />
              </tr>
            </thead>
            <tbody>
              {opts.map((o) => (
                <tr
                  key={o.id}
                  className={`border-t border-border ${selectedId === o.id ? "bg-accent-muted" : ""}`}
                >
                  <td className="px-2 py-1">{fmtDateTime(o.created_at ?? undefined)}</td>
                  <td className="px-2 py-1">{o.symbol}</td>
                  <td className="px-2 py-1">{o.strategy_id}</td>
                  <td className="px-2 py-1">
                    {OBJECTIVE_LABELS[o.objective ?? ""] ?? o.objective}
                  </td>
                  <td className="px-2 py-1 text-right">{o.n_trials ?? 0}</td>
                  <td className="px-2 py-1 text-right font-mono">
                    {o.deflated_sharpe != null ? o.deflated_sharpe.toFixed(2) : "—"}
                  </td>
                  <td
                    className={`px-2 py-1 text-right font-mono ${
                      o.pbo != null && o.pbo > 0.5 ? "text-bear" : ""
                    }`}
                  >
                    {o.pbo != null ? `${(o.pbo * 100).toFixed(0)}%` : "—"}
                  </td>
                  <td className="px-2 py-1 text-right">
                    <Button size="sm" variant="ghost" onClick={() => onSelect(o.id)}>
                      View
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
