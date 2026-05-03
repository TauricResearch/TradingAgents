/** @jsxImportSource hono/jsx */

export function PortfolioView() {
  return (
    <>
      <section class="panel">
        <h3>Add Position</h3>
        <form
          hx-post="/api/positions"
          hx-target="#positions-tbody"
          hx-swap="none"
          {...{ "hx-on::after-request": "this.reset(); loadPositions()" }}
        >
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. AAPL, TKA.DE)" required />
            <select name="exchange">
              <option value="US">US</option>
              <option value="XETRA">XETRA</option>
              <option value="EUR">EUR</option>
              <option value="CRYPTO">CRYPTO</option>
            </select>
            <input name="quantity" type="number" step="0.01" placeholder="Shares" required />
            <input name="avg_cost" type="number" step="0.01" placeholder="Avg Cost (€)" required />
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

      <section class="panel">
        <h3>Positions</h3>
        <table id="positions-table">
          <thead>
            <tr>
              <th>Platform</th>
              <th>Ticker</th>
              <th>Shares</th>
              <th>Avg Cost</th>
              <th class="date-col">Entry</th>
              <th>Thesis</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="positions-tbody">
            <tr><td colSpan={7} class="muted">Loading…</td></tr>
          </tbody>
        </table>
      </section>

      <script dangerouslySetInnerHTML={{ __html: positionsScript() }} />
    </>
  );
}

function positionsScript(): string {
  return `
function loadPositions() {
  var tbody = document.getElementById('positions-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" class="muted">Loading…</td></tr>';
  fetch('/api/positions')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!Array.isArray(data) || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="muted">No open positions</td></tr>';
        return;
      }
      var _fmt = function(d) {
        if (!d) return '—';
        var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        var parts = d.split('-');
        if (parts.length !== 3) return d;
        return parseInt(parts[2], 10) + months[parseInt(parts[1], 10) - 1] + parts[0].slice(2);
      };
      tbody.innerHTML = data.map(function(p) {
        var platform = p.platform || 'unknown';
        return '<tr>' +
          '<td><span class="platform-tag">' + platform + '</span></td>' +
          '<td class="ticker">' + p.ticker + '</td>' +
          '<td>' + p.quantity + '</td>' +
          '<td>€' + p.avg_cost.toFixed(2) + '</td>' +
          '<td class="date-col">' + _fmt(p.entry_date) + '</td>' +
          '<td>' + (p.thesis || '—') + '</td>' +
          '<td><button class="btn-sm" hx-delete="/api/positions/' + p.id + '" ' +
          'hx-target="#positions-tbody" hx-swap="none" ' +
          'hx-on::after-request="loadPositions()">Close</button></td>' +
        '</tr>';
      }).join('');
      if (window.htmx) htmx.process(tbody);
    })
    .catch(function(e) {
      tbody.innerHTML = '<tr><td colspan="7" class="muted">Failed to load positions</td></tr>';
    });
}

// Load on page ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadPositions);
} else {
  loadPositions();
}
`;
}