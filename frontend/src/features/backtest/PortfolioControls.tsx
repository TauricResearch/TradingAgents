/** Portfolio (multi-symbol) run controls (roadmap P3 / track T4): pick a
 * basket of 2+ symbols, a native strategy, timeframe, run length and sizing,
 * then launch one shared-broker backtest across them. The result is a normal
 * run record, so the live panel + Saved runs + result view below render it
 * unchanged. */
import { Layers, Play } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Segment, Segmented } from "@/components/ui/segmented";
import {
  BacktestCostConfirmation,
  runPortfolioBacktest,
  useBacktestStrategies,
} from "@/lib/api/queries";

const TF_CHOICES = ["5m", "15m", "1h", "4h", "1d"] as const;
const DURATIONS = ["1D", "7D", "30D", "1Y"] as const;
const MAX_SYMBOLS = 6;
// native (order-book) strategies only — the pipeline/LLM path is single-symbol
const NON_NATIVE = new Set(["pipeline_llm", "rules_v1"]);
const STRATEGY_LABELS: Record<string, string> = {
  trend_following_v1: "Trend following (Donchian)",
};

export default function PortfolioControls({
  symbols,
  onStarted,
}: {
  symbols: string[];
  onStarted: (jobId: string) => void;
}) {
  const strategiesQuery = useBacktestStrategies();
  const nativeStrategies = useMemo(
    () => (strategiesQuery.data?.strategies ?? []).filter((s) => !NON_NATIVE.has(s.id)),
    [strategiesQuery.data],
  );

  const universe = symbols.length ? symbols : ["BTC-USD", "ETH-USD", "SOL-USD", "XAUUSD"];
  const [selected, setSelected] = useState<string[]>(
    () => universe.slice(0, 2),
  );
  const [timeframe, setTimeframe] = useState("1d");
  const [duration, setDuration] = useState("1Y");
  const [strategyId, setStrategyId] = useState("trend_following_v1");
  const [initialEquity, setInitialEquity] = useState(100_000);
  const [riskPct, setRiskPct] = useState(1.0);
  const [maxPositionPct, setMaxPositionPct] = useState(33);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [cost, setCost] = useState<BacktestCostConfirmation["estimate"] | null>(null);

  const toggle = (symbol: string) => {
    setSelected((cur) =>
      cur.includes(symbol)
        ? cur.filter((s) => s !== symbol)
        : cur.length >= MAX_SYMBOLS
          ? cur
          : [...cur, symbol],
    );
  };

  const strategyOptions = nativeStrategies.length
    ? nativeStrategies.map((s) => s.id)
    : ["trend_following_v1"];

  const launch = async (confirmCost: boolean) => {
    setError(null);
    setCost(null);
    if (selected.length < 2) {
      setError("Pick at least two symbols for a portfolio run.");
      return;
    }
    setStarting(true);
    try {
      const { job_id } = await runPortfolioBacktest({
        symbols: selected,
        timeframe,
        duration,
        strategy_id: strategyId,
        initial_equity: initialEquity,
        risk_per_trade_pct: riskPct,
        max_position_pct: maxPositionPct,
        confirm_cost: confirmCost,
      });
      onStarted(job_id);
    } catch (err) {
      if (err instanceof BacktestCostConfirmation) setCost(err.estimate);
      else setError(String(err));
    } finally {
      setStarting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2">
        <Layers size={16} className="text-accent" />
        <CardTitle>Configure portfolio run</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3.5">
        <div>
          <div className="mb-1 text-xs uppercase tracking-wide text-fg-subtle">
            Symbols ({selected.length}/{MAX_SYMBOLS})
          </div>
          <div className="flex flex-wrap gap-1.5" data-testid="portfolio-symbols">
            {universe.map((s) => (
              <button
                key={s}
                type="button"
                data-testid={`portfolio-symbol-${s}`}
                aria-pressed={selected.includes(s)}
                onClick={() => toggle(s)}
                className={`rounded-[10px] border px-2.5 py-1 text-xs font-semibold transition-colors ${
                  selected.includes(s)
                    ? "border-accent bg-accent-muted text-accent"
                    : "border-border-strong bg-surface-2 text-fg-muted hover:text-fg"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <Field label="Timeframe">
            <Segmented data-testid="portfolio-timeframe">
              {TF_CHOICES.map((tf) => (
                <Segment key={tf} active={timeframe === tf}
                         onClick={() => setTimeframe(tf)} className="font-mono">
                  {tf}
                </Segment>
              ))}
            </Segmented>
          </Field>
          <Field label="Run length">
            <Segmented data-testid="portfolio-duration">
              {DURATIONS.map((d) => (
                <Segment key={d} active={duration === d}
                         onClick={() => setDuration(d)} className="font-mono">
                  {d}
                </Segment>
              ))}
            </Segmented>
          </Field>
          <Field label="Strategy">
            <select
              aria-label="Portfolio strategy"
              data-testid="portfolio-strategy"
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="h-[30px] rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs"
            >
              {strategyOptions.map((id) => (
                <option key={id} value={id}>{STRATEGY_LABELS[id] ?? id}</option>
              ))}
            </select>
          </Field>
          <Field label="Starting equity">
            <input
              type="number" aria-label="Starting equity"
              data-testid="portfolio-equity" min={1000} step={1000}
              value={initialEquity}
              onChange={(e) => setInitialEquity(Math.max(1, Number(e.target.value) || 0))}
              className="h-[30px] w-28 rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs tabular"
            />
          </Field>
          <Field label="Risk %/trade">
            <input
              type="number" aria-label="Risk percent per trade"
              data-testid="portfolio-risk-pct" min={0.1} max={5} step={0.1}
              value={riskPct}
              onChange={(e) =>
                setRiskPct(Math.min(5, Math.max(0.1, Number(e.target.value) || 0.1)))}
              className="h-[30px] w-16 rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs tabular"
            />
          </Field>
          <Field label="Max position %">
            <input
              type="number" aria-label="Max position percent of equity"
              data-testid="portfolio-max-position-pct" min={1} max={100} step={1}
              value={maxPositionPct}
              onChange={(e) =>
                setMaxPositionPct(Math.min(100, Math.max(1, Number(e.target.value) || 1)))}
              className="h-[30px] w-16 rounded-[10px] border border-border-strong bg-surface-2 px-2.5 text-xs tabular"
            />
          </Field>
          <Button onClick={() => void launch(false)}
                  disabled={starting || cost != null || selected.length < 2}
                  data-testid="portfolio-run">
            <Play size={13} />
            {starting ? "Starting…" : "Run portfolio"}
          </Button>
        </div>

        <p className="text-xs text-fg-subtle">
          One native strategy trades the basket on a shared broker — position
          and gross-exposure caps bind across the whole portfolio (portfolio
          heat). Each symbol decides from its own look-ahead-safe bars on a
          merged clock.
        </p>

        {cost && (
          <div className="rounded-md border border-accent/40 bg-accent-muted px-3 py-2 text-xs"
               data-testid="portfolio-cost-confirm">
            <div className="mb-1.5">
              This basket is a big full-density run:{" "}
              <span className="font-bold">
                {cost.decisions.toLocaleString()} decisions
              </span>{" "}
              over ~{cost.est_minutes} min (free, saved to history). Proceed?
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => void launch(true)}
                      data-testid="portfolio-cost-ok">
                Run anyway
              </Button>
              <Button size="sm" variant="outline" onClick={() => setCost(null)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
        {error && <p className="text-xs text-bear" data-testid="portfolio-error">{error}</p>}
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
