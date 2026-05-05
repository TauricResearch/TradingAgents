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
