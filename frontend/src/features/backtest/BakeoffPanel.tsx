/** Strategy bake-off — run several strategies over the SAME window and rank
 * them by an honest objective, so "which strategy fits this asset?" has a
 * direct answer. Pick a basket of strategies (default: all), launch, watch
 * progress, then read the ranked table with the winner highlighted. */
import { Swords, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Segment, Segmented } from "@/components/ui/segmented";
import {
  BacktestCostConfirmation,
  qk,
  runBakeoff,
  useBacktestBakeoff,
  useBacktestBakeoffJob,
  useBacktestBakeoffs,
  useBacktestStrategies,
} from "@/lib/api/queries";
import { fmtDateTime, fmtPct } from "@/lib/format";

const TF_CHOICES = ["5m", "15m", "1h", "4h", "1d"] as const;
const DURATIONS = ["1D", "7D", "30D", "1Y"] as const;
const OBJECTIVES = ["sharpe", "sortino", "total_return", "profit_factor",
  "expectancy_r"] as const;
const OBJECTIVE_LABELS: Record<string, string> = {
  sharpe: "Sharpe", sortino: "Sortino", total_return: "Total return",
  profit_factor: "Profit factor", expectancy_r: "Expectancy (R)",
};
const STRATEGY_LABELS: Record<string, string> = {
  trend_following_v1: "Trend following", mean_reversion_v1: "Mean reversion",
  momentum_v1: "Momentum", ma_crossover_v1: "MA crossover",
  htf_momentum_v1: "HTF momentum", volatility_breakout_v1: "Volatility breakout",
  rules_v1: "Rules (deterministic)",
};

