/** Screening dashboard — curates watchlist candidates via screening rules. */

/** @jsxImportSource hono/jsx */

import { screeningsRouter } from "../routes/screenings.tsx"
import { listScreeningRules } from "../lib/screening-data.ts"

// ── Screening View ────────────────────────────────────────────────────────────

export function ScreeningsView() {
  return (
    <div class="screenings-page">
      <div class="page-header">
        <h2>Screening</h2>
        <div class="header-actions">
          <a href="/api/screenings/results/html" hx-boost="true" hx-target="#screening-results" hx-swap="innerHTML" class="btn">
            Refresh Results
          </a>
          <a href="/api/screenings/shock/html" hx-boost="true" hx-target="#shock-stocks" hx-swap="innerHTML" class="btn">
            Refresh Shock Stocks
          </a>
        </div>
      </div>

      {/* Rules Summary */}
      <div class="rules-summary">
        <h3>Active Rules</h3>
        <p class="info-text">
          Manage rules via CLI: <code>trading screen create</code> | <code>list</code> | <code>delete</code>
        </p>
      </div>

      {/* Screening Results */}
      <div id="screening-results">
        <div hx-get="/api/screenings/results/html" hx-trigger="load" hx-swap="innerHTML" />
      </div>

      {/* Shock Stocks */}
      <div id="shock-stocks">
        <div hx-get="/api/screenings/shock/html" hx-trigger="load" hx-swap="innerHTML" />
      </div>

      {/* Screening History */}
      <div id="screening-history">
        <div hx-get="/api/screenings/history/html" hx-trigger="load" hx-swap="innerHTML" />
      </div>
    </div>
  )
}

