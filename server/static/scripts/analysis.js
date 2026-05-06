document.getElementById('analysis-ticker').addEventListener('blur', function() {
  var ticker = this.value.trim();
  if (!ticker) return;
  fetch('/api/positions').then(r => r.json()).then(function(positions) {
    var pos = positions.find(function(p) { return p.ticker === ticker; });
    var banner = document.getElementById('position-context-banner');
    if (pos) {
      document.getElementById('position-context-text').textContent =
        'You hold ' + pos.quantity + ' shares @ ' + pos.avg_cost +
        (pos.thesis ? ' — thesis: ' + pos.thesis : '');
      banner.style.display = 'block';
    } else { banner.style.display = 'none'; }
  }).catch(function() {});
});

document.getElementById('analysis-form').addEventListener('submit', function(e) {
  e.preventDefault();
  var ticker = document.getElementById('analysis-ticker').value;
  var date = document.getElementById('analysis-date').value || 'today';
  var debates = document.getElementById('analysis-debates').value;
  var analysts = [];
  document.querySelectorAll('input[name="analysts"]:checked').forEach(function(cb) { analysts.push(cb.value); });
  var progressEl = document.getElementById('analysis-progress');
  var eventsEl = document.getElementById('sse-events');
  var outputEl = document.getElementById('analysis-output');
  var mdEl = document.getElementById('markdown-output');
  progressEl.style.display = 'block';
  outputEl.style.display = 'none';
  eventsEl.innerHTML = '<div class="event">Starting analysis for ' + ticker + '…</div>';
  var body = JSON.stringify({ ticker: ticker, date: date, debates: parseInt(debates), analysts: analysts.join(',') });
  var source = new EventSourcePolyfill('/api/analyze', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body
  });
  source.addEventListener('start', function(e) { eventsEl.innerHTML += '<div class="event">✓ Analysis started</div>'; });
  source.addEventListener('agent_report', function(e) {
    var d = JSON.parse(e.data);
    eventsEl.innerHTML += '<div class="event">✓ ' + d.agent + ' report received</div>';
    if (mdEl) mdEl.innerHTML += '## ' + d.agent + '\\n\\n' + d.content + '\\n\\n';
  });
  source.addEventListener('debate_round', function(e) {
    var d = JSON.parse(e.data);
    eventsEl.innerHTML += '<div class="event">● Debate round ' + d.round + '</div>';
  });
  source.addEventListener('decision', function(e) {
    var d = JSON.parse(e.data);
    eventsEl.innerHTML += '<div class="event status-' + d.signal.toLowerCase() + '">Decision: ' + d.signal + '</div>';
    if (mdEl) mdEl.innerHTML += '## Decision: ' + d.signal + '\\n\\n' + (d.reasoning || '') + '\\n\\n';
  });
  source.addEventListener('complete', function(e) {
    eventsEl.innerHTML += '<div class="event">✓ Analysis complete</div>';
    outputEl.style.display = 'block';
    source.close();
  });
  source.addEventListener('error', function(e) {
    var d = JSON.parse(e.data);
    eventsEl.innerHTML += '<div class="event status-sell">Error: ' + d.message + '</div>';
    source.close();
  });
});

function EventSourcePolyfill(url, opts) {
  var self = this;
  self.close = function() { if (xhr) xhr.abort(); };
  var xhr = new XMLHttpRequest();
  xhr.open(opts.method || 'GET', url, true);
  xhr.setRequestHeader('Accept', 'text/event-stream');
  if (opts.headers) Object.keys(opts.headers).forEach(function(k) { xhr.setRequestHeader(k, opts.headers[k]); });
  var buf = '';
  xhr.onprogress = function() {
    buf += xhr.responseText.slice(buf.length);
    var lines = buf.split('\\n');
    buf = lines.pop();
    lines.forEach(function(line) {
      if (line.startsWith('event:')) { var evt = line.slice(7).trim(); return; }
      if (line.startsWith('data:')) {
        var data = line.slice(5).trim();
        if (evt && self['addEventListener']) {
          var handlers = self._handlers && self._handlers[evt];
          if (handlers) handlers.forEach(function(h) { h({ data: data }); });
        }
        evt = null;
      }
    });
  };
  xhr.onerror = function() {
    var handlers = self._handlers && self._handlers['error'];
    if (handlers) handlers.forEach(function(h) { h({ data: '{"message":"Connection failed"}' }); });
  };
  xhr.send(opts.body || null);
  self._handlers = {};
  self.addEventListener = function(evt, fn) {
    if (!self._handlers[evt]) self._handlers[evt] = [];
    self._handlers[evt].push(fn);
  };
}
