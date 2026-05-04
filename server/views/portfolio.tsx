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

      <script dangerouslySetInnerHTML={{ __html: portfolioScript() }} />
    </>
  )
}

// ── Client-side script ────────────────────────────────────────────────────────

function portfolioScript(): string {
  return `
function _esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');
}
function _cls(pnl) {
  if (pnl == null) return '';
  if (pnl > 0) return 'positive';
  if (pnl < 0) return 'negative';
  return '';
}
function _fmt(n, dec) {
  if (n == null) return '—';
  return n.toFixed(dec != null ? dec : 2);
}
function _fmtPnl(pnl) {
  if (pnl == null) return '—';
  var sign = pnl >= 0 ? '+' : '';
  return sign + _fmt(pnl, 2);
}
function _fmtDate(d) {
  if (!d) return '—';
  var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var parts = d.split('-');
  if (parts.length !== 3) return d;
  return parseInt(parts[2],10) + '-' + months[parseInt(parts[1],10)-1];
}
function _norm(vals) {
  if (!vals || vals.length === 0) return [];
  var lo = Math.min.apply(null, vals);
  var hi = Math.max.apply(null, vals);
  var rng = hi - lo;
  if (rng === 0) return vals.map(function() { return 50; });
  return vals.map(function(v) { return Math.round(((v - lo) / rng) * 100); });
}
function _sparkline(priceHistory) {
  if (!priceHistory || priceHistory.length === 0) return null;
  var closes = priceHistory.slice(-20).map(function(h) { return h.close; }).reverse();
  var norm = _norm(closes);
  return norm.length > 0 ? '{l:' + norm.join(',') + '}' : null;
}

function loadSummary() {
  var loading = document.getElementById('pnl-loading');
  var summary = document.getElementById('pnl-summary');
  var error = document.getElementById('pnl-error');
  if (!loading) return;
  loading.style.display = '';
  if (summary) summary.style.display = 'none';
  if (error) error.style.display = 'none';

  fetch('/api/portfolio/summary')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      loading.style.display = 'none';
      if (summary) summary.style.display = '';

      var tot = data.totals;
      var pnl = tot.total_pnl_gbp;
      var pnlCls = _cls(pnl);

      var valEl = document.getElementById('pnl-total-value');
      var costEl = document.getElementById('pnl-total-cost');
      var pnlEl = document.getElementById('pnl-total-pnl');
      if (valEl) valEl.textContent = '\\u00a3' + _fmt(tot.portfolio_value_gbp);
      if (costEl) costEl.textContent = '\\u00a3' + _fmt(tot.total_cost_gbp);
      if (pnlEl) {
        pnlEl.textContent = '\\u00a3' + _fmtPnl(pnl) + ' (' + (tot.total_pnl_pct != null ? (pnl >= 0 ? '+' : '') + _fmt(tot.total_pnl_pct) + '%' : '—') + ')';
        pnlEl.className = pnlCls ? 'pnl-cell ' + pnlCls : '';
      }

      // Update positions table with enriched data
      updatePositionsTable(data.positions);
    })
    .catch(function() {
      loading.style.display = 'none';
      if (error) error.style.display = '';
    });
}

function updatePositionsTable(positions) {
  var tbody = document.getElementById('positions-tbody');
  if (!tbody) return;
  if (!positions || positions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" class="muted">No open positions</td></tr>';
    return;
  }
  tbody.innerHTML = positions.map(function(p) {
    var pnl = p.pnl_gbp;
    var pnlPct = p.pnl_pct;
    var pnlCls = _cls(pnl);
    var pnlPctStr = pnlPct != null ? _fmt(pnlPct) + '%' : null;
    var pnlStr = pnl != null
      ? _fmtPnl(pnl) + (pnlPctStr ? ' (' + (pnl >= 0 ? '+' : '') + pnlPctStr + ')' : '')
      : '—';
    var curPrice = p.current_price_gbp != null ? '\\u00a3' + _fmt(p.current_price_gbp) : '—';
    var curVal = p.current_value_gbp != null ? '\\u00a3' + _fmt(p.current_value_gbp) : '—';
    return '<tr>' +
      '<td><span class="platform-tag">' + _esc(p.platform) + '</span></td>' +
      '<td class="ticker">' + _esc(p.ticker) + '</td>' +
      '<td>' + _fmt(p.quantity) + '</td>' +
      '<td>\\u00a3' + _fmt(p.avg_cost) + '</td>' +
      '<td style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">' + curPrice + '</td>' +
      '<td style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">' + curVal + '</td>' +
      '<td class="pnl-cell ' + pnlCls + '" style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">' + pnlStr + '</td>' +
      '<td class="date-col">' + _fmtDate(p.entry_date) + '</td>' +
      '<td>' + (_esc(p.thesis) || '—') + '</td>' +
      '<td><button class="btn-sm" hx-delete="/api/positions/' + p.id + '" ' +
      'hx-target="#positions-tbody" hx-swap="none" ' +
      'hx-on::after-request="loadSummary();loadPositions()">Close</button></td>' +
    '</tr>';
  }).join('');
  if (window.htmx) htmx.process(tbody);
}

function loadPositions() {
  // Positions are now loaded via loadSummary() which calls updatePositionsTable.
  // Keep this for the add-position form hx-post callback fallback.
  var tbody = document.getElementById('positions-tbody');
  if (!tbody) return;
  // Don't overwrite — loadSummary handles it
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadSummary);
} else {
  loadSummary();
}
`;
}