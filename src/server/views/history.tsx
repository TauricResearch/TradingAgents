/**
 * History view — shell that loads /api/analyses/html via HTMX (historical analyses list).
 */

/** @jsxImportSource hono/jsx */

export function HistoryView() {
  return (
    <>
      <section class="panel">
        <h3>Past Analyses</h3>
        <div id="history-content">
          <table id="analyses-table">
            <thead>
              <tr><th class="date-col">Date</th><th>Ticker</th><th>Decision</th><th>Platform</th><th></th></tr>
            </thead>
            <tbody
              id="analyses-body"
              hx-get="/api/analyses/list/html"
              hx-target="this"
              hx-trigger="load"
            >
              <tr><td colspan={5} class="muted">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

