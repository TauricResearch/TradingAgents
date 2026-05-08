/** @jsxImportSource hono/jsx */

import { STAGES, type Prospect } from "../lib/prospects-data.ts"

// ── Helpers ─────────────────────────────────────────────────────────────────────

const PLATFORMS = ["degiero", "ibkr", "pension:nn", "test", "unknown"]

// ── Pipeline view ─────────────────────────────────────────────────────────────────

export function ProspectsPipeline({
  items,
  selectedPlatform,
}: {
  items: Prospect[]
  selectedPlatform: string
}) {
  const filtered = selectedPlatform
    ? items.filter((item) => item.platform === selectedPlatform)
    : items

  if (filtered.length === 0) {
    return (
      <div class="muted">
        No prospects{selectedPlatform ? ` for ${selectedPlatform}` : ""}. Add tickers above.
      </div>
    )
  }

  const groups: Record<string, Prospect[]> = {}
  for (const s of STAGES) groups[s] = []
  for (const item of filtered) {
    const g = groups[item.stage]
    if (g) g.push(item)
  }

  return (
    <div class="pipeline">
      {STAGES.map((stage) => {
        const stageItems = groups[stage] || []
        if (stageItems.length === 0) return null
        return (
          <div class="pipeline-column" key={stage}>
            <div class="pipeline-header">
              {stage.charAt(0).toUpperCase() + stage.slice(1)}{" "}
              <span class="badge">{stageItems.length}</span>
            </div>
            <div class="pipeline-body">
              {stageItems.map((item) => (
                <ProspectCard item={item} stage={stage} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Filter bar ──────────────────────────────────────────────────────────────────

export function ProspectsFilter({ selectedPlatform }: { selectedPlatform: string }) {
  return (
    <div
      class="form-row"
      style="margin-bottom:0.75rem"
      hx-get="/api/prospects/html"
      hx-target="#pipeline-wrapper"
      hx-trigger="change"
      hx-include="this"
    >
      <h3 style="margin:0">Prospects Pipeline</h3>
      <select name="platform" style="margin-left:auto">
        <option value="">All platforms</option>
        {PLATFORMS.map((p) => (
          <option value={p} selected={p === selectedPlatform}>
            {p === "unknown" ? "Other/Unknown" : p}
          </option>
        ))}
      </select>
    </div>
  )
}

// ── Individual card ─────────────────────────────────────────────────────────────

function ProspectCard({ item, stage }: { item: Prospect; stage: string }) {
  const idx = STAGES.indexOf(stage as (typeof STAGES)[number])
  const nextStage = idx >= 0 && idx < STAGES.length - 1 ? STAGES[idx + 1] : null

  return (
    <div class="pipeline-card" data-id={item.id}>
      <div class="card-title">{item.ticker}</div>
      <div class="card-meta">
        {item.platform && item.platform !== "unknown" && (
          <span class="platform-tag">{item.platform}</span>
        )}
        <span class={`priority-${item.priority || "medium"}`}>
          {item.priority || "medium"}
        </span>
        <span class="signal">{item.last_signal || "\u2014"}</span>
      </div>
      {item.thesis && <div class="card-thesis">{item.thesis}</div>}
      <div class="card-actions">
        {nextStage && (
          <button
            class="btn-sm"
            hx-post={`/api/prospects/${item.id}/stage`}
            hx-target="#pipeline-wrapper"
            hx-swap="innerHTML"
            hx-vals={`{"stage":"${nextStage}"}`}
          >
            →
          </button>
        )}
        <button
          class="btn-sm danger"
          hx-delete={`/api/prospects/${item.id}`}
          hx-target="#pipeline-wrapper"
          hx-swap="innerHTML"
          hx-confirm={`Remove ${item.ticker}?`}
        >
          ✕
        </button>
      </div>
    </div>
  )
}
