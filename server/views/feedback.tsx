/** @jsxImportSource hono/jsx */

export function FeedbackView() {
  return (
    <>
      <section class="panel" id="accuracy-panel">
        <h3>Signal Accuracy</h3>
        <div id="accuracy-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="correlations-panel">
        <h3>Signal × Position Correlation</h3>
        <div id="correlations-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="post-mortems-panel">
        <h3>Post-Mortems</h3>
        <div id="post-mortems-body">
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

    function renderCorrelations(data) {
      var el = document.getElementById('correlations-body');
      if (!data || !data.correlations || data.correlations.length === 0) {
        el.innerHTML = '<div class="muted">No signals recorded yet.</div>';
        return;
      }

      var summary = data.summary || {};
      var accCls = summary.accuracy >= 60 ? 'positive' : 'negative';
      var html = '<div class="accuracy-summary" style="margin-bottom:1rem">';
      html += '<span>Signal accuracy: </span>';
      html += '<span class="accuracy-score ' + accCls + '">' + summary.accuracy + '%</span>';
      html += '<span class="muted"> (' + summary.accurate + '/' + summary.total + ' buy/sell signals with positions)</span>';
      html += '</div>';

      html += '<table class="data-table" style="font-size:0.85em"><thead><tr>';
      html += '<th>Ticker</th><th>Latest Signal</th><th>Platform</th>';
      html += '<th>Position</th><th>Entry</th><th>P&amp;L</th><th>Signal Outcome</th>';
      html += '</tr></thead><tbody>';

      for (var i = 0; i < data.correlations.length; i++) {
        var c = data.correlations[i];
        var p = c.position;
        var sCls = c.signalOutcome.indexOf('success') !== -1 ? 'positive' :
                   c.signalOutcome.indexOf('failure') !== -1 ? 'negative' :
                   c.signalOutcome === 'hold' ? 'status-hold' : 'muted';
        var pnlCls = c.outcomePct != null ? (c.outcomePct >= 0 ? 'positive' : 'negative') : 'muted';
        var pnlStr = c.outcomePct != null ? (c.outcomePct >= 0 ? '+' : '') + c.outcomePct.toFixed(1) + '%' : '—';

        html += '<tr>';
        html += '<td class="ticker">' + c.ticker + '</td>';
        html += '<td class="status-' + (c.latestSignal.includes('buy') ? 'buy' : c.latestSignal.includes('sell') ? 'sell' : 'hold') + '">' + c.latestSignal + '</td>';
        html += '<td><span class="platform-tag">' + (c.signals[0] && c.signals[0].platform ? c.signals[0].platform : 'unknown') + '</span></td>';
        if (p) {
          html += '<td>' + p.quantity + ' shares @ \u00a3' + p.avg_cost.toFixed(2) + ' <span class="muted">(GBP)</span></td>';
          html += '<td>' + p.entry_date + '</td>';
          html += '<td class="pnl-cell ' + pnlCls + '" style="font-family:Datatype,monospace;font-feature-settings:\'calt\'1,\'liga\'1">' + pnlStr + '</td>';
        } else {
          html += '<td class="muted">—</td><td class="muted">—</td><td class="muted">—</td>';
        }
        html += '<td class="' + sCls + '">' + c.signalOutcome + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
      el.innerHTML = html;
    }

    fetch('/api/feedback/with-positions')
      .then(function(r) { return r.json(); })
      .then(renderCorrelations)
      .catch(function() {
        document.getElementById('correlations-body').innerHTML = '<div class="muted">Failed to load correlations</div>';
      });

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
