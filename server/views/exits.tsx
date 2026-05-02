/** @jsxImportSource hono/jsx */

export function ExitsView() {
  return (
    <>
      <section class="panel" id="exits-panel">
        <h3>Exit Plans</h3>
        <div id="exits-body" hx-get="/api/positions/exits" hx-trigger="load" hx-swap="innerHTML">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: exitsScript() }} />
    </>
  );
}

function exitsScript(): string {
  return `
  (function() {
    function renderExits(statuses) {
      const el = document.getElementById('exits-body');
      if (!statuses || statuses.length === 0) {
        el.innerHTML = '<div class="muted">No exit plans. Create YAML files in ~/.tradingagents/positions/</div>';
        return;
      }

      let html = '';
      for (const s of statuses) {
        const p = s.plan;
        const pnlClass = s.pnlPct >= 0 ? 'positive' : 'negative';
        const stopWarning = s.distanceToStopPct < 10 ? ' style="background:#fff3cd"' : '';

        html += '<div class="exit-card"' + stopWarning + '>';
        html += '<div class="exit-header">';
        html += '<span class="ticker">' + p.ticker + '</span>';
        html += '<span class="pnl ' + pnlClass + '">';
        html += (s.pnlPct >= 0 ? '+' : '') + s.pnlPct.toFixed(1) + '%</span>';
        html += '</div>';

        html += '<div class="exit-details">';
        html += '<div><strong>Thesis:</strong> ' + (p.thesis || '—') + '</div>';
        html += '<div><strong>Entry:</strong> ' + p.quantity + ' @ €' + p.entry_price.toFixed(2) + '</div>';

        // Stop loss
        html += '<div><strong>Stop:</strong> €' + p.invalidation.price.toFixed(2);
        if (s.distanceToStopPct !== undefined) {
          html += ' (' + s.distanceToStopPct.toFixed(1) + '% away)';
        }
        html += '</div>';

        // Targets
        if (p.targets && p.targets.length > 0) {
          html += '<div><strong>Targets:</strong> ' + s.targetsHit + '/' + p.targets.length + ' hit';
          if (s.nextTarget) {
            html += ' → next €' + s.nextTarget.price.toFixed(2);
            if (s.distanceToTargetPct !== undefined) {
              html += ' (' + s.distanceToTargetPct.toFixed(1) + '% away)';
            }
          }
          html += '</div>';
        }

        // Time stop
        if (s.timeStopDaysLeft !== undefined) {
          const urgency = s.timeStopDaysLeft < 30 ? ' ⚠️' : '';
          html += '<div><strong>Time stop:</strong> ' + s.timeStopDaysLeft + ' days left' + urgency + '</div>';
        }

        // Invalidation thesis
        html += '<div><strong>Invalidation:</strong> ' + (p.invalidation.thesis || '—') + '</div>';

        // Notes
        if (p.notes) {
          html += '<div class="notes">' + p.notes + '</div>';
        }

        html += '</div></div>';
      }
      el.innerHTML = html;
    }

    fetch('/api/positions/exits')
      .then(r => r.json())
      .then(renderExits)
      .catch(err => {
        document.getElementById('exits-body').innerHTML =
          '<div class="error-card"><strong>Error loading exits</strong><br>' + err.message + '</div>';
      });
  })();
  `;
}
