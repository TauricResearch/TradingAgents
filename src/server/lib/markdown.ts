/**
 * Server-side Markdown renderer for TradingAgents analysis reports.
 * Uses `marked` to convert MD → HTML. No build step needed.
 */
import { marked } from "marked"

/**
 * Render a markdown string to safe HTML.
 * Strips script tags and event handlers.
 */
export function renderMarkdown(md: string): string {
  const html = marked.parse(md, { async: false }) as string
  return sanitize(html)
}

/**
 * Minimal XSS sanitizer — strips <script>, javascript:, and event handlers.
 * Not a replacement for a full sanitizer, but sufficient for TA output
 * (which is LLM-generated, not user input).
 */
function sanitize(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/javascript\s*:/gi, "")
    .replace(/\bon\w+\s*=/gi, "")
}

/**
 * Render an analysis state object into a single HTML report.
 * Expects the shape written by TradingAgentsGraph._log_state().
 */
export function renderAnalysisReport(state: Record<string, unknown>): string {
  const sections: string[] = []

  // Title
  const ticker = state.company_of_interest ?? "Unknown"
  const date = state.trade_date ?? "unknown date"
  sections.push(`# ${ticker} — Analysis for ${date}\n`)

  // Analyst reports (all markdown strings)
  for (const [key, value] of Object.entries(state)) {
    if (key === "investment_debate_state" && typeof value === "object" && value !== null) {
      const debate = value as Record<string, unknown>
      if (debate.final_decision) {
        sections.push(`## Investment Debate\n`)
        sections.push(String(debate.final_decision))
      }
      if (Array.isArray(debate.history)) {
        sections.push(`\n### Debate Rounds\n`)
        for (const [i, round] of debate.history.entries()) {
          sections.push(`#### Round ${i + 1}\n`)
          sections.push(typeof round === "string" ? round : JSON.stringify(round))
        }
      }
      continue
    }

    if (typeof value === "string" && value.length > 0 && key.endsWith("_report")) {
      const title = key
        .replace("_report", "")
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase())
      sections.push(`## ${title}\n`)
      sections.push(value)
    }
  }

  // Final trade decision
  if (typeof state.final_trade_decision === "string") {
    sections.push(`\n## Final Decision\n`)
    sections.push(state.final_trade_decision)
  }

  return renderMarkdown(sections.join("\n\n---\n\n"))
}
