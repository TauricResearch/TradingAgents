/**
 * Prospects list HTML — renders watchlist items with fair value, upside %, and signal strength.
 */

/** @jsxImportSource hono/jsx */

import { isStale, STAGES, type Prospect } from "../lib/prospects-db.ts"
import type { CoverageGroup } from "../routes/prospects.tsx"

// ── Helpers ─────────────────────────────────────────────────────────────────────

const PLATFORMS = ["degiero", "ibkr", "pension:nn", "test", "unknown"]

// ── Research Coverage Panel ─────────────────────────────────────────────────────

export function ResearchCoveragePanel({
  groups,
  unlinked,
  total,
}: {
  groups: CoverageGroup[]
  unlinked: CoverageGroup | null
  total: number
}) {
  return (
    <section class="panel coverage-panel" id="coverage-panel">
      <div class="coverage-header">
        <h4>Research Coverage</h4>
        <span class="badge">{total} prospects</span>
      </div>

      <div class="coverage-groups">
        {groups.map((g) => {
          const isStaleGroup = g.stale_count > 0
          return (
            <div class={`coverage-group${isStaleGroup ? " stale-group" : ""}`} key={g.research_doc}>
              <div class="coverage-group-header">
                <span class="coverage-label">
                  {g.label}
                  {isStaleGroup && <span class="stale-indicator" title="Research may be outdated">⚠</span>}
                </span>
                <span class="coverage-count">{g.ticker_count} tickers</span>
                {g.last_update && (
                  <span class="coverage-date">Updated: {g.last_update}</span>
                )}
              </div>
              <div class="coverage-tickers">
                {g.high_count > 0 && (
                  <span class="priority-chip high">{g.high_count} high</span>
                )}
                {g.medium_count > 0 && (
                  <span class="priority-chip medium">{g.medium_count} medium</span>
                )}
                {g.low_count > 0 && (
                  <span class="priority-chip low">{g.low_count} low</span>
                )}
                <span class="ticker-list">{g.tickers.join(", ")}</span>
              </div>
            </div>
          )
        })}

        {unlinked && (
          <div class="coverage-group unlinked-group">
            <div class="coverage-group-header">
              <span class="coverage-label">Unlinked</span>
              <span class="coverage-count">{unlinked.ticker_count} tickers</span>
              <span class="stale-indicator" title="No research doc linked">⚠ stale</span>
            </div>
            <div class="coverage-tickers">
              {unlinked.high_count > 0 && (
                <span class="priority-chip high">{unlinked.high_count} high</span>
              )}
              {unlinked.medium_count > 0 && (
                <span class="priority-chip medium">{unlinked.medium_count} medium</span>
              )}
              {unlinked.low_count > 0 && (
                <span class="priority-chip low">{unlinked.low_count} low</span>
              )}
              <span class="ticker-list">{unlinked.tickers.join(", ")}</span>
            </div>
          </div>
        )}

        {groups.length === 0 && !unlinked && (
          <div class="muted">No research-linked watchlist entries.</div>
        )}
      </div>
    </section>
  )
}

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
  const stale = isStale(item)

  return (
    <div class={`pipeline-card${stale ? " stale" : ""}`} data-id={item.id}>
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
      {item.research_doc && (
        <div class="card-badge">
          <span class="research-badge" title={`Research: ${item.research_doc}`}>
            {item.research_doc.split("-")[1]}
          </span>
          {stale && <span class="stale-badge" title="Research may be outdated">⚠</span>}
        </div>
      )}
      {!item.research_doc && <div class="card-badge"><span class="no-research-badge">unlinked</span></div>}
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
