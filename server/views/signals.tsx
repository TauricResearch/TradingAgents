/** @jsxImportSource hono/jsx */

export function SignalsView() {
  return (
    <>
      <h2>Signals</h2>

      <section class="panel">
        <div class="form-row">
          <select id="signals-ticker" hx-get="/api/signals" hx-target="#signals-table"
                  hx-swap="innerHTML" hx-trigger="change">
            <option value="">All tickers</option>
          </select>
        </div>
      </section>

      <section class="panel">
        <table id="signals-table" hx-get="/api/signals" hx-trigger="load"
               hx-target="#signals-table" hx-swap="innerHTML">
          <thead>
            <tr><th>Date</th><th>Ticker</th><th>Signal</th><th>Confidence</th><th>Reasoning</th></tr>
          </thead>
          <tbody><tr><td colspan="5" class="muted">Loading…</td></tr></tbody>
        </table>
      </section>

      <script dangerouslySetInnerHTML={{ __html: signalsScript() }} />
    </>
  );
}

function signalsScript(): string {
  return `
document.body.addEventListener('htmx:afterOnLoad', function(evt) {
  if (evt.detail.target.id !== 'signals-table') return;
  try {
    var data = JSON.parse(evt.detail.xhr.responseText);
    var tbody = document.querySelector('#signals-table tbody');
    if (!tbody) return;
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted">No signals recorded</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(function(s) {
      var cls = '';
      var sig = (s.signal || '').toLowerCase();
      if (sig.includes('buy') || sig.includes('overweight')) cls = 'status-buy';
      else if (sig.includes('sell') || sig.includes('underweight')) cls = 'status-sell';
      else cls = 'status-hold';
      return '<tr>' +
        '<td>' + (s.date || '—') + '</td>' +
        '<td>' + s.ticker + '</td>' +
        '<td class="' + cls + '">' + s.signal + '</td>' +
        '<td>' + (s.confidence != null ? Math.round(s.confidence * 100) + '%' : '—') + '</td>' +
        '<td class="muted">' + (s.reasoning || '').substring(0, 120) + (s.reasoning && s.reasoning.length > 120 ? '…' : '') + '</td>' +
      '</tr>';
    }).join('');
    var select = document.getElementById('signals-ticker');
    if (select && select.options.length <= 1) {
      var tickers = [];
      data.forEach(function(s) { if (!tickers.includes(s.ticker)) tickers.push(s.ticker); });
      tickers.forEach(function(t) {
        var opt = document.createElement('option');
        opt.value = t; opt.textContent = t;
        select.appendChild(opt);
      });
    }
  } catch(e) {}
});`;
}
