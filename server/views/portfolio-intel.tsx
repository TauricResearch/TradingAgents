/** @jsxImportSource hono/jsx */

import type {
  AssetClassAllocation,
  PlatformAllocation,
  PortfolioIntel,
} from "../lib/portfolio-intel-data.ts"

// ── Helpers ───────────────────────────────────────────────────────────────────

function escIntel(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

function fmtIntel(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—"
  const s = n.toFixed(2)
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
}

const ASSET_COLORS: Record<string, string> = {
  cash: "#3b82f6",
  equity: "#22c55e",
  etf: "#eab308",
  crypto: "#ef4444",
}

// ── Hero ──────────────────────────────────────────────────────────────────────

function IntelHero({ data }: { data: PortfolioIntel }) {
  return (
    <>
      {data.cash_negative && (
        <div class="banner" style="margin-bottom:1rem">
          \u26a0\ufe0f hledger cash is negative — more sells recorded than buys in journal.
          Total and % figures may be misleading until hledger cash is corrected.
        </div>
      )}
      <div class="intel-hero">
        <div class="intel-stat">
          <div class="intel-label">Total Portfolio</div>
          <div class="intel-value">\u00a3{fmtIntel(data.total_value_gbp)}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Cash</div>
          <div class={`intel-value${data.cash_negative ? " negative" : ""}`}>
            \u00a3{fmtIntel(data.cash_gbp)}
            <span class="intel-pct"> ({fmtIntel(data.cash_pct_raw)}%)</span>
          </div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Positions</div>
          <div class="intel-value">{data.positions_count}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Live Value</div>
          <div class="intel-value">\u00a3{fmtIntel(data.position_value_gbp)}</div>
        </div>
      </div>
      <div class="intel-fx">
        {data.fx_rates.GBPEUR > 0 && (
          <span>GBPEUR: {data.fx_rates.GBPEUR.toFixed(4)}</span>
        )}
        {data.fx_rates.GBPUSD > 0 && (
          <span>GBPUSD: {data.fx_rates.GBPUSD.toFixed(4)}</span>
        )}
      </div>
    </>
  )
}

// ── Asset class allocation ────────────────────────────────────────────────────

function AssetClassBars({ assetClasses, totalValue }: { assetClasses: AssetClassAllocation[]; totalValue: number }) {
  if (!assetClasses || assetClasses.length === 0) {
    return <div class="muted">No allocation data</div>
  }

  const total = totalValue || 1

  return (
    <div class="allocation-bar">
      <div style="height:16px;display:flex">
        {assetClasses.map((ac) => {
          const w = Math.round((ac.value_gbp / total) * 100)
          const color = ASSET_COLORS[ac.assetClass] ?? "#71717a"
          return (
            <div
              style={`display:inline-block;height:16px;width:${w}%;background:${color};margin-right:2px`}
              title={`${ac.assetClass}: ${w}% (${ac.value_gbp.toFixed(0)} GBP)`}
            />
          )
        })}
      </div>
      <div style="margin-top:4px;font-size:0.75em;color:var(--text-dim)">
        {assetClasses.map((ac) => {
          const w = Math.round((ac.value_gbp / total) * 100)
          const color = ASSET_COLORS[ac.assetClass] ?? "#71717a"
          return (
            <span style="margin-right:12px">
              <span
                style={`display:inline-block;width:10px;height:10px;border-radius:2px;background:${color};vertical-align:middle;margin-right:4px`}
              />
              {ac.assetClass} {w}% ({ac.value_gbp.toFixed(0)})
            </span>
          )
        })}
      </div>
    </div>
  )
}

// ── Platform table ────────────────────────────────────────────────────────────

function PlatformTable({ platforms }: { platforms: PlatformAllocation[] }) {
  if (!platforms || platforms.length === 0) {
    return <div class="muted">No platform data</div>
  }

  return (
    <table class="data-table">
      <thead>
        <tr>
          <th>Platform</th>
          <th>Total Value</th>
          <th>Weight</th>
          <th>Cash</th>
          <th>Positions</th>
        </tr>
      </thead>
      <tbody>
        {platforms.map((p) => (
          <tr>
            <td>
              <span class="platform-tag">{escIntel(p.platform)}</span>
            </td>
            <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
              \u00a3{fmtIntel(p.total_value_gbp)}
            </td>
            <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
              {fmtIntel(p.weight_pct)}%
            </td>
            <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
              \u00a3{fmtIntel(p.cash_gbp)}{" "}
              <span class="muted">({fmtIntel(p.cash_pct)}%)</span>
            </td>
            <td>
              {p.positions.map((pos) => {
                const pnl = pos.pnl_pct
                const pnlCls = pnl != null ? (pnl >= 0 ? "positive" : "negative") : ""
                const pnlStr = pnl != null ? `${(pnl >= 0 ? "+" : "") + fmtIntel(pnl)}%` : ""
                return (
                  <span class="position-pill">
                    {escIntel(pos.ticker)}{" "}
                    <span class={pnlCls}>{pnlStr}</span>
                  </span>
                )
              })}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Governance ──────────────────────────────────────────────────────────────

function GovernancePanel({ data }: { data: PortfolioIntel }) {
  const gov = data.governance

  return (
    <>
      {gov.violations && gov.violations.length > 0 ? (
        <>
          <h4>\u26a0\ufe0f Violations</h4>
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
        <div class="ok">\u2705 All rules satisfied</div>
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
                  <td>{fmtIntel(s.currentWeight)}%</td>
                  <td>{fmtIntel(s.targetWeight)}%</td>
                  <td>{fmtIntel(s.delta)}pp</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function PortfolioIntelView({ data }: { data: PortfolioIntel }) {
  return (
    <>
      <IntelHero data={data} />
      <AssetClassBars assetClasses={data.asset_classes} totalValue={data.total_value_gbp} />
      <PlatformTable platforms={data.platforms} />
      <GovernancePanel data={data} />
    </>
  )
}
