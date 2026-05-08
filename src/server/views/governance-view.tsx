/** @jsxImportSource hono/jsx */

import type { GovernanceRule, RebalanceSuggestion, RuleViolation } from "../lib/governance-data.ts"

// ── Rules table ─────────────────────────────────────────────────────────────────

export function RulesTable({ rules }: { rules: GovernanceRule[] }) {
  return (
    <table class="data-table">
      <thead>
        <tr>
          <th>Rule</th>
          <th>Limit</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        {rules.map((r) => (
          <tr>
            <td>{r.name}</td>
            <td>
              {r.limit}
              {r.unit === "%" ? "%" : r.unit === "count" ? "" : r.unit}
            </td>
            <td class="muted">{r.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Violations panel ──────────────────────────────────────────────────────────

export function ViolationsPanel({
  portfolioValue,
  cashPct,
  violations,
  suggestions,
  note,
}: {
  portfolioValue: number
  cashPct: number
  violations: RuleViolation[]
  suggestions: RebalanceSuggestion[]
  note?: string
}) {
  if (note) {
    return <div class="muted">{note}</div>
  }

  return (
    <>
      <div class="governance-summary">
        <div>
          Portfolio: &pound;{portfolioValue.toFixed(2)}{" "}
          <span class="muted">(base: GBP)</span>
        </div>
        <div>Cash: {cashPct.toFixed(1)}%</div>
      </div>

      {violations.length > 0 ? (
        <>
          <h4>⚠️ Violations</h4>
          {violations.map((v) => {
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

      {suggestions.length > 0 && (
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
              {suggestions.map((s) => (
                <tr>
                  <td class="ticker">{s.ticker}</td>
                  <td class={s.action === "trim" ? "negative" : "positive"}>
                    {s.action.toUpperCase()}
                  </td>
                  <td>{s.currentWeight.toFixed(1)}%</td>
                  <td>{s.targetWeight.toFixed(1)}%</td>
                  <td>{s.delta.toFixed(1)}pp</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}
