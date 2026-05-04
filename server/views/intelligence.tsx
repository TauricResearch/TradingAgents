/** @jsxImportSource hono/jsx */

export function IntelligenceView() {
  return (
    <>
      <section class="panel" id="portfolio-hero">
        <div id="intel-loading" style="color:var(--text-dim)">Loading portfolio intelligence…</div>
        <div id="intel-body" style="display:none" />
      </section>

      <section class="panel" id="asset-class-panel">
        <h3>Asset Allocation</h3>
        <div id="asset-class-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="platforms-panel">
        <h3>Platform Breakdown</h3>
        <div id="platforms-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="governance-panel">
        <h3>Governance Alerts</h3>
        <div id="governance-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: intelligenceScript() }} />
    </>
  )
}

function intelligenceScript(): string {
  return `
function _esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');
}
function _cls(n) {
  if (n == null) return '';
  if (n > 0) return 'positive';
  if (n < 0) return 'negative';
  return '';
}
function _fmt(n, dec) {
  if (n == null) return '—';
  return n.toFixed(dec != null ? dec : 2);
}
function _bar(vals, total) {
  if (!vals || total <= 0) return '';
  var bars = vals.map(function(v) {
    var w = Math.round((v.value_gbp / total) * 100);
    var color = v.assetClass === 'cash' ? '#3b82f6' :
                v.assetClass === 'equity' ? '#22c55e' :
                v.assetClass === 'etf' ? '#eab308' :
                v.assetClass === 'crypto' ? '#ef4444' : '#71717a';
    return '<div style="display:inline-block;height:16px;width:' + w + '%;background:' + color + ';margin-right:2px" title="' + v.assetClass + ': ' + w + '% (' + v.value_gbp.toFixed(0) + ' GBP)"></div>';
  });
  return bars.join('') + '<div style="margin-top:4px;font-size:0.75em;color:var(--text-dim)">' +
    vals.map(function(v) {
      var w = Math.round((v.value_gbp / total) * 100);
      return '<span style="margin-right:12px"><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:' +
        (v.assetClass === 'cash' ? '#3b82f6' :
         v.assetClass === 'equity' ? '#22c55e' :
         v.assetClass === 'etf' ? '#eab308' :
         v.assetClass === 'crypto' ? '#ef4444' : '#71717a') + ';vertical-align:middle;margin-right:4px"></span>' +
        v.assetClass + ' ' + w + '% (' + v.value_gbp.toFixed(0) + ')</span>';
    }).join('') + '</div>';
}

function renderIntel(data) {
  var loading = document.getElementById('intel-loading');
  var body = document.getElementById('intel-body');
  if (loading) loading.style.display = 'none';
  if (body) body.style.display = '';

  var pf = data.portfolio || {};
  var fx = data.fx_rates || {};
  var total = pf.total_value_gbp || 0;
  var pnl = (pf.position_value_gbp || 0) - (pf.total_value_gbp - pf.position_value_gbp - pf.cash_gbp);
  var pnlPct = pf.cash_pct != null ? (100 - pf.cash_pct > 0 ? (pnl / pf.total_value_gbp * 100) : 0) : 0;

  var html = '';

  // Data quality warning for negative cash
  if (pf.cash_negative) {
    html += '<div class="banner" style="margin-bottom:1rem">';
    html += '\u26a0\ufe0f hledger cash is negative \u2014 more sells recorded than buys in journal. Total and % figures may be misleading until hledger cash is corrected.';
    html += '</div>';
  }

  // Hero row
  html += '<div class="intel-hero">';
  html += '<div class="intel-stat"><div class="intel-label">Total Portfolio</div><div class="intel-value">\\u00a3' + _fmt(total) + '</div></div>';
  html += '<div class="intel-stat"><div class="intel-label">Cash</div><div class="intel-value' + (pf.cash_negative ? ' negative' : '') + '">\\u00a3' + _fmt(pf.cash_gbp) + '<span class="intel-pct"> (' + _fmt(pf.cash_pct_raw) + '%)</span></div></div>';
  html += '<div class="intel-stat"><div class="intel-label">Positions</div><div class="intel-value">' + pf.positions_count + '</div></div>';
  html += '<div class="intel-stat"><div class="intel-label">Live Value</div><div class="intel-value">\\u00a3' + _fmt(pf.position_value_gbp) + '</div></div>';
  html += '</div>';

  // FX rates
  html += '<div class="intel-fx">';
  if (fx.GBPEUR) html += '<span>GBPEUR: ' + fx.GBPEUR.toFixed(4) + '</span>';
  if (fx.GBPUSD) html += '<span>GBPUSD: ' + fx.GBPUSD.toFixed(4) + '</span>';
  html += '</div>';

  body.innerHTML = html;
}

function renderAssetClasses(data) {
  var el = document.getElementById('asset-class-body');
  if (!data || !data.asset_classes || data.asset_classes.length === 0) {
    el.innerHTML = '<div class="muted">No allocation data</div>';
    return;
  }
  var total = (data.portfolio && data.portfolio.total_value_gbp) || 1;
  el.innerHTML = '<div class="allocation-bar">' + _bar(data.asset_classes, total) + '</div>';
}

function renderPlatforms(data) {
  var el = document.getElementById('platforms-body');
  if (!data || !data.platforms || data.platforms.length === 0) {
    el.innerHTML = '<div class="muted">No platform data</div>';
    return;
  }

  var total = (data.portfolio && data.portfolio.total_value_gbp) || 1;
  var html = '<table class="data-table"><thead><tr>';
  html += '<th>Platform</th><th>Total Value</th><th>Weight</th><th>Cash</th><th>Positions</th>';
  html += '</tr></thead><tbody>';

  for (var pi = 0; pi < data.platforms.length; pi++) {
    var p = data.platforms[pi];
    var posList = p.positions || [];
    var posValue = p.position_value_gbp || 0;
    var cashValue = p.cash_gbp || 0;

    html += '<tr>';
    html += '<td><span class="platform-tag">' + _esc(p.platform) + '</span></td>';
    html += '<td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1">\\u00a3' + _fmt(p.total_value_gbp) + '</td>';
    html += '<td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1">' + _fmt(p.weight_pct) + '%</td>';
    html += '<td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1">\\u00a3' + _fmt(cashValue) + ' <span class="muted">(' + _fmt(p.cash_pct) + '%)</span></td>';
    html += '<td>';
    for (var ji = 0; ji < posList.length; ji++) {
      var pos = posList[ji];
      var pnl = pos.pnl_pct;
      var pnlCls = _cls(pnl);
      var pnlStr = pnl != null ? (pnl >= 0 ? '+' : '') + _fmt(pnl) + '%' : '';
      html += '<span class="position-pill">' + _esc(pos.ticker) + ' <span class="' + pnlCls + '">' + pnlStr + '</span></span>';
    }
    html += '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

function renderGovernance(data) {
  var el = document.getElementById('governance-body');
  if (!data || !data.governance) {
    el.innerHTML = '<div class="muted">No governance data</div>';
    return;
  }

  var gov = data.governance;
  var html = '';

  if (gov.violations && gov.violations.length > 0) {
    html += '<h4>\\u26a0\\ufe0f Violations</h4>';
    for (var vi = 0; vi < gov.violations.length; vi++) {
      var v = gov.violations[vi];
      var cls = v.severity === 'breach' ? 'violation-breach' : 'violation-warn';
      html += '<div class="' + cls + '">';
      html += '<strong>' + v.rule.name + '</strong>: ' + v.detail;
      html += '</div>';
    }
  } else {
    html += '<div class="ok">\\u2705 All rules satisfied</div>';
  }

  if (gov.suggestions && gov.suggestions.length > 0) {
    html += '<h4 style="margin-top:1rem">Rebalance Suggestions</h4>';
    html += '<table class="data-table" style="font-size:0.85em"><thead><tr>';
    html += '<th>Ticker</th><th>Action</th><th>Current</th><th>Target</th><th>Drift</th>';
    html += '</tr></thead><tbody>';
    for (var si = 0; si < gov.suggestions.length; si++) {
      var s = gov.suggestions[si];
      html += '<tr>';
      html += '<td class="ticker">' + s.ticker + '</td>';
      html += '<td class="' + (s.action === 'trim' ? 'negative' : 'positive') + '">' + s.action.toUpperCase() + '</td>';
      html += '<td>' + _fmt(s.currentWeight) + '%</td>';
      html += '<td>' + _fmt(s.targetWeight) + '%</td>';
      html += '<td>' + _fmt(s.delta) + 'pp</td>';
      html += '</tr>';
    }
    html += '</tbody></table>';
  }

  el.innerHTML = html;
}

fetch('/api/portfolio/intelligence')
  .then(function(r) { return r.json(); })
  .then(function(data) {
    renderIntel(data);
    renderAssetClasses(data);
    renderPlatforms(data);
    renderGovernance(data);
  })
  .catch(function(err) {
    document.getElementById('intel-body').innerHTML =
      '<div class="error-card"><strong>Intelligence error</strong><br>' + err.message + '</div>';
    document.getElementById('intel-loading').style.display = 'none';
  });
`;
}