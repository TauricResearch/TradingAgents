/** @jsxImportSource hono/jsx */

const STAGES = ["researching", "analyzed", "candidate", "approved"] as const;

export function ProspectsView() {
  return (
    <>
      <section class="panel" id="prospects-panel">
        <div class="form-row" style="margin-bottom:0.75rem">
          <h3 style="margin:0">Prospects Pipeline</h3>
          <select id="prospects-platform" style="margin-left:auto">
            <option value="">All platforms</option>
            <option value="degiero">DeGiro</option>
            <option value="ibkr">IBKR</option>
            <option value="pension:nn">Pension (NN)</option>
            <option value="test">Test</option>
            <option value="unknown">Other/Unknown</option>
          </select>
        </div>
        <div id="pipeline-container">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="add-prospect">
        <h3>Add to Watchlist</h3>
        <form
          id="prospect-form"
          hx-post="/api/prospects"
          hx-swap="none"
          {...{ "hx-on::after-request": "handleProspectSubmit(event)" }}
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
          <div id="prospect-error" class="error-card" style="display:none"></div>
        </form>
      </section>
      <script src="/static/scripts/prospects.js" />
    </>
  );
}
