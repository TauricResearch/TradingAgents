/** @jsxImportSource hono/jsx */

export function IntelligenceView() {
  return (
    <>
      <section class="panel" id="portfolio-hero">
        <h3>Portfolio Overview</h3>
        <div
          id="intel-body"
          hx-get="/api/portfolio/intelligence/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading portfolio intelligence…</div>
        </div>
      </section>

      <section class="panel" id="balance-update-panel">
        <h3>Update Account Balance</h3>
        <form
          hx-post="/api/portfolio/balance"
          hx-target="#balance-result"
          hx-swap="innerHTML"
        >
          <div class="form-row" style="display:flex;gap:0.5rem;align-items:flex-end">
            <input
              name="account_id"
              type="text"
              placeholder="Account ID (e.g. ig-isa)"
              required
              style="flex:1"
            />
            <input
              name="balance"
              type="number"
              step="0.01"
              placeholder="New balance (£)"
              required
              style="flex:1"
            />
            <input
              name="note"
              placeholder="Note (e.g. 'monthly update')"
              style="flex:2"
            />
            <button type="submit">Update</button>
          </div>
        </form>
        <div id="balance-result" style="margin-top:0.5rem" />
      </section>
    </>
  )
}

