/** @jsxImportSource hono/jsx */

export function GovernanceView() {
  return (
    <>
      <section class="panel" id="governance-panel">
        <h3>Governance — Risk Rules</h3>
        <div id="rules-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="violations-panel">
        <h3>Violations</h3>
        <div id="violations-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: governanceScript() }} />
    </>
  );
}

function governanceScript(): string {
  return `
  (function() {
    function renderRules(rules) {
      const el = document.getElementById('rules-body');
      let html = '<table class="data-table"><thead><tr>';
      html += '<th>Rule</th><th>Limit</th><th>Description</th>';
      html += '</tr></thead><tbody>';
      for (const r of rules) {
        html += '<tr>';
        html += '<td>' + r.name + '</td>';
        html += '<td>' + r.limit + (r.unit === '%' ? '%' : r.unit === 'count' ? '' : r.unit) + '</td>';
        html += '<td class="muted">' + r.description + '</td>';
        html += '</tr>';
      }
      html += '</tbody></table>';
      el.innerHTML = html;
    }

    function renderCheck(result) {
      const el = document.getElementById('violations-body');
      if (result.note) {
        el.innerHTML = '<div class="muted">' + result.note + '</div>';
        return;
      }

      let html = '<div class="governance-summary">';
      html += '<div>Portfolio: \u00a3' + result.portfolioValue.toFixed(2) + ' <span class="muted">(base: GBP)</span></div>';
      html += '<div>Cash: ' + result.cashPct.toFixed(1) + '%</div>';
      html += '</div>';

      // Violations
      if (result.violations && result.violations.length > 0) {
        html += '<h4>⚠️ Violations</h4>';
        for (const v of result.violations) {
          const cls = v.severity === 'breach' ? 'violation-breach' : 'violation-warn';
          html += '<div class="' + cls + '">';
          html += '<strong>' + v.rule.name + '</strong>: ' + v.detail;
          html += '</div>';
        }
      } else {
        html += '<div class="ok">✅ All rules satisfied</div>';
      }

      // Rebalance suggestions
      if (result.suggestions && result.suggestions.length > 0) {
        html += '<h4>Rebalance Suggestions</h4>';
        html += '<table class="data-table"><thead><tr>';
        html += '<th>Ticker</th><th>Action</th><th>Current</th><th>Target</th><th>Drift</th>';
        html += '</tr></thead><tbody>';
        for (const s of result.suggestions) {
          html += '<tr>';
          html += '<td class="ticker">' + s.ticker + '</td>';
          html += '<td class="' + (s.action === 'trim' ? 'negative' : 'positive') + '">' + s.action.toUpperCase() + '</td>';
          html += '<td>' + s.currentWeight.toFixed(1) + '%</td>';
          html += '<td>' + s.targetWeight.toFixed(1) + '%</td>';
          html += '<td>' + s.delta.toFixed(1) + 'pp</td>';
          html += '</tr>';
        }
        html += '</tbody></table>';
      }

      el.innerHTML = html;
    }

    // Render rules
    fetch('/api/governance/rules')
      .then(r => r.json())
      .then(renderRules)
      .catch(() => {});

    // Render check — use portfolio/intelligence for GBP-consistent values
    fetch('/api/portfolio/intelligence')
      .then(r => r.json())
      .then(function(data) {
        var pf = data.portfolio || {};
        var gov = data.governance || {};
        var el = document.getElementById('violations-body');
        var html = '<div class="governance-summary">';
        html += '<div>Portfolio: \u00a3' + (pf.total_value_gbp || 0).toFixed(2) + ' <span class="muted">(base: GBP)</span></div>';
        html += '<div>Cash: ' + (pf.cash_pct || 0).toFixed(1) + '%</div>';
        html += '<div>Positions: ' + (pf.positions_count || 0) + '</div>';
        html += '</div>';

        if (gov.violations && gov.violations.length > 0) {
          html += '<h4>\u26a0\ufe0f Violations</h4>';
          for (var vi = 0; vi < gov.violations.length; vi++) {
            var v = gov.violations[vi];
            var cls = v.severity === 'breach' ? 'violation-breach' : 'violation-warn';
            html += '<div class="' + cls + '">';
            html += '<strong>' + v.rule.name + '</strong>: ' + v.detail;
            html += '</div>';
          }
        } else {
          html += '<div class="ok">\u2705 All rules satisfied</div>';
        }

        if (gov.suggestions && gov.suggestions.length > 0) {
          html += '<h4 style="margin-top:1rem">Rebalance Suggestions</h4>';
          html += '<table class="data-table" style="font-size:0.85em"><thead><tr>';
          html += '<th>Ticker</th><th>Action</th><th>Current</th><th>Target</th><th>Drift</th>';
          html += '</tr></thead><tbody>';
          for (var si = 0; si < gov.suggestions.length; si++) {
            var s = gov.suggestions[si];
            html += '<tr>';
            html += '<td class="ticker">' + s.ticker + '</td>';
            html += '<td class="' + (s.action === 'trim' ? 'negative' : 'positive') + '">' + s.action.toUpperCase() + '</td>';
            html += '<td>' + (s.currentWeight || 0).toFixed(1) + '%</td>';
            html += '<td>' + (s.targetWeight || 0).toFixed(1) + '%</td>';
            html += '<td>' + (s.delta || 0).toFixed(1) + 'pp</td>';
            html += '</tr>';
          }
          html += '</tbody></table>';
        }

        el.innerHTML = html;
      })
      .catch(function(err) {
        document.getElementById('violations-body').innerHTML = '<div class="muted">Failed to load governance data</div>';
      });
  })();
  `;
}
