/** @jsxImportSource hono/jsx */

export function HoldingsView() {
  return (
    <>
      <section class="panel" id="holdings-panel">
        <h3>Holdings</h3>
        <div id="holdings-body" hx-get="/api/holdings" hx-trigger="load" hx-swap="innerHTML">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="cash-panel">
        <h3>Cash</h3>
        <div id="cash-body" hx-get="/api/holdings" hx-trigger="load" hx-target="#cash-body" hx-swap="innerHTML" hx-select="#cash-body">
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
    function renderHoldings(result) {
      const el = document.getElementById('holdings-body');
      if (!result.holdings || result.holdings.length === 0) {
        el.innerHTML = '<div class="muted">No holdings found. Add transactions to your hLedger journal.</div>';
        return;
      }

      let html = '<table class="data-table"><thead><tr>';
      html += '<th>Ticker</th><th>Qty</th><th>Cost/Share</th><th>Cost Basis</th><th></th>';
      html += '</tr></thead><tbody>';

      for (const h of result.holdings) {
        html += '<tr>';
        html += '<td class="ticker">' + h.ticker + '</td>';
        html += '<td>' + h.quantity + '</td>';
        html += '<td>€' + h.costPerShare.toFixed(2) + '</td>';
        html += '<td>€' + h.costBasis.toFixed(2) + '</td>';
        html += '<td><button class="btn-sm" onclick="analyzeTicker(\\'' + h.ticker + '\\')">Analyze</button></td>';
        html += '</tr>';
      }

      html += '</tbody></table>';
      el.innerHTML = html;
    }

    function renderCash(result) {
      const el = document.getElementById('cash-body');
      if (!result.cash || result.cash.length === 0) {
        el.innerHTML = '<div class="muted">No cash balances.</div>';
        return;
      }

      let html = '<table class="data-table"><thead><tr>';
      html += '<th>Currency</th><th>Amount</th>';
      html += '</tr></thead><tbody>';

      for (const c of result.cash) {
        html += '<tr>';
        html += '<td>' + c.currency + '</td>';
        html += '<td>€' + c.amount.toFixed(2) + '</td>';
        html += '</tr>';
      }

      html += '</tbody></table>';
      el.innerHTML = html;
    }

    // Poll /api/holdings every 30s
    function refresh() {
      fetch('/api/holdings')
        .then(r => r.json())
        .then(result => {
          renderHoldings(result);
          renderCash(result);
        })
        .catch(err => {
          document.getElementById('holdings-body').innerHTML =
            '<div class="error-card"><strong>hLedger error</strong><br>' + err.message + '</div>';
        });
    }

    refresh();
    setInterval(refresh, 30000);

    window.analyzeTicker = function(ticker) {
      htmx.ajax('GET', '/analyze', { target: 'body', swap: 'innerHTML' });
      // Set ticker in analysis form after load
      setTimeout(() => {
        const input = document.querySelector('#analyze-form input[name="ticker"]');
        if (input) input.value = ticker;
      }, 100);
    };
  })();
  `;
}
