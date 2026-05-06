/** @jsxImportSource hono/jsx */

import type { PeriodReturn } from "../lib/benchmark-data.ts"

// ── Benchmark table ───────────────────────────────────────────────────────────

export function BenchmarkTable({
  ticker,
  currentValue,
  periodReturns,
}: {
  ticker: string
  currentValue: number
  periodReturns: PeriodReturn[]
}) {
  return (
    <>
      <div class="benchmark-summary">
        <div>
          Portfolio value: &pound;{currentValue.toFixed(2)}{" "}
          <span class="muted">(base: GBP, live prices)</span>
        </div>
        <div>Benchmark: {ticker}</div>
      </div>

      {periodReturns.length > 0 ? (
        <table class="data-table">
          <thead>
            <tr>
              <th>Period</th>
              <th>Portfolio</th>
              <th>Benchmark</th>
              <th>Alpha</th>
            </tr>
          </thead>
          <tbody>
            {periodReturns.map((r) => {
              const pClass = r.portfolioPct >= 0 ? "positive" : "negative"
              const bClass = r.benchmarkPct >= 0 ? "positive" : "negative"
              const aClass = r.alpha >= 0 ? "positive" : "negative"
              return (
                <tr key={r.period}>
                  <td>{r.period}</td>
                  <td class={pClass}>
                    {r.portfolioPct >= 0 ? "+" : ""}
                    {r.portfolioPct.toFixed(1)}%
                  </td>
                  <td class={bClass}>
                    {r.benchmarkPct >= 0 ? "+" : ""}
                    {r.benchmarkPct.toFixed(1)}%
                  </td>
                  <td class={aClass}>
                    {r.alpha >= 0 ? "+" : ""}
                    {r.alpha.toFixed(1)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      ) : (
        <div class="muted">Insufficient benchmark data (need at least 3 months)</div>
      )}
    </>
  )
}
