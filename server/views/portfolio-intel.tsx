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

// ── Allocation bar ────────────────────────────────────────────────────────────

function AllocationBarSection({ bar }: { bar: PortfolioIntel["allocation_bar"] }) {
  if (!bar) return null
  const { buckets, actual, targets } = bar
  return (
    <div class="allocation-bar-section" style="margin:1.5rem 0">
      <h4>Allocation Bar (Target vs Actual)</h4>
      <div style="height:24px;display:flex;border-radius:4px;overflow:hidden;margin:8px 0">
        {buckets.map((b) => (
          <div
            style={`display:inline-block;height:24px;width:${b.actual_pct}%;background:${b.color};`}
            title={`${b.label}: ${b.actual_pct}% (target ${b.target_pct}%)`}
          />
        ))}
      </div>
      <div style="font-size:0.75em;color:var(--text-dim)">
        {buckets.map((b) => (
          <span style="margin-right:16px">
            <span
              style={`display:inline-block;width:10px;height:10px;border-radius:2px;background:${b.color};vertical-align:middle;margin-right:4px`}
            />
            {b.label}: {b.actual_pct}% (target {b.target_pct}%)
          </span>
        ))}
      </div>
      {actual.cash_pct < targets.cash_reserve_pct && (
        <div class="hint" style="margin-top:4px">
          ⚠️ Cash below target ({actual.cash_pct}% &lt; {targets.cash_reserve_pct}%)
        </div>
      )}
      {actual.spreadbet_pct > targets.spreadbet_pct && (
        <div class="hint" style="margin-top:4px">
          ⚠️ Spread bet above target ({actual.spreadbet_pct}% &gt; {targets.spreadbet_pct}%)
        </div>
      )}
    </div>
  )
}

// ── Cash breakdown ────────────────────────────────────────────────────────────

function CashBreakdownPanel({ breakdown }: { breakdown: PortfolioIntel["cash_breakdown"] }) {
  if (!breakdown) return null
  return (
    <div class="cash-breakdown" style="margin:1.5rem 0">
      <h4>Cash Breakdown</h4>
      <div class="intel-hero" style="margin-top:0.5rem">
        <div class="intel-stat">
          <div class="intel-label">Total Cash</div>
          <div class={`intel-value${breakdown.cash_negative ? " negative" : ""}`}>
            £{fmtIntel(breakdown.total_cash_gbp)}
          </div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Reserve ({breakdown.reserve_pct}%)</div>
          <div class="intel-value">£{fmtIntel(breakdown.reserve_gbp)}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Spread Bet Alloc ({breakdown.spreadbet_allocation_pct}%)</div>
          <div class="intel-value">£{fmtIntel(breakdown.spreadbet_allocation_gbp)}</div>
        </div>
        <div class="intel-stat">
          <div class="intel-label">Investable</div>
          <div class="intel-value">£{fmtIntel(breakdown.investable_gbp)}</div>
        </div>
      </div>
    </div>
  )
}

// ── Accounts table ────────────────────────────────────────────────────────────

function AccountsTable({ accounts }: { accounts: PortfolioIntel["accounts"] }) {
  if (!accounts || accounts.length === 0) {
    return <div class="muted">No accounts configured</div>
  }
  return (
    <div style="margin:1.5rem 0">
      <h4>Accounts</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>Account</th>
            <th>Type</th>
            <th>Cash</th>
            <th>Deployed</th>
            <th>Spread Bet</th>
            <th>Total</th>
            <th>Positions</th>
            <th>Bets</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => (
            <tr>
              <td>
                <strong>{escIntel(a.name || a.id)}</strong>
                {a.notes && <div class="muted" style="font-size:0.75em">{escIntel(a.notes)}</div>}
              </td>
              <td>
                <span class="platform-tag">{escIntel(a.account_type)}</span>
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                £{fmtIntel(a.balance_gbp)}
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                £{fmtIntel(a.deployed_gbp)}
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                £{fmtIntel(a.spreadbet_gbp)}
              </td>
              <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                <strong>£{fmtIntel(a.total_value_gbp)}</strong>
              </td>
              <td>{a.positions_count}</td>
              <td>{a.bets_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Spread bet table ─────────────────────────────────────────────────────────

function SpreadBetTable({ bets }: { bets: PortfolioIntel["spreadbets"] }) {
  if (!bets || bets.length === 0) {
    return <div class="muted">No open spread bets</div>
  }
  return (
    <div style="margin:1.5rem 0">
      <h4>Spread Bet Positions</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Direction</th>
            <th>Stake/£pt</th>
            <th>Entry</th>
            <th>Current</th>
            <th>P&L</th>
            <th>P&L %</th>
            <th>Notional</th>
          </tr>
        </thead>
        <tbody>
          {bets.map((b) => {
            const pnlCls = b.pnl_gbp != null ? (b.pnl_gbp >= 0 ? "positive" : "negative") : ""
            return (
              <tr>
                <td class="ticker">{escIntel(b.ticker)}</td>
                <td>
                  <span class={b.direction === "long" ? "positive" : "negative"}>
                    {b.direction.toUpperCase()}
                  </span>
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {fmtIntel(b.stake_per_point)}
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  £{fmtIntel(b.entry_price)}
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {b.current_price_gbp != null ? `£${fmtIntel(b.current_price_gbp)}` : "—"}
                </td>
                <td class={pnlCls} style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {b.pnl_gbp != null ? (b.pnl_gbp >= 0 ? "+" : "") + `£${fmtIntel(b.pnl_gbp)}` : "—"}
                </td>
                <td class={pnlCls} style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  {b.pnl_pct != null ? (b.pnl_pct >= 0 ? "+" : "") + `${fmtIntel(b.pnl_pct)}%` : "—"}
                </td>
                <td style="font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">
                  £{fmtIntel(b.notional_gbp)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Research queue ─────────────────────────────────────────────────────────────

function ResearchQueue({ items }: { items: PortfolioIntel["research_queue"] }) {
  if (!items || items.length === 0) {
    return <div class="muted">No approved research items</div>
  }
  return (
    <div style="margin:1.5rem 0">
      <h4>Research Queue (Approved)</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Exchange</th>
            <th>Priority</th>
            <th>Signal</th>
            <th>Added</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr>
              <td class="ticker">{escIntel(i.ticker)}</td>
              <td>{escIntel(i.exchange)}</td>
              <td>
                <span class={i.priority === "high" ? "negative" : i.priority === "medium" ? "" : "muted"}>
                  {escIntel(i.priority)}
                </span>
              </td>
              <td>{escIntel(i.last_signal) || "—"}</td>
              <td>{escIntel(i.added_date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
      <AllocationBarSection bar={data.allocation_bar} />
      <CashBreakdownPanel breakdown={data.cash_breakdown} />
      <AccountsTable accounts={data.accounts} />
      <SpreadBetTable bets={data.spreadbets} />
      <ResearchQueue items={data.research_queue} />
      <AssetClassBars assetClasses={data.asset_classes} totalValue={data.total_value_gbp} />
      <PlatformTable platforms={data.platforms} />
      <GovernancePanel data={data} />
    </>
  )
}
