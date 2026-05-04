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

  // FX conversion helpers (GBP base currency)
  // Rates fetched from /api/portfolio/intelligence; fallbacks for offline
  var GBPEUR = 1.18;
  var GBPUSD = 1.27;
  var gbpPerEur = 1 / GBPEUR;
  var gbpPerUsd = 1 / GBPUSD;

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
      .catch(function() { cb(); }); // fall back to defaults
  }

  function toGbp(amount, currency) {
    if (currency === 'EUR') return amount * gbpPerEur;
    if (currency === 'USD') return amount * gbpPerUsd;
    return amount; // already GBP
  }

  function fmt(n) {
    return '\\u00a3' + n.toFixed(2);
  }

  // ── Event delegation ────────────────────────────────────────────────
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
        // hledger costBasis is in the commodity's cost currency — convert to GBP
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
      fetch('/api/holdings')
        .then(function(r) { return r.json(); })
        .then(function(result) {
          renderHoldings(result);
          renderCash(result);
        })
        .catch(function(err) {
          document.getElementById('holdings-body').innerHTML =
            '<div class="error-card"><strong>hLedger error</strong><br>' + err.message + '</div>';
        });
    });
  }

  refresh();
  setInterval(refresh, 30000);

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