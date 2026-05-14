/**
 * Holdings view — shell that loads /api/holdings/html via HTMX.
 */

/** @jsxImportSource hono/jsx */

import { esc, fmt, fmtGBP } from "../lib/markup.ts"

// ── Shared UI components ────────────────────────────────────────────────────

export function StopBadge({ level }: { level: string }) {
  if (level === "danger")
    return (
      <span class="stop-badge stop-danger" title="Stop triggered or within 5%">
        🔴 stop
      </span>
    );
  if (level === "watch")
    return (
      <span class="stop-badge stop-watch" title="Stop within 5—20%">
        🟡 watch
      </span>
    );
  if (level === "safe")
    return (
      <span class="stop-badge stop-safe" title="Stop &gt;20% above current price">
        🟢 ok
      </span>
    );
  return <span class="stop-badge stop-none" title="No exit plan">—</span>;
}

export function FreshnessBadge({ dateStr }: { dateStr: string | null }) {
  if (!dateStr) return <span class="freshness-none">—</span>;
  // Timezone-safe calendar-day diff
  const [y, m, d] = dateStr.split("-").map(Number) as [number, number, number];
  const priceDate = new Date(Date.UTC(y, m - 1, d));
  const now = new Date();
  const today = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  const diffMs = today.getTime() - priceDate.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  if (diffDays < 1)
    return (
      <span class="freshness fresh-ok" title="Updated today">
        🟢
      </span>
    );
  if (diffDays < 2)
    return (
      <span class="freshness fresh-stale" title="Updated yesterday">
        🟡
      </span>
    );
  return (
    <span
      class="freshness fresh-old"
      title={`No recent data (${Math.floor(diffDays)} days)`}
    >
      🔴
    </span>
  );
}

export function Sparkline({ values }: { values: number[] | null }) {
  if (!values || values.length === 0)
    return <span class="sparkline-muted">—</span>;
  const W = 80;
  const H = 24;
  const min = Math.min.apply(null, values);
  const max = Math.max.apply(null, values);
  const range = max - min || 1;
  const n = values.length;
  const pts = values
    .map((v, i) => {
      const x = (i / (n - 1)) * W;
      const y = H - ((v - min) / range) * H;
      return x.toFixed(1) + "," + y.toFixed(1);
    })
    .join(" ");
  const color =
    (values[n - 1] ?? 0) >= (values[0] ?? 0) ? "#22c55e" : "#ef4444";
  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style="overflow:visible;display:block"
    >
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        stroke-width="1.5"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
    </svg>
  );
}

// ── Row and table components ────────────────────────────────────────────────

function fmtPct(n: number | null): string {
  return n !== null ? (n >= 0 ? "+" : "") + n.toFixed(1) + "%" : "\u2014";
}

function isCrypto(ticker: string): boolean {
  return (
    ticker === "ETH" ||
    ticker === "BTC" ||
    ticker === "SOL" ||
    ticker === "XRP" ||
    ticker === "ADA" ||
    ticker === "DOT"
  );
}

interface PositionRow {
  ticker: string;
  platform: string | null;
  quantity: number;
  avgCost: number;
  currentPrice: number | null;
  currentValue: number | null;
  pnlPct: number | null;
  sparkline: number[] | null;
  stopLevel: string;
  lastPriceDate: string | null;
  invalidationPrice: number | null;
}

