/**
 * Analysis report HTML — renders the full multi-agent debate report with agent sections, debate rounds, and decision.
 */

/** @jsxImportSource hono/jsx */

import type { DbAnalysis, AnalysisEvent } from "../lib/analysis-data.ts"
import { fmtDate } from "../lib/analysis-data.ts"
import { renderMarkdown } from "../lib/markdown.ts"
import { escapeHtml, signalClass, extractSignal } from "../routes/analyses-common.ts"

// ── Event section component ───────────────────────────────────────────────────

function EventSection({ event }: { event: AnalysisEvent }) {
  const t = event.type
  const d = event.data

  if (t === "start") {
    return (
      <div class="event-section event-start">
        <h4>Analysis started</h4>
        <p class="muted">{escapeHtml(String(d.date ?? d.timestamp ?? ""))}</p>
      </div>
    )
  }

  if (t === "agent_report") {
    const agent = String(d.agent ?? "Unknown")
    const report = String(d.report ?? "")
    const sectionClass = agent.toLowerCase().replace(/\s+/g, "-")
    return (
      <div class={`event-section agent-report ${sectionClass}`}>
        <h4>{escapeHtml(agent)} Report</h4>
        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(report) }} />
      </div>
    )
  }

  if (t === "debate_round") {
    const round = Number(d.round ?? 0)
    const stance = String(d.stance ?? "")
    const discussion = String(d.discussion ?? "")
    const verdict = String(d.verdict ?? "")
    const cls = signalClass(verdict)
    return (
      <div class="event-section debate-round">
        <h4>
          Debate Round {round}{" "}
          <span class={cls}>({escapeHtml(stance)})</span>
        </h4>
        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(discussion) }} />
        {verdict ? (
          <div class={`verdict ${cls}`}>
            <strong>Verdict:</strong>{" "}
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(verdict) }} />
          </div>
        ) : null}
      </div>
    )
  }

  if (t === "risk_assessment") {
    const severity = String(d.severity ?? "info")
    const content = String(d.content ?? d.assessment ?? "")
    return (
      <div class={`event-section risk-assessment risk-${severity}`}>
        <h4>
          Risk Assessment <span class="risk-badge">{escapeHtml(severity)}</span>
        </h4>
        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
      </div>
    )
  }

  if (t === "decision") {
    const signal = String(d.signal ?? "")
    const confidence = d.confidence != null ? Number(d.confidence) : null
    const rationale = String(d.rationale ?? d.text ?? "")
    const cls = signalClass(signal)
    const confStr =
      confidence != null ? ` (${Math.round(confidence * 100)}% confidence)` : ""
    return (
      <div class={`event-section final-decision ${cls}`}>
        <h4>
          Final Decision{" "}
          <span class={cls}>
            {escapeHtml(signal)}
            {confStr}
          </span>
        </h4>
        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(rationale) }} />
      </div>
    )
  }

  if (t === "complete") {
    return (
      <div class="event-section event-complete">
        <p class="muted">Analysis complete</p>
      </div>
    )
  }

  if (t === "error") {
    const msg = String(d.message ?? "Unknown error")
    return (
      <div class="event-section event-error">
        <h4>Error</h4>
        <p style="color:var(--red)">{escapeHtml(msg)}</p>
      </div>
    )
  }

  return (
    <div class="event-section unknown">
      <h4>{escapeHtml(t)}</h4>
      <pre>{escapeHtml(JSON.stringify(event.data, null, 2))}</pre>
    </div>
  )
}

// ── Analysis report view ──────────────────────────────────────────────────────

export function AnalysisReportView({ row }: { row: DbAnalysis }) {
  const events: AnalysisEvent[] = []
  if (row.raw_state && row.raw_state !== "[]" && row.raw_state !== "") {
    try {
      const parsed = JSON.parse(row.raw_state) as AnalysisEvent[]
      events.push(...parsed)
    } catch {
      // Malformed JSON — skip
    }
  }

  return (
    <div class="panel report-panel">
      <div class="report-body">
        <div class="report-header">
          <h2>{escapeHtml(row.ticker)}</h2>
          <span class="report-date">{escapeHtml(row.date)}</span>
          <span class="report-platform">{escapeHtml(row.platform)}</span>
        </div>

        {row.decision ? (
          <div class={`report-decision ${signalClass(extractSignal(row.decision))}`}>
            <strong>Decision:</strong>{" "}
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(row.decision) }} />
          </div>
        ) : null}

        {events.map((event, i) => (
          <EventSection key={i} event={event} />
        ))}
      </div>
    </div>
  )
}

// ── Analyses list view (table rows for HTMX tbody swap) ──────────────────────

export function AnalysesListView({ rows }: { rows: DbAnalysis[] }) {
  if (!rows || rows.length === 0) {
    return (
      <tr>
        <td colSpan={5} class="muted">
          No analyses yet. Run one from the Analysis tab.
        </td>
      </tr>
    )
  }

  return (
    <>
      {rows.map((r) => {
        const hasRaw = r.raw_state != null && r.raw_state !== "[]" && r.raw_state !== ""
        const decisionShort = r.decision ? r.decision.substring(0, 60) : "\u2014"
        const rowClass = hasRaw ? "has-raw" : "dec-only"
        return (
          <tr class={rowClass}>
            <td class="date-col">{fmtDate(r.date)}</td>
            <td class="ticker">{escapeHtml(r.ticker)}</td>
            <td
              class="muted"
              style="font-size:0.8em;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
              title={escapeHtml(r.decision ?? "")}
            >
              {escapeHtml(decisionShort)}
            </td>
            <td>
              <span class="platform-tag">{escapeHtml(r.platform)}</span>
            </td>
            <td>
              <button
                class="btn-sm"
                hx-get={`/api/analyses/${r.id}/card`}
                hx-target="#history-content"
                hx-swap="innerHTML"
              >
                View
              </button>
            </td>
          </tr>
        )
      })}
    </>
  )
}

// ── Analysis card view (full card with back button) ───────────────────────────

export function AnalysisCardView({ row }: { row: DbAnalysis }) {
  return (
    <div class="analysis-card">
      <button
        class="btn-sm"
        hx-get="/api/analyses/list/html"
        hx-target="#history-content"
        hx-swap="innerHTML"
      >
        ← Back to list
      </button>
      <div class="analysis-report-container">
        <AnalysisReportView row={row} />
      </div>
    </div>
  )
}
