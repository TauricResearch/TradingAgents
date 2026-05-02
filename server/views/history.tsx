/** @jsxImportSource hono/jsx */

export function HistoryView() {
  return (
    <>
      <section class="panel">
        <h3>Past Analyses</h3>
        <table id="analyses-table" hx-get="/api/analyses" hx-trigger="load"
               hx-target="#analyses-body" hx-swap="innerHTML">
          <thead>
            <tr><th>Date</th><th>Ticker</th><th></th></tr>
          </thead>
          <tbody id="analyses-body"><tr><td colspan="3" class="muted">Loading…</td></tr></tbody>
        </table>
      </section>

      <section class="panel" id="analysis-detail" style="display:none">
        <button class="btn-sm" onclick="document.getElementById('analysis-detail').style.display='none'; document.getElementById('analyses-table').style.display='table';">← Back to list</button>
        <div id="analysis-content" />
      </section>

      <script dangerouslySetInnerHTML={{ __html: historyScript() }} />
    </>
  );
}

function historyScript(): string {
  return `
document.body.addEventListener('htmx:afterOnLoad', function(evt) {
  if (evt.detail.target.id !== 'analyses-body') return;
  try {
    var data = JSON.parse(evt.detail.xhr.responseText);
    var tbody = document.getElementById('analyses-body');
    if (!tbody) return;
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="muted">No analyses yet. Run one from the Analysis tab.</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(function(a) {
      return '<tr>' +
        '<td>' + a.date + '</td>' +
        '<td>' + a.ticker + '</td>' +
        '<td><button class="btn-sm" onclick="loadAnalysis(\\'' + a.ticker + '\\',\\'' + a.date + '\\')">View</button></td>' +
      '</tr>';
    }).join('');
  } catch(e) {}
});

function loadAnalysis(ticker, date) {
  document.getElementById('analyses-table').style.display = 'none';
  var detail = document.getElementById('analysis-detail');
  var content = document.getElementById('analysis-content');
  detail.style.display = 'block';
  content.innerHTML = '<p class="muted">Loading report…</p>';
  fetch('/api/analyses/' + ticker + '/' + date)
    .then(function(r) { return r.text(); })
    .then(function(html) { content.innerHTML = html; })
    .catch(function() { content.innerHTML = '<p class="muted">Failed to load report</p>'; });
}`;
}
