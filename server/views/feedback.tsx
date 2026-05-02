/** @jsxImportSource hono/jsx */

export function FeedbackView() {
  return (
    <>
      <section class="panel" id="accuracy-panel">
        <h3>Signal Accuracy</h3>
        <div id="accuracy-body" hx-get="/api/feedback/accuracy" hx-trigger="load" hx-swap="innerHTML">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="post-mortems-panel">
        <h3>Post-Mortems</h3>
        <div id="post-mortems-body" hx-get="/api/feedback/post-mortems" hx-trigger="load" hx-swap="innerHTML">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: feedbackScript() }} />
    </>
  );
}

function feedbackScript(): string {
  return `
  (function() {
    function renderAccuracy(data) {
      const el = document.getElementById('accuracy-body');
      if (!data || data.totalSignals === 0) {
        el.innerHTML = '<div class="muted">No post-mortems yet. Exit a position to generate one.</div>';
        return;
      }

      let html = '<div class="accuracy-summary">';
      html += '<div class="accuracy-score ' + (data.accuracyPct >= 60 ? 'positive' : 'negative') + '">';
      html += data.accuracyPct + '% accuracy (' + data.correctSignals + '/' + data.totalSignals + ')';
      html += '</div></div>';

      if (data.bySignalType && Object.keys(data.bySignalType).length > 0) {
        html += '<table class="data-table"><thead><tr>';
        html += '<th>Exit Trigger</th><th>Signals</th><th>Correct</th><th>Accuracy</th>';
        html += '</tr></thead><tbody>';
        for (const [type, d] of Object.entries(data.bySignalType)) {
          html += '<tr>';
          html += '<td>' + type + '</td>';
          html += '<td>' + d.total + '</td>';
          html += '<td>' + d.correct + '</td>';
          html += '<td class="' + (d.pct >= 60 ? 'positive' : 'negative') + '">' + d.pct + '%</td>';
          html += '</tr>';
        }
        html += '</tbody></table>';
      }
      el.innerHTML = html;
    }

    function renderPostMortems(mortems) {
      const el = document.getElementById('post-mortems-body');
      if (!mortems || mortems.length === 0) {
        el.innerHTML = '<div class="muted">No post-mortems yet.</div>';
        return;
      }

      let html = '';
      for (const pm of mortems) {
        const signalClass = pm.aiSignalCorrect ? 'positive' : 'negative';
        const signalIcon = pm.aiSignalCorrect ? '✅' : '❌';
        html += '<div class="post-mortem-card">';
        html += '<div class="pm-header">';
        html += '<span class="ticker">' + pm.ticker + '</span>';
        html += '<span class="pm-date">' + pm.exitDate + '</span>';
        html += '</div>';
        html += '<div class="pm-thesis">' + pm.thesis + '</div>';
        html += '<div class="pm-outcome">';
        html += '<span>Thesis: ' + (pm.thesisPlayedOut ? '✅' : '❌') + '</span>';
        html += '<span>AI signal: <span class="' + signalClass + '">' + signalIcon + '</span></span>';
        html += '<span>Exit: ' + pm.exitTrigger + '</span>';
        html += '</div>';
        if (pm.lesson) {
          html += '<div class="pm-lesson">' + pm.lesson + '</div>';
        }
        html += '</div>';
      }
      el.innerHTML = html;
    }

    fetch('/api/feedback/accuracy')
      .then(r => r.json())
      .then(renderAccuracy)
      .catch(() => {});

    fetch('/api/feedback/post-mortems')
      .then(r => r.json())
      .then(renderPostMortems)
      .catch(() => {});
  })();
  `;
}
