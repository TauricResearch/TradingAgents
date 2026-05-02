/** @jsxImportSource hono/jsx */

export function SignalsView() {
  return (
    <>
      <section class="panel">
        <div class="form-row">
          <select id="signals-ticker" hx-get="/api/signals" hx-target="#signals-body"
                  hx-swap="none" hx-trigger="change">
            <option value="">All tickers</option>
          </select>
        </div>
      </section>

      <section class="panel" id="timeline-panel" style="display:none">
        <h3>Signal Timeline</h3>
        <div id="signal-timeline" />
      </section>

      <section class="panel">
        <table id="signals-table">
          <thead>
            <tr><th>Date</th><th>Ticker</th><th>Signal</th><th>Confidence</th><th>Reasoning</th></tr>
          </thead>
          <tbody id="signals-body"><tr><td colspan={5} class="muted">Loading…</td></tr></tbody>
        </table>
      </section>

      <script dangerouslySetInnerHTML={{ __html: signalsScript() }} />
    </>
  );
}

function signalsScript(): string {
  return `
// Load signals on page load
function loadSignals(ticker) {
  var url = '/api/signals' + (ticker ? '?ticker=' + encodeURIComponent(ticker) : '');
  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    var tbody = document.getElementById('signals-body');
    if (!tbody) return;
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted">No signals recorded</td></tr>';
      return;
    }
    tbody.innerHTML = data.map(function(s) {
      var cls = signalClass(s.signal);
      return '<tr>' +
        '<td>' + (s.date || '—') + '</td>' +
        '<td>' + s.ticker + '</td>' +
        '<td class="' + cls + '">' + s.signal + '</td>' +
        '<td>' + (s.confidence != null ? Math.round((parseFloat(s.confidence) || 0) * 100) + '%' : '—') + '</td>' +
        '<td class="muted">' + (s.reasoning || '').substring(0, 120) + '</td>' +
      '</tr>';
    }).join('');

    // Populate ticker dropdown
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

    // Render timeline if a single ticker is selected
    var sel = document.getElementById('signals-ticker').value;
    if (sel && data.length > 0) {
      var filtered = data.filter(function(s) { return s.ticker === sel; });
      if (filtered.length > 0) renderTimeline(sel, filtered);
    } else {
      var tp = document.getElementById('timeline-panel');
      if (tp) tp.style.display = 'none';
    }
  }).catch(function() {
    var tbody = document.getElementById('signals-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="muted">Failed to load signals</td></tr>';
  });
}

function signalClass(signal) {
  var s = (signal || '').toLowerCase();
  if (s.includes('buy') || s.includes('overweight')) return 'status-buy';
  if (s.includes('sell') || s.includes('underweight')) return 'status-sell';
  return 'status-hold';
}

function renderTimeline(ticker, signals) {
  var panel = document.getElementById('timeline-panel');
  var container = document.getElementById('signal-timeline');
  panel.style.display = 'block';

  var confValues = signals.map(function(s) { return Math.round((parseFloat(s.confidence) || 0.5) * 100); });
  var sparkline = '{l:' + confValues.join(',') + '}';
  var barchart = '{b:' + confValues.join(',') + '}';
  var firstSig = signalClass(signals[0].signal);

  var html = '<div class="sparkline ' + firstSig + '">' + sparkline + '</div>';
  html += '<div class="bar-chart">' + barchart + '</div>';
  html += '<div class="timeline-entries">';
  html += signals.map(function(s, i) {
    var cls = signalClass(s.signal);
    var conf = parseFloat(s.confidence) || 0;
    var pct = Math.round(conf * 100);
    var pie = '{p:' + pct + '}';
    return '<div class="timeline-row ' + cls + '">' +
      '<span class="timeline-signal">' + s.signal + '</span>' +
      '<span class="timeline-date">' + (s.date || '—') + '</span>' +
      '<span class="datatype-pie" title="' + pct + '% confidence">' + pie + '</span>' +
      '<span class="timeline-confidence">' + pct + '%</span>' +
      (i === 0 ? '<span class="timeline-current">current</span>' : '') +
    '</div>';
  }).join('');
  html += '</div>';
  container.innerHTML = html;
}

// Init on load
loadSignals();

document.getElementById('signals-ticker').addEventListener('change', function() {
  loadSignals(this.value || undefined);
});`;
}
