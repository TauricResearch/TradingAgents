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
        <button class="btn-sm" onclick="closeAnalysisDetail()">← Back to list</button>
        <div id="analysis-card"></div>
        <div id="analysis-full" style="display:none"><div id="analysis-content"></div></div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: historyScript() }} />
    </>
  );
}

function historyScript(): string {
  return `
function closeAnalysisDetail() {
  document.getElementById('analysis-detail').style.display = 'none';
  document.getElementById('analyses-table').style.display = 'table';
}

function showAnalysisFull(ticker, date) {
  var full = document.getElementById('analysis-full');
  var content = document.getElementById('analysis-content');
  full.style.display = 'block';
  content.innerHTML = '<p class="muted">Loading full report…</p>';
  fetch('/api/analyses/' + ticker + '/' + date)
    .then(function(r) { return r.text(); })
    .then(function(html) { content.innerHTML = html; })
    .catch(function() { content.innerHTML = '<p class="muted">Failed to load report</p>'; });
}

function explainAnalysis(ticker, date) {
  var el = document.getElementById('analysis-explain');
  if (el.style.display === 'block') { el.style.display = 'none'; return; }
  el.style.display = 'block';
  el.innerHTML = '<p class="muted">Asking LLM to explain…</p>';
  fetch('/api/analyses/' + ticker + '/' + date + '/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var html = '<div class="explain-card">';
      if (d.plain_english) html += '<p class="explain-text">' + d.plain_english + '</p>';
      var fields = [
        ['Position size', d.position_size],
        ['Entry', d.entry_strategy],
        ['Risk', d.risk_management],
        ['Horizon', d.time_horizon],
        ['Catalysts', d.catalysts],
        ['Risks', d.risks],
      ];
      for (var i = 0; i < fields.length; i++) {
        if (fields[i][1]) {
          html += '<div class="explain-field"><strong>' + fields[i][0] + ':</strong> ' + fields[i][1] + '</div>';
        }
      }
      html += '</div>';
      el.innerHTML = html;
    })
    .catch(function() { el.innerHTML = '<p class="muted">Failed to get explanation</p>'; });
}

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
        '<td><button class="btn-sm" onclick="loadAnalysisCard(\\'' + a.ticker + '\\',\\'' + a.date + '\\')">View</button></td>' +
      '</tr>';
    }).join('');
  } catch(e) {}
});

function loadAnalysisCard(ticker, date) {
  document.getElementById('analyses-table').style.display = 'none';
  var detail = document.getElementById('analysis-detail');
  var card = document.getElementById('analysis-card');
  var full = document.getElementById('analysis-full');
  detail.style.display = 'block';
  full.style.display = 'none';
  card.innerHTML = '<p class="muted">Loading summary…</p>';
  fetch('/api/analyses/' + ticker + '/' + date + '/summary')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var cls = signalClass(d.signal);
      var pct = Math.round((d.confidence || 0.5) * 100);
      var pie = '{p:' + pct + '}';
      var sparkline = d.sparkline && d.sparkline.length > 1 ? '{l:' + d.sparkline.join(',') + '}' : '';
      var sparklineHtml = sparkline ? '<div class="datatype-sparkline">' + sparkline + '</div>' : '';

      var agentsHtml = Object.entries(d.agents).map(function(entry) {
        return '<tr><td>' + entry[0] + '</td><td class="' + signalClass(String(entry[1])) + '">' + entry[1] + '</td></tr>';
      }).join('');

      var actionsHtml = (d.actions || []).map(function(a) {
        return '<li>' + a + '</li>';
      }).join('');
      var actionsSection = actionsHtml ? '<h4>Recommended Actions</h4><ul class="action-list">' + actionsHtml + '</ul>' : '';

      card.innerHTML =
        '<div class="analysis-header">' +
          '<span class="datatype-pie ' + cls + '">' + pie + '</span>' +
          '<h3 class="' + cls + '">' + d.ticker + ' — ' + d.signal + '</h3>' +
          '<span class="analysis-date">' + d.date + ' · ' + pct + '%</span>' +
        '</div>' +
        sparklineHtml +
        '<p class="analysis-summary">' + d.summary + '</p>' +
        '<button class="btn-detail" onclick="explainAnalysis(\\'' + d.ticker + '\\',\\'' + d.date + '\\')">Explain this analysis →</button>' +
        '<div id="analysis-explain" style="display:none"></div>' +
        '<table class="agent-table"><thead><tr><th>Agent</th><th>Verdict</th></tr></thead><tbody>' + agentsHtml + '</tbody></table>' +
        '<button class="btn-detail" onclick="showAnalysisFull(\\'' + d.ticker + '\\',\\'' + d.date + '\\')">View full report →</button>';
    })
    .catch(function() { card.innerHTML = '<p class="muted">Failed to load summary</p>'; });
}

function signalClass(signal) {
  var s = (signal || '').toLowerCase();
  if (s.includes('buy') || s.includes('overweight')) return 'status-buy';
  if (s.includes('sell') || s.includes('underweight')) return 'status-sell';
  return 'status-hold';
}`;
}
