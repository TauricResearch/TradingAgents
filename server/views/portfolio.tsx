/** @jsxImportSource hono/jsx */

export function PortfolioView() {
  return (
    <>
      <section class="panel">
        <h3>Positions</h3>
        <table id="positions-table" hx-get="/api/positions" hx-trigger="load" hx-target="#positions-table" hx-swap="innerHTML">
          <thead>
            <tr>
              <th>Ticker</th><th>Shares</th><th>Avg Cost</th>
              <th>Entry Date</th><th>Thesis</th><th></th>
            </tr>
          </thead>
          <tbody><tr><td colspan="6" class="muted">Loading…</td></tr></tbody>
        </table>
      </section>

      <section class="panel">
        <h3>Add Position</h3>
        <form hx-post="/api/positions" hx-target="#positions-table" hx-swap="none" {...{ "hx-on::after-request": "this.reset(); htmx.trigger('#positions-table','load')" }}>
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. TKA.DE)" required />
            <input name="quantity" type="number" placeholder="Shares" required />
            <input name="avg_cost" type="number" step="0.01" placeholder="Avg Cost" required />
          </div>
          <div class="form-row">
            <input name="entry_date" type="date" />
            <input name="thesis" placeholder="Investment thesis" />
            <button type="submit">Add Position</button>
          </div>
        </form>
      </section>

      <script dangerouslySetInnerHTML={{ __html: renderPositionsScript() }} />
    </>
  );
}

function renderPositionsScript(): string {
  return `
document.body.addEventListener('htmx:afterOnLoad', function(evt) {
  if (evt.detail.target.id !== 'positions-table') return;
  try {
    const data = JSON.parse(evt.detail.xhr.responseText);
    const tbody = document.querySelector('#positions-table tbody');
    if (!tbody) return;
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">No open positions</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(function(p) {
      return '<tr>' +
        '<td>' + p.ticker + '</td>' +
        '<td>' + p.quantity + '</td>' +
        '<td>€' + p.avg_cost + '</td>' +
        '<td>' + (p.entry_date || '—') + '</td>' +
        '<td>' + (p.thesis || '—') + '</td>' +
        '<td><button class="btn-sm" hx-delete="/api/positions/' + p.id + '" ' +
        'hx-target="#positions-table" hx-swap="none" ' +
        'hx-on::after-request="htmx.trigger(\'#positions-table\',\'load\')">Close</button></td>' +
      '</tr>';
    }).join('');
  } catch(e) {}
});`;
}
