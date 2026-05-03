/** @jsxImportSource hono/jsx */

export function BenchmarkView() {
  return (
    <>
      <section class="panel" id="benchmark-panel">
        <h3>Benchmark — Portfolio vs. {process.env.BENCHMARK || "VWCE.DE"}</h3>
        <div id="benchmark-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script dangerouslySetInnerHTML={{ __html: benchmarkScript() }} />
    </>
  );
}

function benchmarkScript(): string {
  return `
  (function() {
    function renderBenchmark(result) {
      const el = document.getElementById('benchmark-body');
      if (!result || result.error) {
        el.innerHTML = '<div class="error-card"><strong>Benchmark error</strong><br>' +
          (result ? result.error : 'Unknown error') + '</div>';
        return;
      }

      let html = '<div class="benchmark-summary">';
      html += '<div>Portfolio value: €' + result.currentValue.toFixed(2) + '</div>';
      html += '<div>Benchmark: ' + result.ticker + '</div>';
      html += '</div>';

      if (result.periodReturns && result.periodReturns.length > 0) {
        html += '<table class="data-table"><thead><tr>';
        html += '<th>Period</th><th>Portfolio</th><th>Benchmark</th><th>Alpha</th>';
        html += '</tr></thead><tbody>';

        for (const r of result.periodReturns) {
          const pClass = r.portfolioPct >= 0 ? 'positive' : 'negative';
          const bClass = r.benchmarkPct >= 0 ? 'positive' : 'negative';
          const aClass = r.alpha >= 0 ? 'positive' : 'negative';

          html += '<tr>';
          html += '<td>' + r.period + '</td>';
          html += '<td class="' + pClass + '">' + (r.portfolioPct >= 0 ? '+' : '') + r.portfolioPct.toFixed(1) + '%</td>';
          html += '<td class="' + bClass + '">' + (r.benchmarkPct >= 0 ? '+' : '') + r.benchmarkPct.toFixed(1) + '%</td>';
          html += '<td class="' + aClass + '">' + (r.alpha >= 0 ? '+' : '') + r.alpha.toFixed(1) + '%</td>';
          html += '</tr>';
        }
        html += '</tbody></table>';
      } else {
        html += '<div class="muted">Insufficient benchmark data (need at least 3 months)</div>';
      }

      el.innerHTML = html;
    }

    fetch('/api/benchmark')
      .then(r => r.json())
      .then(renderBenchmark)
      .catch(err => {
        document.getElementById('benchmark-body').innerHTML =
          '<div class="error-card"><strong>Benchmark error</strong><br>' + err.message + '</div>';
      });
  })();
  `;
}
