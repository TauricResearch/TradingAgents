/**
 * Exit list HTML — renders position exit plans with status, target, stop, and rationale.
 */

/** @jsxImportSource hono/jsx */

import type { ExitStatus } from "../lib/exits-data.ts"

// ── Individual card ─────────────────────────────────────────────────────────

function ExitCard({ status }: { status: ExitStatus }) {
  const p = status.plan
  const isWarn = status.distanceToStopPct < 10
  const pnlColor = isWarn ? "#1a1a2e" : status.pnlPct >= 0 ? "var(--green)" : "var(--red)"

  const stopPrice = p.invalidation?.price ?? p.invalidation_price ?? 0

  const cardStyle = isWarn
    ? "background:#fff3cd;color:#1a1a2e"
    : undefined

  return (
    <div class="exit-card" style={cardStyle}>
      <div class="exit-header">
        <span class="ticker">{p.ticker}</span>
        {p.platform && p.platform !== "unknown" && (
          <span class="platform-tag">{p.platform}</span>
        )}
        <span class="pnl" style={`color:${pnlColor}`}>
          {status.pnlPct >= 0 ? "+" : ""}
          {status.pnlPct.toFixed(1)}%
        </span>
      </div>

      <div class="exit-details">
        <div>
          <strong>Thesis:</strong> {p.thesis || "\u2014"}
        </div>
        <div>
          <strong>Entry:</strong> {p.quantity} @ &pound;{p.entry_price.toFixed(2)}{" "}
          <span class="muted">(GBP)</span>
        </div>

        <div>
          <strong>Stop:</strong> &pound;{stopPrice.toFixed(2)}{" "}
          <span class="muted">(GBP)</span>
          {status.distanceToStopPct !== undefined && (
            <span> ({status.distanceToStopPct.toFixed(1)}% away)</span>
          )}
        </div>

        {p.targets && p.targets.length > 0 && (
          <div>
            <strong>Targets:</strong> {status.targetsHit}/{p.targets.length} hit
            {status.nextTarget && (
              <span>
                {" "}&rarr; next &pound;{status.nextTarget.price.toFixed(2)}{" "}
                <span class="muted">(GBP)</span>
                {status.distanceToTargetPct !== undefined && (
                  <span> ({status.distanceToTargetPct.toFixed(1)}% away)</span>
                )}
              </span>
            )}
          </div>
        )}

        {status.timeStopDaysLeft !== undefined && (
          <div>
            <strong>Time stop:</strong> {status.timeStopDaysLeft} days left
            {status.timeStopDaysLeft < 30 ? " \u26a0\ufe0f" : ""}
          </div>
        )}

        <div>
          <strong>Invalidation:</strong> {p.invalidation?.thesis ?? p.invalidation_thesis ?? "\u2014"}
        </div>

        {p.notes && <div class="notes">{p.notes}</div>}
      </div>
    </div>
  )
}

// ── Main list ─────────────────────────────────────────────────────────────────

export function ExitList({ statuses }: { statuses: ExitStatus[] }) {
  if (!statuses || statuses.length === 0) {
    return (
      <div class="muted">
        No exit plans. Create YAML files in ~/.tradingagents/positions/
      </div>
    )
  }

  return (
    <>
      {statuses.map((status) => (
        <ExitCard status={status} />
      ))}
    </>
  )
}
