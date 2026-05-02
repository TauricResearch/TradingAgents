/** @jsxImportSource hono/jsx */

const STAGES = ["researching", "analyzed", "candidate", "approved"] as const;

export function ProspectsView() {
  return (
    <>
      <section class="panel" id="prospects-panel">
        <h3>Prospects Pipeline</h3>
        <div id="pipeline-container" hx-get="/api/prospects" hx-trigger="load" hx-swap="innerHTML">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="add-prospect">
        <h3>Add to Watchlist</h3>
        <form id="prospect-form" hx-post="/api/prospects" hx-target="#pipeline-container" hx-swap="innerHTML">
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. AAPL)" required />
            <input name="exchange" placeholder="Exchange" value="US" />
            <select name="priority">
              <option value="high">High</option>
              <option value="medium" selected>Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <input name="thesis" placeholder="Investment thesis" />
          <button type="submit" class="btn">Add</button>
        </form>
      </section>

      <script dangerouslySetInnerHTML={{ __html: prospectsScript() }} />
    </>
  );
}

function prospectsScript(): string {
  return `
  (function() {
    function renderPipeline(items) {
      const el = document.getElementById('pipeline-container');
      if (!items || items.length === 0) {
        el.innerHTML = '<div class="muted">No prospects. Add tickers above.</div>';
        return;
      }

      // Group by stage
      const stages = ${JSON.stringify(STAGES)};
      const groups = {};
      for (const s of stages) groups[s] = [];
      for (const item of items) {
        if (groups[item.stage]) groups[item.stage].push(item);
      }

      let html = '<div class="pipeline">';
      for (const stage of stages) {
        const items = groups[stage] || [];
        const count = items.length;
        html += '<div class="pipeline-column">';
        html += '<div class="pipeline-header">' + stage.charAt(0).toUpperCase() + stage.slice(1);
        html += ' <span class="badge">' + count + '</span></div>';
        html += '<div class="pipeline-body">';

        for (const item of items) {
          html += '<div class="pipeline-card" data-id="' + item.id + '">';
          html += '<div class="card-title">' + item.ticker + '</div>';
          html += '<div class="card-meta">';
          html += '<span class="priority-' + (item.priority || 'medium') + '">' + (item.priority || 'medium') + '</span>';
          html += '<span class="signal">' + (item.last_signal || '—') + '</span>';
          html += '</div>';
          if (item.thesis) {
            html += '<div class="card-thesis">' + item.thesis + '</div>';
          }
          html += '<div class="card-actions">';
          html += '<button class="btn-sm" onclick="advanceStage(' + item.id + ', \\'' + stage + '\\')">→</button>';
          html += '<button class="btn-sm danger" onclick="removeProspect(' + item.id + ')">✕</button>';
          html += '</div></div>';
        }

        html += '</div></div>';
      }
      html += '</div>';
      el.innerHTML = html;
    }

    // Wire form reset after HTMX swap
    document.body.addEventListener('htmx:afterRequest', function(e) {
      if (e.detail.elt && e.detail.elt.id === 'prospect-form') {
        e.detail.elt.reset();
      }
    });

    window.advanceStage = function(id, currentStage) {
      const stages = ${JSON.stringify(STAGES)};
      const idx = stages.indexOf(currentStage);
      if (idx >= stages.length - 1) return; // Already at last stage
      const next = stages[idx + 1];
      fetch('/api/prospects/' + id + '/stage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage: next })
      }).then(() => htmx.ajax('GET', '/api/prospects', { target: '#pipeline-container' }));
    };

    window.removeProspect = function(id) {
      fetch('/api/prospects/' + id, { method: 'DELETE' })
        .then(() => htmx.ajax('GET', '/api/prospects', { target: '#pipeline-container' }));
    };
  })();
  `;
}
