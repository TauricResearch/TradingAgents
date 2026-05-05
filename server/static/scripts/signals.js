function signalClass(signal) {
  var s = (signal || '').toLowerCase();
  if (s.includes('buy') || s.includes('overweight')) return 'status-buy';
  if (s.includes('sell') || s.includes('underweight')) return 'status-sell';
  return 'status-hold';
}

function loadSignals() {
  var params = [];
  var pSel = document.getElementById('signals-platform');
  var tSel = document.getElementById('signals-ticker');
  if (pSel && pSel.value) params.push('platform=' + encodeURIComponent(pSel.value));
  if (tSel && tSel.value) params.push('ticker=' + encodeURIComponent(tSel.value));

  // Use /table endpoint for signals + price history
  var url = '/api/signals/table' + (params.length ? '?' + params.join('&') : '');
  fetch(url).then(function(r) { return r.json(); }).then(function(data) {
    var tbody = document.getElementById('signals-body');
    if (!tbody) return;
    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="muted">No signals recorded</td></tr>';
      return;
    }

    tbody.innerHTML = data.map(function(s) {
      var cls = signalClass(s.signal);
      var plat = s.platform || 'unknown';
      var conf = s.confidence != null ? Math.round((parseFloat(s.confidence) || 0) * 100) + '%' : '—';
      var reasoning = (s.reasoning || '').substring(0, 100);
      var spark = _sparkline(s.price_history ? s.price_history.history : null);
      var trendCell = spark
        ? '<span class="trend-sparkline">' + spark + '</span>'
        : '<span class="muted">—</span>';
      return '<tr>' +
        '<td><span class="platform-tag">' + _esc(plat) + '</span></td>' +
        '<td class="date-col">' + _fmtDate(s.date) + '</td>' +
        '<td class="ticker">' + _esc(s.ticker) + '</td>' +
        '<td class="' + cls + '">' + s.signal + '</td>' +
        '<td class="trend-cell ' + cls + '">' + trendCell + '</td>' +
        '<td>' + conf + '</td>' +
        '<td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + _esc(s.reasoning || '') + '">' + _esc(reasoning) + '</td>' +
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
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="muted">Failed to load signals</td></tr>';
  });
}

function renderTimeline(ticker, signals) {
  var panel = document.getElementById('timeline-panel');
  var container = document.getElementById('signal-timeline');
  panel.style.display = 'block';

  // Use price history from first signal for price sparkline
  var priceHist = signals[0].price_history ? signals[0].price_history.history : null;
  var priceSpark = _sparkline(priceHist);

  // Confidence sparkline
  var confValues = signals.map(function(s) { return Math.round((parseFloat(s.confidence) || 0.5) * 100); });
  var confSpark = '{l:' + confValues.join(',') + '}';
  var firstCls = signalClass(signals[0].signal);

  var html = '<div class="timeline-header">';
  if (priceSpark) html += '<div class="timeline-section"><span class="muted" style="font-size:0.75em">Price (20d)</span><div class="trend-cell ' + firstCls + '"><span class="trend-sparkline">' + priceSpark + '</span></div></div>';
  html += '<div class="timeline-section"><span class="muted" style="font-size:0.75em">Confidence</span><div class="sparkline ' + firstCls + '">' + confSpark + '</div></div>';
  html += '</div>';
  html += '<div class="timeline-entries">';
  html += signals.map(function(s, i) {
    var cls = signalClass(s.signal);
    var pct = Math.round((parseFloat(s.confidence) || 0) * 100);
    var pie = '{p:' + pct + '}';
    return '<div class="timeline-row ' + cls + '">' +
      '<span class="timeline-signal">' + s.signal + '</span>' +
      '<span class="timeline-date date-col">' + _fmtDate(s.date) + '</span>' +
      '<span class="datatype-pie" title="' + pct + '% confidence">' + pie + '</span>' +
      '<span class="timeline-confidence">' + pct + '%</span>' +
      (i === 0 ? '<span class="timeline-current">current</span>' : '') +
    '</div>';
  }).join('');
  html += '</div>';
  container.innerHTML = html;
}

loadSignals();

document.getElementById('signals-ticker').addEventListener('change', loadSignals);
document.getElementById('signals-platform').addEventListener('change', loadSignals);
