/** @jsxImportSource hono/jsx */

export function ExitsView() {
  return (
    <>
      <section class="panel" id="exits-panel">
        <h3>Exit Plans</h3>
        <div id="exits-body">
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

      var _e = function(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');};
      let html = '';
      for (const s of statuses) {
        const p = s.plan;
        const pnlClass = s.pnlPct >= 0 ? 'positive' : 'negative';
        const isWarn = s.distanceToStopPct < 10;
        // Warning card: light yellow bg → dark text. Normal card: dark bg → light text.
        const warnStyle = isWarn ? ' style="background:#fff3cd;color:#1a1a2e"' : '';

        html += '<div class="exit-card"' + warnStyle + '>';
        html += '<div class="exit-header">';
        html += '<span class="ticker">' + p.ticker + '</span>';
        if (p.platform && p.platform !== 'unknown') {
          html += '<span class="platform-tag">' + p.platform + '</span>';
        }
        const pnlColor = isWarn ? '#1a1a2e' : (s.pnlPct >= 0 ? 'var(--green)' : 'var(--red)');
        html += '<span class="pnl" style="color:' + pnlColor + '">';
        html += (s.pnlPct >= 0 ? '+' : '') + s.pnlPct.toFixed(1) + '%</span>';
        html += '</div>';

        html += '<div class="exit-details">';
        html += '<div><strong>Thesis:</strong> ' + _e(p.thesis || '—') + '</div>';
        html += '<div><strong>Entry:</strong> ' + p.quantity + ' @ \u00a3' + p.entry_price.toFixed(2) + ' <span class="muted">(GBP)</span></div>';

        // Stop loss (handle flat YAML format: invalidation_price vs nested invalidation.price)
        const stopPrice = p.invalidation?.price ?? p.invalidation_price ?? 0;
        html += '<div><strong>Stop:</strong> \u00a3' + stopPrice.toFixed(2) + ' <span class="muted">(GBP)</span>';
        if (s.distanceToStopPct !== undefined) {
          html += ' (' + s.distanceToStopPct.toFixed(1) + '% away)';
        }
        html += '</div>';

        // Targets
        if (p.targets && p.targets.length > 0) {
          html += '<div><strong>Targets:</strong> ' + s.targetsHit + '/' + p.targets.length + ' hit';
          if (s.nextTarget) {
            html += ' \u2192 next \u00a3' + s.nextTarget.price.toFixed(2) + ' <span class="muted">(GBP)</span>';
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

        // Invalidation thesis (flat: invalidation_thesis, nested: invalidation.thesis)
        const invThesis = p.invalidation?.thesis ?? p.invalidation_thesis ?? '—';
        html += '<div><strong>Invalidation:</strong> ' + _e(invThesis) + '</div>';

        // Notes
        if (p.notes) {
          html += '<div class="notes">' + _e(p.notes) + '</div>';
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
