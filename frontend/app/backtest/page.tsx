"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { InfoTip } from "@/components/InfoTip";
import { StateBlock } from "@/components/StateBlock";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";

export default function BacktestPage() {
  const [start, setStart] = useState("2025-01-01");
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));
  const run = useMutation({
    mutationFn: () =>
      api.backtest({
        universe: "NIFTY50",
        start_date: start,
        end_date: end,
        research_depth: "medium",
        holding_days: 5,
      }),
  });
  const result = run.data as {
    initial_capital?: number;
    final_capital?: number;
    number_of_decisions?: number;
    ai_strategy?: { total_return?: number; win_rate?: number; max_drawdown?: number; sharpe?: number };
    buy_hold?: { total_return?: number | null };
    equity_curve?: number[];
    note?: string;
  } | undefined;

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">
        Historical evaluation
        <InfoTip text="Scores your saved AI decisions against later prices. It does not replay the LLM on every day, and it does not claim profitability." />
      </h1>
      <div className="grid gap-3 rounded-xl border border-line bg-ink-800 p-4 md:grid-cols-4">
        <label className="text-sm text-mist">
          Universe
          <input disabled value="NIFTY 50" className="mt-1 w-full rounded-md border border-line bg-ink-900 px-2 py-2 text-white" />
        </label>
        <label className="text-sm text-mist">
          Start
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 w-full rounded-md border border-line bg-ink-900 px-2 py-2 text-white" />
        </label>
        <label className="text-sm text-mist">
          End
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="mt-1 w-full rounded-md border border-line bg-ink-900 px-2 py-2 text-white" />
        </label>
        <button onClick={() => run.mutate()} className="self-end rounded-md bg-gold px-3 py-2 text-sm font-semibold text-ink-950">
          RUN
        </button>
      </div>
      {run.isError && <StateBlock title="Evaluation failed" message={(run.error as Error).message} onRetry={() => run.mutate()} />}
      {result && (
        <div className="space-y-4">
          <p className="text-sm text-mist">{result.note}</p>
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Initial Capital" value="₹1,00,000" />
            <Metric label="Final Capital" value={result.final_capital?.toLocaleString("en-IN") || "—"} />
            <Metric label="AI Return" value={pct((result.ai_strategy?.total_return || 0) * 100)} />
            <Metric label="Buy & Hold NIFTY" value={result.buy_hold?.total_return == null ? "—" : pct(result.buy_hold.total_return * 100)} />
            <Metric label="Win Rate" value={result.ai_strategy?.win_rate == null ? "—" : pct((result.ai_strategy.win_rate || 0) * 100)} />
            <Metric label="Max Drawdown" value={result.ai_strategy?.max_drawdown == null ? "—" : pct((result.ai_strategy.max_drawdown || 0) * 100)} />
            <Metric label="Sharpe" value={result.ai_strategy?.sharpe == null ? "—" : result.ai_strategy.sharpe.toFixed(2)} />
            <Metric label="Decisions" value={String(result.number_of_decisions ?? 0)} />
          </div>
          {result.equity_curve && (
            <div className="h-64 rounded-xl border border-line bg-ink-800 p-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result.equity_curve.map((value, i) => ({ i, value }))}>
                  <CartesianGrid stroke="#1d2a38" />
                  <XAxis dataKey="i" hide />
                  <YAxis stroke="#9bb0c3" />
                  <Tooltip contentStyle={{ background: "#101820", border: "1px solid #243140" }} />
                  <Line dataKey="value" stroke="#c8a15a" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-ink-800 p-4">
      <p className="text-xs text-mist">{label}</p>
      <p className="mt-1 text-xl tabular">{value}</p>
    </div>
  );
}
