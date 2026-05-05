/** @jsxImportSource hono/jsx */

// Signals view — table of all signals with price history sparklines
// Uses /api/signals/table (signals + price history) for sparkline rendering

export function SignalsView() {
  return (
    <>
      <section class="panel">
        <div class="form-row">
          <select id="signals-platform">
            <option value="">— Platform —</option>
            <option value="degiero">DeGiro</option>
            <option value="ibkr">IBKR</option>
            <option value="pension:nn">Pension (NN)</option>
            <option value="test">Test</option>
            <option value="unknown">Other/Unknown</option>
          </select>
          <select id="signals-ticker">
            <option value="">All tickers</option>
          </select>
        </div>
      </section>

      <section class="panel" id="timeline-panel" style="display:none">
        <h3>Signal Timeline</h3>
        <div id="signal-timeline" />
      </section>

      <section class="panel">
        <div style="overflow-x:auto">
          <table id="signals-table" class="signals-table">
            <thead>
              <tr>
                <th>Platform</th>
                <th class="date-col">Date</th>
                <th>Ticker</th>
                <th>Signal</th>
                <th>Trend</th>
                <th>Conf.</th>
                <th>Reasoning</th>
              </tr>
            </thead>
            <tbody id="signals-body"><tr><td colSpan={7} class="muted">Loading…</td></tr></tbody>
          </table>
        </div>
      </section>

      <script src="/static/scripts/signals.js" />
    </>
  )
}

