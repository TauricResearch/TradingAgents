"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Area, ComposedChart,
} from "recharts";
import { Simulation } from "@/lib/api";
import type { SimDetail, SimRunRequest, SimTrade } from "@/lib/types";

export default function SimulationPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["sim-list"], queryFn: () => Simulation.list() });

  const [name, setName] = useState("");
  const [startingCapital, setStartingCapital] = useState("10000");
  const [trades, setTrades] = useState<SimTrade[]>([
    { ticker: "NVDA", shares: 10, entry_price: 200, hold_days: 30 },
  ]);
  const [historyDays, setHistoryDays] = useState("180");
  const [result, setResult] = useState<SimDetail | null>(null);

  const run = useMutation({
    mutationFn: (req: SimRunRequest) => Simulation.run(req),
    onSuccess: (r) => {
      setResult(r);
      qc.invalidateQueries({ queryKey: ["sim-list"] });
    },
  });

  function addTrade() {
    setTrades([...trades, { ticker: "", shares: 1, entry_price: 100, hold_days: 30 }]);
  }
  function updateTrade(i: number, field: keyof SimTrade, value: any) {
    const next = [...trades];
    (next[i] as any)[field] = value;
    setTrades(next);
  }
  function removeTrade(i: number) {
    setTrades(trades.filter((_, j) => j !== i));
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold">Portfolio simulation</h1>
        <p className="text-muted text-sm">
          Project a hypothetical scenario forward using historical drift +
          volatility. Compares to a SPY-only baseline over the same window.
        </p>
      </header>

      {/* ---- Scenario builder ---- */}
      <div className="card space-y-3">
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="label">Scenario name</label>
            <input className="input w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="optional" />
          </div>
          <div>
            <label className="label">Starting capital ($)</label>
            <input className="input w-full" type="number" step="any" value={startingCapital} onChange={(e) => setStartingCapital(e.target.value)} />
          </div>
          <div>
            <label className="label">History window (days)</label>
            <input className="input w-full" type="number" min={30} max={1825} value={historyDays} onChange={(e) => setHistoryDays(e.target.value)} />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="label !mb-0">Trades</span>
            <button className="btn text-xs" onClick={addTrade}>+ Add trade</button>
          </div>
          <div className="space-y-2">
            {trades.map((t, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-end">
                <div className="col-span-3">
                  <label className="label">Ticker</label>
                  <input
                    className="input w-full"
                    value={t.ticker}
                    onChange={(e) => updateTrade(i, "ticker", e.target.value.toUpperCase())}
                  />
                </div>
                <div className="col-span-2">
                  <label className="label">Shares</label>
                  <input className="input w-full" type="number" step="any" value={t.shares} onChange={(e) => updateTrade(i, "shares", parseFloat(e.target.value) || 0)} />
                </div>
                <div className="col-span-3">
                  <label className="label">Entry price ($)</label>
                  <input className="input w-full" type="number" step="any" value={t.entry_price} onChange={(e) => updateTrade(i, "entry_price", parseFloat(e.target.value) || 0)} />
                </div>
                <div className="col-span-3">
                  <label className="label">Hold (days)</label>
                  <input className="input w-full" type="number" min={1} max={1095} value={t.hold_days} onChange={(e) => updateTrade(i, "hold_days", parseInt(e.target.value) || 1)} />
                </div>
                <div className="col-span-1 text-right">
                  <button className="btn btn-danger text-xs" onClick={() => removeTrade(i)}>✕</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end">
          <button
            className="btn btn-primary"
            disabled={run.isPending || trades.some((t) => !t.ticker)}
            onClick={() => run.mutate({
              name: name || undefined,
              starting_capital: parseFloat(startingCapital),
              history_days: parseInt(historyDays),
              trades,
            })}
          >
            {run.isPending ? "Simulating…" : "▶ Run simulation"}
          </button>
        </div>
        {run.isError && <div className="text-sm text-danger">{(run.error as Error).message}</div>}
      </div>

      {/* ---- Result ---- */}
      {result && <SimResultCard sim={result} />}

      {/* ---- Saved sims ---- */}
      <div className="card">
        <h2 className="font-semibold mb-2">Saved simulations</h2>
        {(list.data?.length ?? 0) === 0 && <div className="text-sm text-muted">No saved sims yet.</div>}
        <div className="space-y-1">
          {(list.data ?? []).map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-3 py-1.5 border-b border-border last:border-0 text-sm">
              <div className="flex-1 min-w-0">
                <div className="font-medium">{s.name ?? `sim #${s.id}`}</div>
                <div className="text-xs text-muted">{s.created_at} · {s.ticker ?? ""}</div>
              </div>
              <button className="btn text-xs" onClick={async () => {
                const detail = await Simulation.get(s.id);
                setResult(detail);
              }}>Open</button>
              <button className="btn btn-danger text-xs" onClick={async () => {
                if (confirm("Delete?")) {
                  await Simulation.delete(s.id);
                  qc.invalidateQueries({ queryKey: ["sim-list"] });
                  if (result?.id === s.id) setResult(null);
                }
              }}>✕</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SimResultCard({ sim }: { sim: SimDetail }) {
  const r = sim.result;
  const data = r.points.map((p) => ({
    day: p.day,
    portfolio: p.portfolio,
    baseline: p.baseline_spy,
    low: p.portfolio_low,
    high: p.portfolio_high,
  }));

  return (
    <div className="card space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">{r.name}</h2>
          <p className="text-xs text-muted">
            {r.horizon_days}-day projection from ${r.starting_capital.toFixed(2)} starting capital
          </p>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold tabular-nums ${r.alpha_pct >= 0 ? "text-success" : "text-danger"}`}>
            {r.alpha_pct >= 0 ? "+" : ""}{r.alpha_pct.toFixed(2)}%
          </div>
          <div className="text-xs text-muted">vs SPY baseline</div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Final value" value={`$${r.expected_final_value.toFixed(2)}`} accent={r.expected_return_pct >= 0 ? "success" : "danger"} />
        <Stat label="Return" value={`${r.expected_return_pct >= 0 ? "+" : ""}${r.expected_return_pct.toFixed(2)}%`} accent={r.expected_return_pct >= 0 ? "success" : "danger"} />
        <Stat label="SPY final" value={`$${r.baseline_final_value.toFixed(2)}`} />
        <Stat label="SPY return" value={`${r.baseline_return_pct >= 0 ? "+" : ""}${r.baseline_return_pct.toFixed(2)}%`} />
      </div>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgb(var(--border))" strokeDasharray="3 3" />
            <XAxis dataKey="day" stroke="rgb(var(--muted))" tick={{ fontSize: 11 }} />
            <YAxis stroke="rgb(var(--muted))" tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--border))", borderRadius: 6, fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area type="monotone" dataKey="high" stroke="none" fill="rgb(var(--accent) / 0.1)" />
            <Area type="monotone" dataKey="low" stroke="none" fill="rgb(var(--bg))" />
            <Line type="monotone" dataKey="portfolio" stroke="rgb(var(--accent))" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="baseline" stroke="rgb(var(--muted))" strokeWidth={1.25} dot={false} strokeDasharray="4 4" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <details className="text-xs">
        <summary className="cursor-pointer text-muted">Per-trade stats</summary>
        <table className="w-full mt-2">
          <thead>
            <tr className="text-muted">
              <th className="text-left py-1 px-2">Ticker</th>
              <th className="text-right py-1 px-2">Shares</th>
              <th className="text-right py-1 px-2">Entry $</th>
              <th className="text-right py-1 px-2">Cost</th>
              <th className="text-right py-1 px-2">μ (annual)</th>
              <th className="text-right py-1 px-2">σ (annual)</th>
            </tr>
          </thead>
          <tbody>
            {r.per_trade.map((t, i) => (
              <tr key={i} className="border-t border-border">
                <td className="py-1 px-2 font-semibold">{t.ticker}</td>
                <td className="py-1 px-2 text-right">{t.shares}</td>
                <td className="py-1 px-2 text-right">${t.entry_price.toFixed(2)}</td>
                <td className="py-1 px-2 text-right">${t.cost.toFixed(2)}</td>
                <td className="py-1 px-2 text-right">{(t.mu_annual * 100).toFixed(2)}%</td>
                <td className="py-1 px-2 text-right">{(t.sigma_annual * 100).toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: "success" | "danger" }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className={`text-lg font-semibold ${accent === "success" ? "text-success" : accent === "danger" ? "text-danger" : ""}`}>{value}</div>
    </div>
  );
}