function PositionsTableRow({ pos }: { pos: PositionRow }) {
  const pnlClass =
    pos.pnlPct !== null && pos.pnlPct >= 0 ? "pnl-pos" : "pnl-neg";
  const invStr =
    pos.invalidationPrice !== null ? fmtGBP(pos.invalidationPrice) : "\u2014";
  return (
    <tr class={`position-row position-${esc(pos.stopLevel)}`}>
      <td>
        <FreshnessBadge dateStr={pos.lastPriceDate} />
      </td>
      <td class="ticker-cell">
        <span class="ticker">{esc(pos.ticker)}</span>
        {pos.platform ? (
          <span class="platform-tag">{esc(pos.platform)}</span>
        ) : null}
      </td>
      <td>
        <Sparkline values={pos.sparkline} />
      </td>
      <td>{fmt(pos.quantity, isCrypto(pos.ticker) ? 4 : 0)}</td>
      <td class="mono">{fmtGBP(pos.avgCost)}</td>
      <td class="mono" title={`Inv: ${invStr}`}>
        {fmtGBP(pos.currentPrice)}
      </td>
      <td class="mono">{fmtGBP(pos.currentValue)}</td>
      <td class={`mono ${pnlClass}`}>{fmtPct(pos.pnlPct)}</td>
      <td>
        <StopBadge level={pos.stopLevel} />
      </td>
      <td>
        <a
          href={`/analyze?ticker=${pos.ticker}`}
          class="btn-sm"
        >
          Analyze
        </a>
      </td>
    </tr>
  );
}

interface PositionsTableProps {
  positions: PositionRow[];
}

