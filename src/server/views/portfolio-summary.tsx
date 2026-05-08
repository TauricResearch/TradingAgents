/** @jsxImportSource hono/jsx */

import type { PortfolioSummary } from "../lib/portfolio-data.ts"
import { esc, fmt } from "../lib/markup.ts"

// ── Helpers ───────────────────────────────────────────────────────────────────

function cls(pnl: number | null | undefined): string {
  if (pnl == null) return ""
  if (pnl > 0) return "positive"
  if (pnl < 0) return "negative"
  return ""
}

function fmtPnl(pnl: number | null | undefined): string {
  if (pnl == null) return "\u2014"
  const sign = pnl >= 0 ? "+" : ""
  return `${sign}${fmt(pnl, 2)}`
}

// ── Main component ────────────────────────────────────────────────────────────

export function PortfolioSummaryView({ data }: { data: PortfolioSummary }) {
  const totals = data.totals
  const pnl = totals.total_pnl_gbp
  const pnlCls = cls(pnl)

  return (
    <>
      <section class="panel" id="pnl-panel">
        <h3>
          <span id="pnl-title">Portfolio Summary</span>
        </h3>
        <div id="pnl-summary">
          <div
            class="pnl-totals"
            style="display:flex;gap:2rem;margin-bottom:1rem;flex-wrap:wrap"
          >
            <div>
              <div class="muted" style="font-size:0.75em">
                Portfolio Value
              </div>
              <div
                id="pnl-total-value"
                style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1"
              >
                £{fmt(totals.portfolio_value_gbp)}
              </div>
            </div>
            <div>
              <div class="muted" style="font-size:0.75em">
                Total Cost
              </div>
              <div
                id="pnl-total-cost"
                style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1"
              >
                £{fmt(totals.total_cost_gbp)}
              </div>
            </div>
            <div>
              <div class="muted" style="font-size:0.75em">
                Unrealised P&L
              </div>
              <div
                id="pnl-total-pnl"
                style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1"
                class={`pnl-cell ${pnlCls}`}
              >
                £{fmtPnl(pnl)}
                {totals.total_pnl_pct != null
                  ? ` (${pnl != null && pnl >= 0 ? "+" : ""}${fmt(totals.total_pnl_pct)}%)`
                  : " \u2014"}
              </div>
            </div>
          </div>
          <p class="muted" style="font-size:0.75em;margin:0">
            Prices in GBP via live FX conversion (GBPEUR, GBPUSD). Sorted by
            P&L descending (worst positions first).
          </p>
        </div>
      </section>

      <section class="panel">
        <h3>Positions</h3>
        <div style="overflow-x:auto">
          <table id="positions-table" class="positions-table">
            <thead>
              <tr>
                <th>Platform</th>
                <th>Ticker</th>
                <th>Qty</th>
                <th>Avg Cost</th>
                <th>Current</th>
                <th>Value (GBP)</th>
                <th>P&L</th>
                <th class="date-col">Entry</th>
                <th>Thesis</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="positions-tbody">
              {!data.positions || data.positions.length === 0 ? (
                <tr>
                  <td colSpan={10} class="muted">
                    No open positions
                  </td>
                </tr>
              ) : (
                data.positions.map((p) => {
                  const pnlCls = cls(p.pnl_gbp)
                  const pnlStr =
                    p.pnl_gbp != null
                      ? `${fmtPnl(p.pnl_gbp)}${p.pnl_pct != null ? ` (${p.pnl_pct >= 0 ? "+" : ""}${fmt(p.pnl_pct)}%)` : ""}`
                      : "\u2014"
                  const curPrice =
                    p.current_price_gbp != null
                      ? `£${fmt(p.current_price_gbp)}`
                      : "\u2014"
                  const curVal =
                    p.current_value_gbp != null
                      ? `£${fmt(p.current_value_gbp)}`
                      : "\u2014"

                  return (
                    <tr>
                      <td>
                        <span class="platform-tag">{esc(p.platform)}</span>
                      </td>
                      <td class="ticker">{esc(p.ticker)}</td>
                      <td>{fmt(p.quantity)}</td>
                      <td>£{fmt(p.avg_cost)}</td>
                      <td
                        style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1"
                      >
                        {curPrice}
                      </td>
                      <td
                        style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1"
                      >
                        {curVal}
                      </td>
                      <td
                        class={`pnl-cell ${pnlCls}`}
                        style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1"
                      >
                        {pnlStr}
                      </td>
                      <td class="date-col">{p.entry_date}</td>
                      <td>{esc(p.thesis) || "\u2014"}</td>
                      <td>
                        <button
                          class="btn-sm"
                          hx-delete={`/api/positions/${p.id}`}
                          hx-target="#portfolio-wrapper"
                          hx-swap="innerHTML"
                          hx-confirm="Close this position?"
                        >
                          Close
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
