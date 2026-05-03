/** @jsxImportSource hono/jsx */

export function SignalsView() {
  return (
    <>
      <section class="panel">
        <div class="form-row">
          <select id="signals-platform">
            <option value="">— Platform —</option>
            <option value="degiero">DeGiro</option>
            <option value="ibkr">IBKR</option>
            <option value="pension:nn">Pension (NN)</option>
            <option value="test">Test</option>
            <option value="unknown">Other/Unknown</option>
          </select>
          <select id="signals-ticker">
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
            <tr><th>Platform</th><th class="date-col">Date</th><th>Ticker</th><th>Signal</th><th>Conf.</th><th>Reasoning</th></tr>
          </thead>
          <tbody id="signals-body"><tr><td colSpan={6} class="muted">Loading…</td></tr></tbody>
        </table>
      </section>

      <script dangerouslySetInnerHTML={{ __html: signalsScript() }} />
    </>
  );
}

function signalsScript(): string {
  return `
// Load signals on page load
function loadSignals() {
  var params = [];
  var pSel = document.getElementById('signals-platform');
  var tSel = document.getElementById('signals-ticker');
  if (pSel && pSel.value) params.push('platform=' + encodeURIComponent(pSel.value));
  if (tSel && tSel.value) params.push('ticker=' + encodeURIComponent(tSel.value));
  var url = '/api/signals' + (params.length ? '?' + params.join('&') : '');
  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    var tbody = document.getElementById('signals-body');
    if (!tbody) return;
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">No signals recorded</td></tr>';
      return;
    }
    var _fmt = function(d) {
      if (!d) return '—';
      var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      var parts = d.split('-');
      if (parts.length !== 3) return d;
      return parseInt(parts[2], 10) + months[parseInt(parts[1], 10) - 1] + parts[0].slice(2);
    };
    tbody.innerHTML = data.map(function(s) {
      var cls = signalClass(s.signal);
      var plat = s.platform || 'unknown';
      return '<tr>' +
        '<td><span class="platform-tag date-col">' + plat + '</span></td>' +
        '<td class="date-col">' + _fmt(s.date) + '</td>' +
        '<td class="ticker">' + s.ticker + '</td>' +
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
      '<span class="timeline-date date-col">' + _fmt(s.date) + '</span>' +
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
  loadSignals();
});
document.getElementById('signals-platform').addEventListener('change', function() {
  loadSignals();
});`;
}
