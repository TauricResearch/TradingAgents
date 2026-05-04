/** @jsxImportSource hono/jsx */

export function HoldingsView() {
  return (
    <>
      <section class="panel" id="holdings-panel">
        <h3>Holdings <span class="muted" style="font-size:0.8em">(base: GBP)</span></h3>
        <div id="holdings-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      {/* ── Positions with prices + sparklines + stop monitoring ── */}
      <section class="panel" id="positions-panel">
        <h3>
          Positions
          <span class="muted" style="font-size:0.8em"> — live prices from Yahoo Finance</span>
        </h3>
        <div id="positions-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="cash-panel">
        <h3>Cash <span class="muted" style="font-size:0.8em">(base: GBP)</span></h3>
        <div id="cash-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: holdingsScript() }} />
    </>
  );
}

function holdingsScript(): string {
  return `
(function() {

  // ── FX helpers ─────────────────────────────────────────────────
  var GBPEUR = 1.18, GBPUSD = 1.27;
  var gbpPerEur = 1 / GBPEUR, gbpPerUsd = 1 / GBPUSD;
  var ratesLoaded = false;

  function loadRates(cb) {
    if (ratesLoaded) { cb(); return; }
    fetch('/api/portfolio/intelligence')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var fx = data.fx_rates || {};
        if (fx.GBPEUR) { GBPEUR = fx.GBPEUR; gbpPerEur = 1 / GBPEUR; }
        if (fx.GBPUSD) { GBPUSD = fx.GBPUSD; gbpPerUsd = 1 / GBPUSD; }
        ratesLoaded = true;
        cb();
      })
      .catch(function() { cb(); });
  }

  function toGbp(amount, currency) {
    if (currency === 'EUR') return amount * gbpPerEur;
    if (currency === 'USD') return amount * gbpPerUsd;
    return amount;
  }

  function fmt(n) {
    return '\\u00a3' + n.toFixed(2);
  }

  function fmtPct(n) {
    return (n >= 0 ? '+' : '') + n.toFixed(1) + '%';
  }

  function fmtNum(n, decimals) {
    return n.toFixed(decimals != null ? decimals : 2);
  }

  function isCrypto(ticker) {
    return ticker === 'ETH' || ticker === 'BTC' || ticker === 'SOL' ||
           ticker === 'XRP' || ticker === 'ADA' || ticker === 'DOT';
  }

  function renderStopBadge(level) {
    if (level === 'danger') return '<span class="stop-badge stop-danger" title="Stop triggered or within 5%">\\u{1F534} stop</span>';
    if (level === 'watch') return '<span class="stop-badge stop-watch" title="Stop within 5\\u201320%">\\u{1F7E1} watch</span>';
    if (level === 'safe') return '<span class="stop-badge stop-safe" title="Stop >20% above current price">\\u{1F7E2} ok</span>';
    return '<span class="stop-badge stop-none" title="No exit plan">\\u2014</span>';
  }

  function renderFreshnessBadge(dateStr) {
    if (!dateStr) return '<span class="freshness-none">\\u2014</span>';
    var diffMs = Date.now() - new Date(dateStr + 'T12:00:00Z').getTime();
    var diffDays = diffMs / (1000 * 60 * 60 * 24);
    if (diffDays < 1) return '<span class="freshness fresh-ok" title="Updated today">\\u{1F7E2}</span>';
    if (diffDays < 2) return '<span class="freshness fresh-stale" title="Updated yesterday">\\u{1F7E1}</span>';
    return '<span class="freshness fresh-old" title="No recent data (\\u003e' + Math.floor(diffDays) + ' days)">\\u{1F534}</span>';
  }

  function renderSparkline(values) {
    if (!values || values.length === 0) return '<span class="sparkline-muted">\\u2014</span>';
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    var range = max - min || 1;
    var encoded = values.map(function(v) {
      return Math.round(((v - min) / range) * 100);
    }).join(',');
    return '<span class="datatype" style="font-feature-settings:\\'calt\\' 1,\\'liga\\' 1">' +
           '{l:' + encoded + '}</span>';
  }

  function renderPositions(result) {
    var el = document.getElementById('positions-body');
    if (!result.positions || result.positions.length === 0) {
      el.innerHTML = '<div class="muted">No open positions.</div>';
      return;
    }

    var html = '';
    var groups = {};
    for (var i = 0; i < result.positions.length; i++) {
      var p = result.positions[i];
      var key = p.platform || 'unknown';
      if (!groups[key]) groups[key] = [];
      groups[key].push(p);
    }

    var platformNames = Object.keys(groups).sort();
    for (var gi = 0; gi < platformNames.length; gi++) {
      var platName = platformNames[gi];
      var items = groups[platName];

      html += '<div class="positions-platform">';
      html += '<div class="positions-platform-header">' + platName + ' (' + items.length + ')</div>';

      html += '<table class="data-table positions-table"><thead><tr>';
      html += '<th></th>';
      html += '<th>Ticker</th>';
      html += '<th>Sparkline</th>';
      html += '<th>Qty</th>';
      html += '<th>Avg Cost</th>';
      html += '<th>Current</th>';
      html += '<th>Value</th>';
      html += '<th>P\\u0026L</th>';
      html += '<th>Stop</th>';
      html += '<th></th>';
      html += '</tr></thead><tbody>';

      for (var j = 0; j < items.length; j++) {
        var pos = items[j];
        var costPerShareGbp = toGbp(pos.avgCost || 0, pos.exchange === 'XETRA' ? 'EUR' : pos.exchange === 'CRYPTO' ? 'USD' : 'USD');
        var pnlClass = pos.pnlPct >= 0 ? 'pnl-pos' : 'pnl-neg';
        var pnlStr = pos.pnlPct !== null ? fmtPct(pos.pnlPct) : '\\u2014';
        var valueStr = pos.currentValue !== null ? fmt(toGbp(pos.currentValue, 'GBP')) : '\\u2014';
        var currStr = pos.currentPrice !== null ? '\\u00a3' + fmtNum(pos.currentPrice, 2) : '\\u2014';
        var invStr = pos.invalidationPrice !== null ? '\\u00a3' + fmtNum(pos.invalidationPrice, 2) : '\\u2014';

        html += '<tr class="position-row position-' + pos.stopLevel + '">';
        html += '<td>' + renderFreshnessBadge(pos.lastPriceDate) + '</td>';
        html += '<td class="ticker-cell"><span class="ticker">' + pos.ticker + '</span>';
        if (pos.platform) html += '<span class="platform-tag">' + pos.platform + '</span>';
        html += '</td>';
        html += '<td>' + renderSparkline(pos.sparkline) + '</td>';
        html += '<td>' + fmtNum(pos.quantity, isCrypto(pos.ticker) ? 4 : 0) + '</td>';
        html += '<td class="mono">' + fmt(toGbp(costPerShareGbp, 'GBP')) + '</td>';
        html += '<td class="mono" title="Inv: ' + invStr + '">' + currStr + '</td>';
        html += '<td class="mono">' + valueStr + '</td>';
        html += '<td class="mono ' + pnlClass + '">' + pnlStr + '</td>';
        html += '<td>' + renderStopBadge(pos.stopLevel) + '</td>';
        html += '<td><button class="btn-sm" data-action="analyzeTicker" data-ticker="' + pos.ticker + '">Analyze</button></td>';
        html += '</tr>';
      }

      html += '</tbody></table>';
      html += '</div>';
    }

    el.innerHTML = html;
    wireActions();
  }

  function wireActions() {
    document.querySelectorAll('[data-action]').forEach(function(el) {
      el.addEventListener('click', function(e) {
        var action = e.currentTarget.dataset.action;
        if (action === 'analyzeTicker') analyzeTicker(e.currentTarget.dataset.ticker);
      });
    });
  }

  function renderHoldings(result) {
    var el = document.getElementById('holdings-body');
    if (!result.holdings || result.holdings.length === 0) {
      el.innerHTML = '<div class="muted">No holdings found. Add transactions to your hLedger journal.</div>';
      return;
    }

    var html = '';
    if (result.platforms && result.platforms.length > 0) {
      html += '<div class="platform-cards">';
      for (var pi = 0; pi < result.platforms.length; pi++) {
        var p = result.platforms[pi];
        html += '<div class="platform-card">';
        html += '<div class="platform-name">' + p.name + '</div>';
        html += '<div class="platform-total">' + fmt(p.totalValue) + '</div>';
        html += '<div class="platform-detail">' + p.holdingCount + ' holdings \\u00b7 ' + fmt(p.cash) + ' cash</div>';
        html += '</div>';
      }
      html += '</div>';
    }

    html += '<table class="data-table"><thead><tr>';
    html += '<th>Platform</th><th>Ticker</th><th>Qty</th><th>Cost/Share (GBP)</th><th>Cost Basis (GBP)</th><th></th>';
    html += '</tr></thead><tbody>';

    var groups = {};
    for (var hi = 0; hi < result.holdings.length; hi++) {
      var h = result.holdings[hi];
      var p = h.platform || 'unknown';
      if (!groups[p]) groups[p] = [];
      groups[p].push(h);
    }

    var platformNames = Object.keys(groups).sort();
    for (var gi = 0; gi < platformNames.length; gi++) {
      var platName = platformNames[gi];
      var groupItems = groups[platName];
      var groupHtml = '';
      var total = 0;
      for (var hj = 0; hj < groupItems.length; hj++) {
        var h2 = groupItems[hj];
        var costGbp = toGbp(h2.costBasis, h2.currency || 'EUR');
        var costPerShareGbp = toGbp(h2.costPerShare || 0, h2.currency || 'EUR');
        total += costGbp;
        groupHtml += '<tr>';
        groupHtml += '<td></td>';
        groupHtml += '<td class="ticker">' + h2.ticker + '</td>';
        groupHtml += '<td>' + h2.quantity + '</td>';
        groupHtml += '<td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1">' + fmt(costPerShareGbp) + '</td>';
        groupHtml += '<td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1">' + fmt(costGbp) + '</td>';
        groupHtml += '<td><button class="btn-sm" data-action="analyzeTicker" data-ticker="' + h2.ticker + '">Analyze</button></td>';
        groupHtml += '</tr>';
      }
      html += '<tr class="platform-group-header">';
      html += '<td colspan="2"><strong>' + platName + '</strong></td>';
      html += '<td colspan="2" class="muted">' + groupItems.length + ' position(s)</td>';
      html += '<td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1"><strong>' + fmt(total) + '</strong></td>';
      html += '<td></td>';
      html += '</tr>';
      html += groupHtml;
    }

    html += '</tbody></table>';
    el.innerHTML = html;
    wireActions();
  }

  function renderCash(result) {
    var el = document.getElementById('cash-body');
    if (!result.cash || result.cash.length === 0) {
      el.innerHTML = '<div class="muted">No cash balances.</div>';
      return;
    }

    var groups = {};
    for (var ci = 0; ci < result.cash.length; ci++) {
      var c = result.cash[ci];
      var p = c.platform || 'unknown';
      if (!groups[p]) groups[p] = [];
      groups[p].push(c);
    }

    var html = '<table class="data-table"><thead><tr>';
    html += '<th>Platform</th><th>Currency</th><th>Amount (GBP)</th>';
    html += '</tr></thead><tbody>';

    var platformNames = Object.keys(groups).sort();
    for (var gi = 0; gi < platformNames.length; gi++) {
      var platName = platformNames[gi];
      var groupItems = groups[platName];
      var totalGbp = 0;
      for (var cj = 0; cj < groupItems.length; cj++) {
        var c2 = groupItems[cj];
        var amtGbp = toGbp(c2.amount, c2.currency);
        totalGbp += amtGbp;
        html += '<tr><td></td><td>' + c2.currency + '</td><td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1">' + fmt(amtGbp) + '</td></tr>';
      }
      html += '<tr class="platform-group-header">';
      html += '<td><strong>' + platName + '</strong></td>';
      html += '<td class="muted">' + groupItems.length + ' currency</td>';
      html += '<td style="font-family:Datatype,monospace;font-feature-settings:\\'calt\\'1,\\'liga\\'1"><strong>' + fmt(totalGbp) + '</strong></td>';
      html += '</tr>';
    }

    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function refresh() {
    loadRates(function() {
      Promise.all([
        fetch('/api/holdings').then(function(r) { return r.json(); }),
        fetch('/api/holdings/positions').then(function(r) { return r.json(); }),
      ])
        .then(function(results) {
          renderHoldings(results[0]);
          renderPositions(results[1]);
          renderCash(results[0]);
        })
        .catch(function(err) {
          document.getElementById('holdings-body').innerHTML =
            '<div class="error-card"><strong>hLedger error</strong><br>' + err.message + '</div>';
          document.getElementById('positions-body').innerHTML =
            '<div class="error-card"><strong>Positions error</strong><br>' + err.message + '</div>';
        });
    });
  }

  refresh();
  setInterval(refresh, 60000);

  window.analyzeTicker = function(ticker) {
    htmx.ajax('GET', '/analyze', { target: 'body', swap: 'innerHTML' });
    setTimeout(function() {
      var input = document.querySelector('#analyze-form input[name="ticker"]');
      if (input) input.value = ticker;
    }, 100);
  };

})();
`;
}