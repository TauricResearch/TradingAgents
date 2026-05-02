/** @jsxImportSource hono/jsx */

export function SignalsView() {
  return (
    <>
      <h2>Signals</h2>

      <section class="panel">
        <div class="form-row">
          <select id="signals-ticker" hx-get="/api/signals" hx-target="#signals-body"
                  hx-swap="innerHTML" hx-trigger="change">
            <option value="">All tickers</option>
          </select>
        </div>
      </section>

      <section class="panel" id="timeline-panel" style="display:none">
        <h3>Signal Timeline</h3>
        <div id="signal-timeline" />
      </section>

      <section class="panel">
        <table id="signals-table" hx-get="/api/signals" hx-trigger="load"
               hx-target="#signals-body" hx-swap="innerHTML">
          <thead>
            <tr><th>Date</th><th>Ticker</th><th>Signal</th><th>Confidence</th><th>Reasoning</th></tr>
          </thead>
          <tbody id="signals-body"><tr><td colspan="5" class="muted">Loading…</td></tr></tbody>
        </table>
      </section>

      <script dangerouslySetInnerHTML={{ __html: signalsScript() }} />
    </>
  );
}

function signalsScript(): string {
  return `
document.body.addEventListener('htmx:afterOnLoad', function(evt) {
  var isSignals = evt.detail.target.id === 'signals-body';
  var isTimeline = evt.detail.target.id === 'signals-timeline';
  if (!isSignals && !isTimeline) return;
  try {
    var data = JSON.parse(evt.detail.xhr.responseText);
    if (data.length === 0) {
      if (isSignals) {
        document.getElementById('signals-body').innerHTML = '<tr><td colspan="5" class="muted">No signals recorded</td></tr>';
      }
      return;
    }
    // Render table rows
    if (isSignals) {
      document.getElementById('signals-body').innerHTML = data.map(function(s) {
        var cls = signalClass(s.signal);
        return '<tr>' +
          '<td>' + (s.date || '—') + '</td>' +
          '<td>' + s.ticker + '</td>' +
          '<td class="' + cls + '">' + s.signal + '</td>' +
          '<td>' + (s.confidence != null ? Math.round(s.confidence * 100) + '%' : '—') + '</td>' +
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
    }

    // Render timeline if a single ticker is selected
    var ticker = document.getElementById('signals-ticker').value;
    if (ticker && data.length > 0) {
      var filtered = data.filter(function(s) { return s.ticker === ticker; });
      if (filtered.length > 0) renderTimeline(ticker, filtered);
    } else {
      document.getElementById('timeline-panel').style.display = 'none';
    }
  } catch(e) {}
});

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
  var maxLen = 30;
  container.innerHTML = signals.map(function(s, i) {
    var cls = signalClass(s.signal);
    var barLen = Math.max(4, maxLen - i * 2);
    return '<div class="timeline-row">' +
      '<span class="timeline-signal ' + cls + '">' + s.signal + '</span>' +
      '<span class="timeline-bar" style="width:' + barLen + 'px"></span>' +
      '<span class="timeline-date">' + (s.date || '—') + '</span>' +
      (i === 0 ? '<span class="timeline-current">current</span>' : '') +
    '</div>';
  }).join('');
}`;
}