export default function BakeoffPanel() {
  const strategiesQuery = useBacktestStrategies();
  // pipeline_llm needs the model bundle → not eligible for a headless bake-off
  const eligible = useMemo(
    () => (strategiesQuery.data?.strategies ?? [])
      .map((s) => s.id).filter((id) => id !== "pipeline_llm"),
    [strategiesQuery.data],
  );

  const [symbol, setSymbol] = useState("BTC-USD");
  const [timeframe, setTimeframe] = useState("1d");
  const [duration, setDuration] = useState("1Y");
  const [objective, setObjective] = useState<string>("sharpe");
  const [selected, setSelected] = useState<string[] | null>(null); // null = all
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [cost, setCost] = useState<BacktestCostConfirmation["estimate"] | null>(null);
  const [liveJobId, setLiveJobId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const chosen = selected ?? eligible;  // default: the whole library
  const toggle = (id: string) => {
    const cur = selected ?? eligible;
    setSelected(cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id]);
  };

  const qc = useQueryClient();
  const jobPoll = useBacktestBakeoffJob(liveJobId != null);
  const job = jobPoll.data;
  const running = liveJobId != null;
  const progress = job?.progress as
    | { done?: number; total?: number; pct?: number; strategy_id?: string; phase?: string }
    | undefined;
  useEffect(() => {
    if (!job || !liveJobId) return;
    if (job.job_id && job.job_id !== liveJobId) return;
    if (job.status === "done" || job.status === "cancelled") {
      setLiveJobId(null);
      setSelectedId(job.job_id ?? null);
      void qc.invalidateQueries({ queryKey: qk.backtestBakeoffs });
    } else if (job.status === "error") {
      setLiveJobId(null);
      setError(job.error ?? "bake-off failed");
    }
  }, [job, liveJobId, qc]);

  const bakeoffsQuery = useBacktestBakeoffs();
  const bakeoffs = bakeoffsQuery.data?.bakeoffs ?? [];
  const effectiveId = selectedId ?? bakeoffs[0]?.id ?? null;

  const launch = async (confirmCost: boolean) => {
    setError(null);
    setCost(null);
    if (chosen.length < 2) {
      setError("Pick at least two strategies to compare.");
      return;
    }
    setStarting(true);
    try {
      const { job_id } = await runBakeoff({
        symbol, timeframe, duration, objective,
        // send explicit ids only when the user narrowed from "all"
        strategy_ids: selected == null ? undefined : selected,
        confirm_cost: confirmCost,
      });
      setLiveJobId(job_id);
      setSelectedId(job_id);
    } catch (err) {
      if (err instanceof BacktestCostConfirmation) setCost(err.estimate);
      else setError(String(err));
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-center gap-2">
          <Swords size={16} className="text-accent" />
          <CardTitle>Strategy bake-off</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3.5">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
            <Field label="Asset">
              <select aria-label="Bakeoff asset" data-testid="bakeoff-asset"
                value={symbol} onChange={(e) => setSymbol(e.target.value)}
                className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs">
                {["BTC-USD", "ETH-USD", "SOL-USD", "XAUUSD"].map((s) => (
                  <option key={s} value={s}>{s}</option>))}
              </select>
            </Field>
            <Field label="Timeframe">
              <Segmented data-testid="bakeoff-timeframe">
                {TF_CHOICES.map((tf) => (
                  <Segment key={tf} active={timeframe === tf}
                    onClick={() => setTimeframe(tf)} className="font-mono">{tf}</Segment>))}
              </Segmented>
            </Field>
            <Field label="Run length">
              <Segmented data-testid="bakeoff-duration">
                {DURATIONS.map((d) => (
                  <Segment key={d} active={duration === d}
                    onClick={() => setDuration(d)} className="font-mono">{d}</Segment>))}
              </Segmented>
            </Field>
            <Field label="Rank by">
              <select aria-label="Bakeoff objective" data-testid="bakeoff-objective"
                value={objective} onChange={(e) => setObjective(e.target.value)}
                className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs">
                {OBJECTIVES.map((o) => (
                  <option key={o} value={o}>{OBJECTIVE_LABELS[o]}</option>))}
              </select>
            </Field>
          </div>

          <div>
            <div className="mb-1 text-xs uppercase tracking-wide text-fg-subtle">
              Strategies ({chosen.length})
            </div>
            <div className="flex flex-wrap gap-1.5" data-testid="bakeoff-strategies">
              {(eligible.length ? eligible : chosen).map((id) => (
                <button key={id} type="button" data-testid={`bakeoff-strat-${id}`}
                  aria-pressed={chosen.includes(id)} onClick={() => toggle(id)}
                  className={`rounded-[10px] border px-2.5 py-1 text-xs font-semibold transition-colors ${
                    chosen.includes(id)
                      ? "border-accent bg-accent-muted text-accent"
                      : "border-border-strong bg-surface-2 text-fg-muted hover:text-fg"}`}>
                  {STRATEGY_LABELS[id] ?? id}
                </button>))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={() => void launch(false)}
              disabled={running || starting || cost != null || chosen.length < 2}
              data-testid="bakeoff-run">
              <Play size={13} />
              {running ? "Running…" : "Run bake-off"}
            </Button>
            <span className="text-xs text-fg-subtle">
              {chosen.length} strategies · same window · ranked by {OBJECTIVE_LABELS[objective]}
            </span>
          </div>

          {cost && (
            <div className="rounded-md border border-accent/40 bg-accent-muted px-3 py-2 text-xs"
              data-testid="bakeoff-cost-confirm">
              <div className="mb-1.5">
                This bake-off is{" "}
                <span className="font-bold">{cost.decisions.toLocaleString()} decisions</span>{" "}
                across the basket (~{cost.est_minutes} min, free). Proceed?
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => void launch(true)} data-testid="bakeoff-cost-ok">
                  Run anyway
                </Button>
                <Button size="sm" variant="outline" onClick={() => setCost(null)}>Cancel</Button>
              </div>
            </div>
          )}
          {error && <p className="text-xs text-bear" data-testid="bakeoff-error">{error}</p>}

          {running && (
            <div data-testid="bakeoff-progress-panel">
              <div className="mb-1 flex justify-between text-xs text-fg-muted">
                <span>
                  {progress?.phase === "fetching" ? "fetching bars"
                    : `strategy ${progress?.done ?? 0} / ${progress?.total ?? chosen.length}`}
                  {progress?.strategy_id && ` · ${STRATEGY_LABELS[progress.strategy_id] ?? progress.strategy_id}`}
                </span>
                <span className="font-mono">{(progress?.pct ?? 0).toFixed(0)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full rounded-full bg-accent transition-[width]"
                  style={{ width: `${Math.min(100, progress?.pct ?? 0)}%` }}
                  data-testid="bakeoff-progress" />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {!running && effectiveId && <ResultCard bakeoffId={effectiveId} objective={objective} />}
      {bakeoffs.length > 0 && (
        <SavedBakeoffs bakeoffs={bakeoffs} selectedId={selectedId} onSelect={setSelectedId} />
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

function ResultCard({ bakeoffId }: { bakeoffId: string; objective: string }) {
  const query = useBacktestBakeoff(bakeoffId);
  const view = query.data?.view;
  if (!view) return null;
  const rows = view.results;
  const objLabel = OBJECTIVE_LABELS[view.objective] ?? view.objective;
  const num = (v: number | null | undefined, d = 2) =>
    v != null && Number.isFinite(v) ? v.toFixed(d) : "—";
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>
          Bake-off — {view.symbol} · {view.timeframe} · {view.duration}
        </CardTitle>
        <div className="flex items-center gap-2">
          {view.window && (
            <span className="text-xs text-fg-subtle">{view.window[0]} → {view.window[1]}</span>
          )}
          <Badge variant="accent">rank by {objLabel}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-xs tabular" data-testid="bakeoff-results">
            <thead className="bg-surface-2 text-fg-subtle">
              <tr>
                <th className="px-2 py-1 text-left">#</th>
                <th className="px-2 py-1 text-left">Strategy</th>
                <th className="px-2 py-1 text-right">Return</th>
                <th className="px-2 py-1 text-right">Sharpe</th>
                <th className="px-2 py-1 text-right">MAR</th>
                <th className="px-2 py-1 text-right">Max DD</th>
                <th className="px-2 py-1 text-right">Edge stab.</th>
                <th className="px-2 py-1 text-right">Trades</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.strategy_id}
                  className={`border-t border-border ${i === 0 ? "bg-accent-muted font-semibold" : ""}`}>
                  <td className="px-2 py-1">{i + 1}{i === 0 ? " 🏆" : ""}</td>
                  <td className="px-2 py-1">{STRATEGY_LABELS[r.strategy_id] ?? r.strategy_id}</td>
                  <td className={`px-2 py-1 text-right ${
                    r.total_return != null ? (r.total_return >= 0 ? "text-bull" : "text-bear") : ""}`}>
                    {fmtPct(r.total_return ?? undefined)}
                  </td>
                  <td className="px-2 py-1 text-right font-mono">{num(r.sharpe)}</td>
                  <td className="px-2 py-1 text-right font-mono">{num(r.mar)}</td>
                  <td className="px-2 py-1 text-right text-bear">{fmtPct(r.max_drawdown ?? undefined)}</td>
                  <td className="px-2 py-1 text-right font-mono">{fmtPct(r.sharpe_stability ?? undefined)}</td>
                  <td className="px-2 py-1 text-right">{r.n_trades ?? 0}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-fg-subtle">
          Same window, same per-asset costs — ranked by {objLabel}. A winner here is a
          hypothesis to confirm out-of-sample (run it through Optimize's guards), not a
          deploy signal.
        </p>
      </CardContent>
    </Card>
  );
}

function SavedBakeoffs({
  bakeoffs, selectedId, onSelect,
}: {
  bakeoffs: Array<{
    id: string; created_at?: string | null; symbol?: string | null;
    timeframe?: string | null; objective?: string | null;
    n_strategies?: number | null; winner?: string | null;
  }>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Card>
      <CardHeader><CardTitle>Saved bake-offs</CardTitle></CardHeader>
      <CardContent>
        <div className="overflow-x-auto" data-testid="bakeoff-saved">
          <table className="w-full text-xs tabular">
            <thead className="text-fg-subtle">
              <tr>
                <th className="px-2 py-1 text-left">When</th>
                <th className="px-2 py-1 text-left">Asset</th>
                <th className="px-2 py-1 text-left">Rank by</th>
                <th className="px-2 py-1 text-right">Strategies</th>
                <th className="px-2 py-1 text-left">Winner</th>
                <th className="px-2 py-1" />
              </tr>
            </thead>
            <tbody>
              {bakeoffs.map((b) => (
                <tr key={b.id}
                  className={`border-t border-border ${selectedId === b.id ? "bg-accent-muted" : ""}`}>
                  <td className="px-2 py-1">{fmtDateTime(b.created_at ?? undefined)}</td>
                  <td className="px-2 py-1">{b.symbol}</td>
                  <td className="px-2 py-1">{OBJECTIVE_LABELS[b.objective ?? ""] ?? b.objective}</td>
                  <td className="px-2 py-1 text-right">{b.n_strategies ?? 0}</td>
                  <td className="px-2 py-1">{STRATEGY_LABELS[b.winner ?? ""] ?? b.winner}</td>
                  <td className="px-2 py-1 text-right">
                    <Button size="sm" variant="ghost" onClick={() => onSelect(b.id)}>View</Button>
                  </td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
