/** @jsxImportSource hono/jsx */

export function HistoryView() {
  return (
    <>
      <section class="panel">
        <h3>Past Analyses</h3>
        <table id="analyses-table">
          <thead>
            <tr><th class="date-col">Date</th><th>Ticker</th><th></th></tr>
          </thead>
          <tbody id="analyses-body">
            <tr><td colspan={5} class="muted">Loading…</td></tr>
          </tbody>
        </table>
      </section>

      <section class="panel" id="analysis-detail" style="display:none">
        <button class="btn-sm" data-action="closeAnalysisDetail">← Back to list</button>
        <div id="analysis-card"></div>
        <div id="analysis-full" style="display:none"><div id="analysis-content"></div></div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: historyScript() }} />
    </>
  );
}

function historyScript(): string {
  return `
(function() {

  // ── Event delegation for data-action attributes ──────────────────────
  function wireActions() {
    document.querySelectorAll('[data-action]').forEach(function(el) {
      el.addEventListener('click', function(e) {
        var action = e.currentTarget.dataset.action;
        if (action === 'closeAnalysisDetail') closeAnalysisDetail();
        if (action === 'loadAnalysisCard') loadAnalysisCard(
          e.currentTarget.dataset.ticker, e.currentTarget.dataset.date);
        if (action === 'explainAnalysis') explainAnalysis(
          e.currentTarget.dataset.ticker, e.currentTarget.dataset.date);
        if (action === 'showAnalysisFull') showAnalysisFull(
          e.currentTarget.dataset.ticker, e.currentTarget.dataset.date);
      });
    });
  }

  function _fmt(d) {
    if (!d) return '—';
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var parts = d.split('-');
    if (parts.length !== 3) return d;
    return parseInt(parts[2], 10) + months[parseInt(parts[1], 10) - 1] + parts[0].slice(2);
  }
  function _esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function loadAnalyses() {
    var tbody = document.getElementById('analyses-body');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="3" class="muted">Loading…</td></tr>';
    fetch('/api/analyses/list')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!Array.isArray(data) || data.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" class="muted">No analyses yet. Run one from the Analysis tab.</td></tr>';
          wireActions();
          return;
        }
        var hasRaw = function(a) { return a.has_raw_state ? 'raw' : 'dec'; };
        var rowClass = function(a) { return a.has_raw_state ? 'has-raw' : 'dec-only'; };
        tbody.innerHTML = data.map(function(a) {
          var decisionShort = a.decision ? a.decision.substring(0,60) : '—';
          return '<tr class="' + rowClass(a) + '">' +
            '<td class="date-col">' + _fmt(a.date) + '</td>' +
            '<td class="ticker">' + a.ticker + '</td>' +
            '<td class="muted" style="font-size:0.8em;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + _esc(a.decision || '') + '">' + _esc(decisionShort) + '</td>' +
            '<td><span class="platform-tag">' + _esc(a.platform) + '</span></td>' +
            '<td><button class="btn-sm" data-action="loadAnalysisCard" data-id="' + a.id + '" data-date="' + _esc(a.date) + '">View</button></td>' +
          '</tr>';
        }).join('');
        wireActions();
      })
      .catch(function() {
        tbody.innerHTML = '<tr><td colspan="5" class="muted">Failed to load analyses</td></tr>';
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadAnalyses);
  } else {
    loadAnalyses();
  }

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

  function loadAnalysisCard(id, date) {
    document.getElementById('analyses-table').style.display = 'none';
    var detail = document.getElementById('analysis-detail');
    var card = document.getElementById('analysis-card');
    var full = document.getElementById('analysis-full');
    detail.style.display = 'block';
    full.style.display = 'none';
    card.innerHTML = '<p class="muted">Loading report…</p>';

    fetch('/api/analyses/' + id)
      .then(function(r) {
        if (!r.ok) return r.json().then(function(err) { throw new Error(err.error || 'Server error ' + r.status); });
        return r.text();
      })
      .then(function(html) {
        // Wrap in analysis card container
        card.innerHTML = '<div class="analysis-report-container">' + html + '</div>';
        wireActions();
      })
      .catch(function(e) { card.innerHTML = '<div class="error-card"><strong>Error:</strong> ' + e.message + '</div>'; });
  }

  function signalClass(signal) {
    var s = (signal || '').toLowerCase();
    if (s.includes('buy') || s.includes('overweight')) return 'status-buy';
    if (s.includes('sell') || s.includes('underweight')) return 'status-sell';
    return 'status-hold';
  }

})();
`;
}