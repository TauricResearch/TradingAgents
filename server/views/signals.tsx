/** @jsxImportSource hono/jsx */

export function SignalsView() {
  return (
    <>
      <section class="panel" id="signals-panel">
        <h3>Signal History</h3>
        <div class="form-row" style="margin-bottom:0.5rem">
          <select id="signals-platform" style="max-width:150px">
            <option value="">All platforms</option>
          </select>
          <select id="signals-ticker" style="max-width:150px">
            <option value="">All tickers</option>
          </select>
        </div>
        <table id="signals-table">
          <thead>
            <tr>
              <th>Platform</th><th>Date</th><th>Ticker</th><th>Signal</th>
              <th>Trend</th><th>Confidence</th><th>Reasoning</th>
            </tr>
          </thead>
          <tbody id="signals-body">
            <tr><td colspan={7} class="muted">Loading…</td></tr>
          </tbody>
        </table>
      </section>

      <section class="panel" id="timeline-panel" style="display:none">
        <h4>Timeline: <span id="timeline-ticker"></span></h4>
        <div id="signal-timeline"></div>
      </section>

      <script src="/static/scripts/signals.js" />
    </>
  );
}