export function PositionsTable({ positions }: PositionsTableProps) {
  if (positions.length === 0) {
    return <div class="muted">No open positions.</div>;
  }

  // Group by platform
  const groups: Record<string, PositionRow[]> = {};
  for (const pos of positions) {
    const key = pos.platform || "unknown";
    if (!groups[key]) groups[key] = [];
    groups[key].push(pos);
  }

  const platformNames = Object.keys(groups).sort();

  return (
    <>
      {platformNames.map((platName) => {
        const items = groups[platName]!;
        return (
          <div class="positions-platform">
            <div class="positions-platform-header">
              {platName} ({items.length})
            </div>
            <table class="data-table positions-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Ticker</th>
                  <th>Sparkline</th>
                  <th>Qty</th>
                  <th>Avg Cost</th>
                  <th>Current</th>
                  <th>Value</th>
                  <th>P&amp;L</th>
                  <th>Stop</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((pos) => (
                  <PositionsTableRow pos={pos} />
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </>
  );
}

// ── HoldingsPage — full page wrapper ────────────────────────────────────────

interface HoldingsData {
  holdings: Array<{
    ticker: string;
    platform: string | null;
    quantity: number | string;
    costBasis: number | string;
    costPerShare: number | string;
    currency: string;
  }>;
  platforms: Array<{
    name: string;
    totalValue: number | string;
    holdingCount: number | string;
    cash: number | string;
  }>;
  cash: Array<{
    platform: string | null;
    currency: string;
    amount: number | string;
  }>;
}

interface PositionsData {
  positions: Array<{
    ticker: string;
    platform: string | null;
    quantity: number;
    avgCost: number;
    currentPrice: number | null;
    currentValue: number | null;
    pnlPct: number | null;
    sparkline: number[] | null;
    stopLevel: string;
    lastPriceDate: string | null;
    invalidationPrice: number | null;
  }>;
}

export function HoldingsPage({ holdingsData, positionsData }: {
  holdingsData?: HoldingsData;
  positionsData?: PositionsData;
}) {

  // Guard: default to empty data (client will fetch or HTMX will refresh)
  holdingsData = holdingsData ?? ({ holdings: [], platforms: [], cash: [] } as HoldingsData);
  positionsData = positionsData ?? ({ positions: [] } as PositionsData);

  // Group holdings by platform
  const holdingsGroups: Record<string, typeof holdingsData.holdings> = {};
  for (const h of holdingsData!.holdings) {
    const key = h.platform || "unknown";
    if (!holdingsGroups[key]) holdingsGroups[key] = [];
    holdingsGroups[key].push(h);
  }

  // Group cash by platform
  const cashGroups: Record<string, typeof holdingsData.cash> = {};
  for (const c of holdingsData!.cash) {
    const key = c.platform || "unknown";
    if (!cashGroups[key]) cashGroups[key] = [];
    cashGroups[key].push(c);
  }

  return (
    <>
      {/* ── Holdings (hLedger) ── */}
      <section class="panel" id="holdings-panel">
        <h3>
          Holdings <span class="muted" style="font-size:0.8em">(base: GBP)</span>
        </h3>
        <div id="holdings-body">
          {holdingsData!.holdings.length === 0 ? (
            <div class="muted">No holdings found. Add transactions to your hLedger journal.</div>
          ) : (
            <div>
              {holdingsData!.platforms && holdingsData!.platforms.length > 0 ? (
                <div class="platform-cards">
                  {holdingsData.platforms.map((p) => (
                    <div class="platform-card">
                      <div class="platform-name">{p.name}</div>
                      <div class="platform-total">{fmtGBP(Number(p.totalValue))}</div>
                      <div class="platform-detail">
                        {Number(p.holdingCount)} holdings · {fmtGBP(Number(p.cash))} cash
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Platform</th>
                    <th>Ticker</th>
                    <th>Qty</th>
                    <th>Cost/Share (GBP)</th>
                    <th>Cost Basis (GBP)</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(holdingsGroups).sort().map((platName) => {
                    const items = holdingsGroups[platName]!;
                    let total: number = 0;
                    const rows = items.map((h2) => {
                      const costGbp = Number(h2.costBasis);
                      total = total + Number(h2.costBasis);
                      return (
                        <tr>
                          <td></td>
                          <td class="ticker">{h2.ticker}</td>
                          <td>{h2.quantity}</td>
                          <td style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">
                            {fmtGBP(Number(h2.costPerShare))}
                          </td>
                          <td style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">
                            {fmtGBP(costGbp)}
                          </td>
                          <td>
                            <a
                              href={`/analyze?ticker=${h2.ticker}`}
                              class="btn-sm"
                            >
                              Analyze
                            </a>
                          </td>
                        </tr>
                      );
                    });
                    return [
                      <tr class="platform-group-header">
                        <td colspan={2}>
                          <strong>{platName}</strong>
                        </td>
                        <td colspan={2} class="muted">{items.length} position(s)</td>
                        <td style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">
                          <strong>{fmtGBP(total as number)}</strong>
                        </td>
                        <td></td>
                      </tr>,
                      ...rows,
                    ];
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* ── Positions with prices + sparklines + stop monitoring ── */}
      <section class="panel" id="positions-panel">
        <h3>
          Positions
          <span class="muted" style="font-size:0.8em"> — live prices from Yahoo Finance</span>
        </h3>
        <div
          id="positions-body"
          hx-get="/api/holdings/positions/html"
          hx-trigger="load,every 60s"
          hx-swap="innerHTML"
        >
          <PositionsTable positions={positionsData!.positions} />
        </div>
      </section>

      {/* ── Cash ── */}
      <section class="panel" id="cash-panel">
        <h3>
          Cash <span class="muted" style="font-size:0.8em">(base: GBP)</span>
        </h3>
        <div id="cash-body">
          {holdingsData.cash.length === 0 ? (
            <div class="muted">No cash balances.</div>
          ) : (
            <table class="data-table">
              <thead>
                <tr>
                  <th>Platform</th>
                  <th>Currency</th>
                  <th>Amount (GBP)</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(cashGroups).sort().map((platName) => {
                  const items = cashGroups[platName]!;
                  let totalGbp: number = 0;
                  const rows = items.map((c2) => {
                    totalGbp += Number(c2.amount);
                    return (
                      <tr>
                        <td></td>
                        <td>{c2.currency}</td>
                        <td style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">
                          {fmtGBP(Number(c2.amount))}
                        </td>
                      </tr>
                    );
                  });
                  return [
                    <tr class="platform-group-header">
                      <td>
                        <strong>{platName}</strong>
                      </td>
                      <td class="muted">{items.length} currency</td>
                      <td style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">
                        <strong>{fmtGBP(totalGbp as number)}</strong>
                      </td>
                    </tr>,
                    ...rows,
                  ];
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

    </>
  )
}

// Alias for backwards compat with index.tsx
export { HoldingsPage as HoldingsView };
