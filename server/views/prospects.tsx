/** @jsxImportSource hono/jsx */

const STAGES = ["researching", "analyzed", "candidate", "approved"] as const;

export function ProspectsView() {
  return (
    <>
      <section class="panel" id="prospects-panel">
        <div class="form-row" style="margin-bottom:0.75rem">
          <h3 style="margin:0">Prospects Pipeline</h3>
          <select id="prospects-platform" style="margin-left:auto">
            <option value="">All platforms</option>
            <option value="degiero">DeGiro</option>
            <option value="ibkr">IBKR</option>
            <option value="pension:nn">Pension (NN)</option>
            <option value="test">Test</option>
            <option value="unknown">Other/Unknown</option>
          </select>
        </div>
        <div id="pipeline-container">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="add-prospect">
        <h3>Add to Watchlist</h3>
        <form
          id="prospect-form"
          hx-post="/api/prospects"
          hx-swap="none"
          {...{ "hx-on::after-request": "handleProspectSubmit(event)" }}
        >
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. AAPL)" required />
            <input name="exchange" placeholder="Exchange" value="US" />
            <select name="platform">
              <option value="">— Platform —</option>
              <option value="degiero">DeGiro</option>
              <option value="ibkr">IBKR</option>
              <option value="pension:nn">Pension (NN)</option>
              <option value="test">Test</option>
              <option value="unknown">Other</option>
            </select>
          </div>
          <div class="form-row">
            <select name="priority">
              <option value="high">High</option>
              <option value="medium" selected>Medium</option>
              <option value="low">Low</option>
            </select>
            <input name="thesis" placeholder="Investment thesis" />
            <button type="submit" class="btn">Add</button>
          </div>
          <div id="prospect-error" class="error-card" style="display:none"></div>
        </form>
      </section>

      <script dangerouslySetInnerHTML={{ __html: prospectsScript() }} />
    </>
  )
}

function prospectsScript(): string {
  return `
(function() {

  var currentPlatform = '';

  // ── Event delegation ────────────────────────────────────────────────
  function wireActions() {
    document.querySelectorAll('[data-action]').forEach(function(el) {
      el.addEventListener('click', function(e) {
        var action = e.currentTarget.dataset.action;
        if (action === 'advanceStage') advanceStage(
          e.currentTarget.dataset.id, e.currentTarget.dataset.stage);
        if (action === 'removeProspect') removeProspect(e.currentTarget.dataset.id);
      });
    });
  }

  function renderPipeline(items) {
    var el = document.getElementById('pipeline-container');
    if (!items || items.length === 0) {
      el.innerHTML = '<div class="muted">No prospects' + (currentPlatform ? ' for ' + currentPlatform : '') + '. Add tickers above.</div>';
      return;
    }

    // Filter by platform
    var filtered = currentPlatform
      ? items.filter(function(item) { return item.platform === currentPlatform; })
      : items;

    if (filtered.length === 0) {
      el.innerHTML = '<div class="muted">No prospects for ' + currentPlatform + '</div>';
      return;
    }

    var stages = ${JSON.stringify(STAGES)};
    var groups = {};
    for (var si = 0; si < stages.length; si++) {
      groups[stages[si]] = [];
    }
    for (var ii = 0; ii < filtered.length; ii++) {
      var item = filtered[ii];
      if (groups[item.stage]) groups[item.stage].push(item);
    }

    var html = '<div class="pipeline">';
    for (var si = 0; si < stages.length; si++) {
      var stage = stages[si];
      var stageItems = groups[stage] || [];
      var count = stageItems.length;
      if (count === 0) continue; // Skip empty stages
      html += '<div class="pipeline-column">';
      html += '<div class="pipeline-header">' + stage.charAt(0).toUpperCase() + stage.slice(1);
      html += ' <span class="badge">' + count + '</span></div>';
      html += '<div class="pipeline-body">';

      for (var ji = 0; ji < stageItems.length; ji++) {
        var item = stageItems[ji];
        html += '<div class="pipeline-card" data-id="' + item.id + '">';
        html += '<div class="card-title">' + item.ticker + '</div>';
        html += '<div class="card-meta">';
        if (item.platform && item.platform !== 'unknown') {
          html += '<span class="platform-tag">' + item.platform + '</span>';
        }
        html += '<span class="priority-' + (item.priority || 'medium') + '">' + (item.priority || 'medium') + '</span>';
        html += '<span class="signal">' + (item.last_signal || '—') + '</span>';
        html += '</div>';
        if (item.thesis) {
          html += '<div class="card-thesis">' + item.thesis + '</div>';
        }
        html += '<div class="card-actions">';
        html += '<button class="btn-sm" data-action="advanceStage" data-id="' + item.id + '" data-stage="' + stage + '">→</button>';
        html += '<button class="btn-sm danger" data-action="removeProspect" data-id="' + item.id + '">✕</button>';
        html += '</div></div>';
      }

      html += '</div></div>';
    }
    html += '</div>';
    el.innerHTML = html;
    wireActions();
  }

  function loadProspects() {
    fetch('/api/prospects')
      .then(function(r) { return r.json(); })
      .then(renderPipeline)
      .catch(function() {
        document.getElementById('pipeline-container').innerHTML = '<div class="muted">Failed to load prospects</div>';
      });
  }

  window.handleProspectSubmit = function(e) {
    var form = e.detail.elt;
    if (e.detail.successful) {
      form.reset();
      document.getElementById('prospect-error').style.display = 'none';
      loadProspects();
    } else if (e.detail.failed) {
      var errEl = document.getElementById('prospect-error');
      if (errEl) { errEl.textContent = 'Failed to add prospect'; errEl.style.display = 'block'; }
    }
  };

  window.advanceStage = function(id, currentStage) {
    var stages = ${JSON.stringify(STAGES)};
    var idx = stages.indexOf(currentStage);
    if (idx >= stages.length - 1) return;
    var next = stages[idx + 1];
    fetch('/api/prospects/' + id + '/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage: next }),
    }).then(loadProspects);
  };

  window.removeProspect = function(id) {
    fetch('/api/prospects/' + id, { method: 'DELETE' })
      .then(loadProspects);
  };

  // Platform filter — update currentPlatform and re-render
  var platformSel = document.getElementById('prospects-platform');
  if (platformSel) {
    platformSel.addEventListener('change', function() {
      currentPlatform = platformSel.value;
      loadProspects();
    });
  }

  loadProspects();

})();
`;
}