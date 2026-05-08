/** @jsxImportSource hono/jsx */

import type {
  ExitPlanData,
  WorkflowApprovedItem,
  WorkflowData,
  WorkflowHoldingItem,
  WorkflowPendingExitItem,
} from "../lib/workflow-data.ts"

// ── Stage definitions ───────────────────────────────────────────────────────

const STAGES_DEF = [
  { id: "approved", label: "Approved", color: "#3b82f6", icon: "\u25C7" },
  { id: "holdings", label: "Holdings", color: "#22c55e", icon: "\u25C6" },
  { id: "pendingExit", label: "Pending Exit", color: "#f59e0b", icon: "\u26A0" },
] as const

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtDate(d: string): string {
  if (!d) return "\u2014"
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ]
  const parts = d.split("-")
  if (parts.length !== 3) return d
  const [year, month, day] = parts as [string, string, string]
  return parseInt(day, 10) + (months[parseInt(month, 10) - 1] ?? "") + year.slice(2)
}

// ── Card components (stage-specific) ────────────────────────────────────────

function ApprovedCard({ item }: { item: WorkflowApprovedItem }) {
  return (
    <>
      <div class="card-meta">
        Entry &pound;{item.avgCost.toFixed(2)} &middot; {item.quantity} shares
      </div>
      <div class="card-meta muted">{fmtDate(item.entryDate)}</div>
      {item.thesis && <div class="card-thesis">{item.thesis}</div>}
      <div class="entry-process">
        <div class="process-row">
          <span class="process-dot" style="background:#6b7280">1</span>
          <span>AI analysis &amp; signal</span>
        </div>
        <div class="process-row">
          <span class="process-dot" style="background:#6b7280">2</span>
          <span>Position size: {item.quantity} shares</span>
        </div>
        <div class="process-row">
          <span class="process-dot" style="background:#6b7280">3</span>
          <span>Entry: &euro;{item.avgCost.toFixed(2)}</span>
        </div>
        <div class="process-row">
          <span class="process-dot" style="background:#ef4444">4</span>
          <span>Define exit plan before entry</span>
        </div>
      </div>
      <div class="card-actions">
        <a href={`/analyze?ticker=${item.ticker}`} class="btn-sm">Analyze</a>
        <a href="/exits" class="btn-sm">+ Exit Plan</a>
      </div>
    </>
  )
}

function HoldingCard({ item }: { item: WorkflowHoldingItem }) {
  const ep = item.exitPlan
  return (
    <>
      <div class="card-meta">
        Entry &pound;{ep.entryPrice.toFixed(2)} &middot; Stop &pound;{ep.invalidationPrice.toFixed(2)}
      </div>
      {ep.timeStopDaysLeft !== undefined && (
        <div class="card-meta muted">{ep.timeStopDaysLeft}d to time stop</div>
      )}
      <div class="card-actions">
        <a href={`/analyze?ticker=${item.ticker}`} class="btn-sm">Analyze</a>
        <button
          class="btn-sm"
          hx-delete={`/api/workflow/close/${item.id}`}
          hx-target="#workflow-wrapper"
          hx-swap="innerHTML"
          hx-confirm="Close this position?"
        >
          Close
        </button>
      </div>
    </>
  )
}

function PendingExitCard({ item }: { item: WorkflowPendingExitItem }) {
  const ep = item.exitPlan
  const targets = ep.targets as Array<{ label?: string }>

  return (
    <>
      <div class="exit-strategy">
        <div class="process-row">
          <span class="process-dot" style="background:#ef4444">Stop</span>
          <span>
            &pound;{ep.invalidationPrice.toFixed(2)} ({ep.distanceToStopPct.toFixed(0)}%)
          </span>
        </div>
        {targets.map((tp, ti) => {
          const isHit = ti < ep.targetsHit
          const label = tp.label || `Target ${ti + 1}`
          return (
            <div class="process-row" key={ti}>
              <span class={`process-dot ${isHit ? "hit" : "pending"}`}>
                {isHit ? "\u2713" : ti + 1}
              </span>
              <span>{label}</span>
            </div>
          )
        })}
        {ep.timeStopDaysLeft !== undefined && ep.timeStopDaysLeft !== null && (
          <div class="process-row">
            <span class={`process-dot ${ep.timeStopDaysLeft < 30 ? "warning" : "pending"}`}>
              ⏱
            </span>
            <span>Time stop in {ep.timeStopDaysLeft}d</span>
          </div>
        )}
      </div>

      {ep.distanceToStopPct > 0 && ep.distanceToStopPct < 10 && (
        <span class="urgency-badge" style="background:#ef4444">
          ⚠ Near stop
        </span>
      )}
      {ep.distanceToStopPct >= 10 && ep.distanceToStopPct < 15 && (
        <span class="urgency-badge" style="background:#f59e0b">
          ⚠ Watch
        </span>
      )}
      {ep.targetsHit > 0 && (
        <span class="urgency-badge" style="background:#22c55e">
          ✓ {ep.targetsHit}/{targets.length} hit
        </span>
      )}
      {ep.timeStopDaysLeft !== undefined && ep.timeStopDaysLeft !== null && ep.timeStopDaysLeft < 30 && (
        <span class="urgency-badge" style="background:#ef4444">
          ⏱ {ep.timeStopDaysLeft}d
        </span>
      )}

      <div class="card-actions">
        <a href={`/analyze?ticker=${item.ticker}`} class="btn-sm">Review</a>
        <button
          class="btn-sm"
          hx-delete={`/api/workflow/close/${item.id}`}
          hx-target="#workflow-wrapper"
          hx-swap="innerHTML"
          hx-confirm="Close this position?"
        >
          Close
        </button>
      </div>
    </>
  )
}

function WorkflowCard({
  item,
  stageId,
}: {
  item: WorkflowApprovedItem | WorkflowHoldingItem | WorkflowPendingExitItem
  stageId: string
}) {
  const plat = item.platform && item.platform !== "unknown" ? item.platform : null

  return (
    <div class="workflow-card">
      <div class="card-header">
        <span class="card-ticker">{item.ticker}</span>
        {plat && <span class="platform-tag">{plat}</span>}
      </div>
      {stageId === "approved" && <ApprovedCard item={item as WorkflowApprovedItem} />}
      {stageId === "holdings" && <HoldingCard item={item as WorkflowHoldingItem} />}
      {stageId === "pendingExit" && <PendingExitCard item={item as WorkflowPendingExitItem} />}
    </div>
  )
}

// ── Main Kanban ─────────────────────────────────────────────────────────────

export function WorkflowKanban({ data }: { data: WorkflowData }) {
  if (data.note) {
    return <div class="muted" style="margin-bottom:1rem">{data.note}</div>
  }

  return (
    <div class="workflow">
      {STAGES_DEF.map((stage) => {
        const items = (data as unknown as Record<string, unknown[]>)[stage.id] || []
        return (
          <div class="workflow-col" key={stage.id}>
            <div class="workflow-header" style={`border-top-color:${stage.color}`}>
              <span style={`color:${stage.color}`}>{stage.icon}</span> {stage.label}{" "}
              <span class="badge" style={`background:${stage.color}`}>
                {items.length}
              </span>
            </div>
            <div class="workflow-body">
              {items.length === 0 ? (
                <div class="workflow-empty">—</div>
              ) : (
                items.map((item) => (
                  <WorkflowCard
                    item={item as WorkflowApprovedItem}
                    stageId={stage.id}
                  />
                ))
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
