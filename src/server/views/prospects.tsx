/**
 * Prospects view — shell that loads /api/prospects/html via HTMX.
 */

/** @jsxImportSource hono/jsx */

export function ProspectsView() {
  return (
    <>
      <section class="panel" id="prospects-panel">
        <div
          id="pipeline-wrapper"
          hx-get="/api/prospects/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="add-prospect">
        <h3>Add to Watchlist</h3>
        <form
          id="prospect-form"
          hx-post="/api/prospects"
          hx-target="#pipeline-wrapper"
          hx-swap="innerHTML"
          {...{ "hx-on::after-request": "this.reset()" }}
        >
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. AAPL)" required />
            <input name="exchange" placeholder="Exchange" value="US" />
            <select name="platform">
              <option value="">— Platform —</option>
              <option value="degiero">DeGiro</option>
              <option value="ibkr">IBKR</option>
              <option value="pension:nn">Pension (NN)</option>
              <option value="test">Test</option>
              <option value="unknown">Other</option>
            </select>
          </div>
          <div class="form-row">
            <select name="priority">
              <option value="high">High</option>
              <option value="medium" selected>Medium</option>
              <option value="low">Low</option>
            </select>
            <input name="thesis" placeholder="Investment thesis" />
            <button type="submit" class="btn">Add</button>
          </div>
        </form>
      </section>
    </>
  )
}

