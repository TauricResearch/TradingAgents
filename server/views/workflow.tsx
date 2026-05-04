/** @jsxImportSource hono/jsx */

function workflowScript(): string {
  return `
(function() {

  var stages = [
    { id: 'approved',    label: 'Approved',     color: '#3b82f6', icon: '\u25C7' },
    { id: 'holdings',    label: 'Holdings',     color: '#22c55e', icon: '\u25C6' },
    { id: 'pendingExit', label: 'Pending Exit', color: '#f59e0b', icon: '\u26A0' },
  ];

  function wireActions() {
    document.querySelectorAll('[data-action]').forEach(function(el) {
      el.addEventListener('click', function(e) {
        var a = el.dataset.action;
        if (a === 'analyzeTicker')   analyzeTicker(el.dataset.ticker);
        if (a === 'createExitPlan')  createExitPlan(el.dataset.ticker, el.dataset.platform);
        if (a === 'closePosition')   closePosition(el.dataset.id);
      });
    });
  }

  function fmt(d) {
    if (!d) return '-';
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var p = d.split('-');
    if (p.length !== 3) return d;
    return parseInt(p[2],10) + months[parseInt(p[1],10)-1] + p[0].slice(2);
  }

  function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  function renderCard(item, stageId) {
    var html = '<div class="workflow-card">';
    var plat = (item.platform && item.platform !== 'unknown') ? item.platform : null;

    html += '<div class="card-header">';
    html += '<span class="card-ticker">' + item.ticker + '</span>';
    if (plat) html += '<span class="platform-tag">' + plat + '</span>';
    html += '</div>';

    if (stageId === 'approved') {
      var qty = item.quantity || 0;
      var cost = parseFloat(item.avgCost || 0);
      html += '<div class="card-meta">Entry \u00a3' + cost.toFixed(2) + ' \u00B7 ' + qty + ' shares</div>';
      html += '<div class="card-meta muted">' + fmt(item.entryDate) + '</div>';
      if (item.thesis) html += '<div class="card-thesis">' + esc(item.thesis) + '</div>';
      html += '<div class="entry-process">';
      html += '<div class="process-row"><span class="process-dot" style="background:#6b7280">1</span><span>AI analysis &amp; signal</span></div>';
      html += '<div class="process-row"><span class="process-dot" style="background:#6b7280">2</span><span>Position size: ' + qty + ' shares</span></div>';
      html += '<div class="process-row"><span class="process-dot" style="background:#6b7280">3</span><span>Entry: \u20AC' + cost.toFixed(2) + '</span></div>';
      html += '<div class="process-row"><span class="process-dot" style="background:#ef4444">4</span><span>Define exit plan before entry</span></div>';
      html += '</div>';
      html += '<div class="card-actions">';
      html += '<button class="btn-sm" data-action="analyzeTicker" data-ticker="' + item.ticker + '">Analyze</button>';
      html += '<button class="btn-sm" data-action="createExitPlan" data-ticker="' + item.ticker + '" data-platform="' + (plat||'unknown') + '">+ Exit Plan</button>';
      html += '</div>';

    } else if (stageId === 'holdings') {
      var ep = item.exitPlan || {};
      var inv = parseFloat(ep.invalidationPrice || 0);
      var entry = parseFloat(item.avgCost || ep.entryPrice || 0);
      var days = ep.timeStopDaysLeft;
      html += '<div class="card-meta">Entry \u00a3' + entry.toFixed(2) + ' \u00B7 Stop \u00a3' + inv.toFixed(2) + '</div>';
      if (days !== undefined) html += '<div class="card-meta muted">' + days + 'd to time stop</div>';
      html += '<div class="card-actions">';
      html += '<button class="btn-sm" data-action="analyzeTicker" data-ticker="' + item.ticker + '">Analyze</button>';
      html += '<button class="btn-sm" data-action="closePosition" data-id="' + item.id + '">Close</button>';
      html += '</div>';

    } else if (stageId === 'pendingExit') {
      var ep = item.exitPlan || {};
      var inv = parseFloat(ep.invalidationPrice || 0);
      var entry = parseFloat(item.avgCost || ep.entryPrice || 0);
      var dist = parseFloat(ep.distanceToStopPct || 0);
      var hit = ep.targetsHit || 0;
      var total = (ep.targets || []).length;
      var days = ep.timeStopDaysLeft;
      var targets = ep.targets || [];

      html += '<div class="exit-strategy">';
      html += '<div class="process-row"><span class="process-dot" style="background:#ef4444">Stop</span><span>\u00a3' + inv.toFixed(2) + ' (' + dist.toFixed(0) + '%)</span></div>';
      for (var ti = 0; ti < targets.length; ti++) {
        var tp = targets[ti];
        var isHit = ti < hit;
        var label = (tp.label || ('Target ' + (ti+1)));
        html += '<div class="process-row"><span class="process-dot ' + (isHit ? 'hit' : 'pending') + '">' + (isHit ? '\u2713' : (ti+1)) + '</span><span>' + esc(label) + '</span></div>';
      }
      if (days !== undefined && days !== null) {
        html += '<div class="process-row"><span class="process-dot ' + (days < 30 ? 'warning' : 'pending') + '">\u23F1</span><span>Time stop in ' + days + 'd</span></div>';
      }
      html += '</div>';

      if (dist > 0 && dist < 10) html += '<span class="urgency-badge" style="background:#ef4444">\u26A0 Near stop</span>';
      else if (dist >= 10 && dist < 15) html += '<span class="urgency-badge" style="background:#f59e0b">\u26A0 Watch</span>';
      if (hit > 0) html += '<span class="urgency-badge" style="background:#22c55e">\u2713 ' + hit + '/' + total + ' hit</span>';
      if (days !== undefined && days !== null && days < 30) html += '<span class="urgency-badge" style="background:#ef4444">\u23F1 ' + days + 'd</span>';

      html += '<div class="card-actions">';
      html += '<button class="btn-sm" data-action="analyzeTicker" data-ticker="' + item.ticker + '">Review</button>';
      html += '<button class="btn-sm" data-action="closePosition" data-id="' + item.id + '">Close</button>';
      html += '</div>';
    }

    html += '</div>';
    return html;
  }

  function render(data) {
    var el = document.getElementById('workflow-container');
    var html = '<div class="workflow">';

    for (var si = 0; si < stages.length; si++) {
      var stage = stages[si];
      var items = data[stage.id] || [];
      html += '<div class="workflow-col">';
      html += '<div class="workflow-header" style="border-top-color:' + stage.color + '">';
      html += '<span style="color:' + stage.color + '">' + stage.icon + '</span> ';
      html += stage.label;
      html += ' <span class="badge" style="background:' + stage.color + '">' + items.length + '</span>';
      html += '</div>';
      html += '<div class="workflow-body">';
      if (items.length === 0) {
        html += '<div class="workflow-empty">-</div>';
      } else {
        for (var ji = 0; ji < items.length; ji++) {
          html += renderCard(items[ji], stage.id);
        }
      }
      html += '</div></div>';
    }

    html += '</div>';
    el.innerHTML = html;
    wireActions();
  }

  window.analyzeTicker = function(ticker) {
    htmx.ajax('GET', '/analyze', { target: 'body', swap: 'innerHTML' });
    setTimeout(function() {
      var input = document.querySelector('#analyze-form input[name="ticker"]');
      if (input) input.value = ticker;
    }, 100);
  };

  window.createExitPlan = function(ticker, platform) {
    htmx.ajax('GET', '/exits', { target: '#content', swap: 'innerHTML' });
  };

  window.closePosition = function(id) {
    if (!confirm('Close this position?')) return;
    fetch('/api/positions/' + id, { method: 'DELETE' })
      .then(function() { return fetch('/api/workflow'); })
      .then(function(r) { return r.json(); })
      .then(render)
      .catch(function(err) {
        document.getElementById('workflow-container').innerHTML =
          '<div class="error-card"><strong>Error</strong><br>' + err.message + '</div>';
      });
  };

  fetch('/api/workflow')
    .then(function(r) { return r.json(); })
    .then(render)
    .catch(function(err) {
      document.getElementById('workflow-container').innerHTML =
        '<div class="error-card"><strong>Error loading workflow</strong><br>' + err.message + '</div>';
    });

})();
`;
}

export function WorkflowView() {
  return (
    <>
      <h2>Workflow</h2>
      <div id="workflow-container">
        <div class="workflow-loading">Loading…</div>
      </div>
      <script dangerouslySetInnerHTML={{ __html: workflowScript() }} />
    </>
  );
}