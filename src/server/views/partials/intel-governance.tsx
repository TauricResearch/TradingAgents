/**
 * Governance alerts panel — shows active rule violations from the risk engine.
 */

/** @jsxImportSource hono/jsx */

import type { PortfolioIntel } from "../../lib/portfolio-intel-data.ts"
import { fmtCommas } from "../../lib/markup.ts"

export function GovernancePanel({ data }: { data: PortfolioIntel }) {
  const gov = data.governance

  return (
    <>
      {gov.violations && gov.violations.length > 0 ? (
        <>
          <h4>⚠️ Violations</h4>
          {gov.violations.map((v) => {
            const cls = v.severity === "breach" ? "violation-breach" : "violation-warn"
            return (
              <div class={cls}>
                <strong>{v.rule.name}</strong>: {v.detail}
              </div>
            )
          })}
        </>
      ) : (
        <div class="ok">✅ All rules satisfied</div>
      )}

      {gov.suggestions && gov.suggestions.length > 0 && (
        <>
          <h4 style="margin-top:1rem">Rebalance Suggestions</h4>
          <table class="data-table" style="font-size:0.85em">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Action</th>
                <th>Current</th>
                <th>Target</th>
                <th>Drift</th>
              </tr>
            </thead>
            <tbody>
              {gov.suggestions.map((s) => (
                <tr>
                  <td class="ticker">{s.ticker}</td>
                  <td class={s.action === "trim" ? "negative" : "positive"}>
                    {s.action.toUpperCase()}
                  </td>
                  <td>{fmtCommas(s.currentWeight)}%</td>
                  <td>{fmtCommas(s.targetWeight)}%</td>
                  <td>{fmtCommas(s.delta)}pp</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}
