/** @jsxImportSource hono/jsx */

export function PortfolioView() {
  return (
    <>
      <div
        id="portfolio-wrapper"
        hx-get="/api/portfolio/summary/html"
        hx-target="this"
        hx-trigger="load"
      >
        <div class="muted">Loading…</div>
      </div>

      <section class="panel">
        <h3>Add Position</h3>
        <form
          hx-post="/api/positions"
          hx-target="#portfolio-wrapper"
          hx-swap="innerHTML"
        >
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. AAPL, TKA.DE)" required />
            <select name="exchange">
              <option value="US">USD</option><option value="XETRA">EUR</option>
              <option value="GBP">GBP</option><option value="CRYPTO">CRYPTO</option>
            </select>
            <input name="quantity" type="number" step="0.01" placeholder="Shares" required />
            <input name="avg_cost" type="number" step="0.01" placeholder="Avg Cost (in selected currency)" required />
          </div>
          <div class="form-row">
            <input name="entry_date" type="date" />
            <select name="platform">
              <option value="">— Platform —</option>
              <option value="degiero">DeGiro</option><option value="ibkr">IBKR</option>
              <option value="pension:nn">Pension (NN)</option>
              <option value="test">Test</option><option value="unknown">Other</option>
            </select>
            <button type="submit">Add Position</button>
          </div>
          <div class="form-row">
            <input name="thesis" placeholder="Investment thesis" style="flex:1" />
          </div>
        </form>
      </section>
    </>
  )
}

