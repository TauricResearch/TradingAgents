/** @jsxImportSource hono/jsx */

export function PortfolioView() {
  return (
    <>
      {/* P&L Summary — fetched client-side from /api/portfolio/summary */}
      <section class="panel" id="pnl-panel">
        <h3>
          <span id="pnl-title">Portfolio Summary</span>
          <span class="muted" id="pnl-loading" style="margin-left:0.75em;font-size:0.8em">Loading…</span>
        </h3>
        <div id="pnl-summary" style="display:none">
          <div class="pnl-totals" style="display:flex;gap:2rem;margin-bottom:1rem;flex-wrap:wrap">
            <div>
              <div class="muted" style="font-size:0.75em">Portfolio Value</div>
              <div id="pnl-total-value" style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">—</div>
            </div>
            <div>
              <div class="muted" style="font-size:0.75em">Total Cost</div>
              <div id="pnl-total-cost" style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">—</div>
            </div>
            <div>
              <div class="muted" style="font-size:0.75em">Unrealised P&amp;L</div>
              <div id="pnl-total-pnl" style="font-size:1.4em;font-family:Datatype,monospace;font-feature-settings:'calt'1,'liga'1">—</div>
            </div>
          </div>
          <p class="muted" style="font-size:0.75em;margin:0">
            Prices in GBP via live FX conversion (GBPEUR, GBPUSD).
            Sorted by P&amp;L descending (worst positions first).
          </p>
        </div>
        <div id="pnl-error" style="display:none;color:var(--red)">Failed to load P&amp;L data</div>
      </section>

      {/* Positions table with live P&L */}
      <section class="panel">
        <h3>Positions</h3>
        <div style="overflow-x:auto">
          <table id="positions-table" class="positions-table">
            <thead>
              <tr>
                <th>Platform</th>
                <th>Ticker</th>
                <th>Qty</th>
                <th>Avg Cost</th>
                <th>Current</th>
                <th>Trend</th>
                <th>Value (GBP)</th>
                <th>P&amp;L</th>
                <th class="date-col">Entry</th>
                <th>Thesis</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="positions-tbody">
              <tr><td colSpan={11} class="muted">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Add position form */}
      <section class="panel">
        <h3>Add Position</h3>
        <form
          hx-post="/api/positions"
          hx-target="#positions-tbody"
          hx-swap="none"
          {...{ "hx-on::after-request": "this.reset(); loadSummary(); loadPositions()" }}
        >
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. AAPL, TKA.DE)" required />
            <select name="exchange">
              <option value="US">USD</option>
              <option value="XETRA">EUR</option>
              <option value="GBP">GBP</option>
              <option value="CRYPTO">CRYPTO</option>
            </select>
            <input name="quantity" type="number" step="0.01" placeholder="Shares" required />
            <input name="avg_cost" type="number" step="0.01" placeholder="Avg Cost (in selected currency)" required />
          </div>
          <div class="form-row">
            <input name="entry_date" type="date" />
            <select name="platform">
              <option value="">— Platform —</option>
              <option value="degiero">DeGiro</option>
              <option value="ibkr">IBKR</option>
              <option value="pension:nn">Pension (NN)</option>
              <option value="test">Test</option>
              <option value="unknown">Other</option>
            </select>
            <button type="submit">Add Position</button>
          </div>
          <div class="form-row">
            <input name="thesis" placeholder="Investment thesis" style="flex:1" />
          </div>
        </form>
      </section>

      <script src="/static/scripts/portfolio.js" />
    </>
  )
}
