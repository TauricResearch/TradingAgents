/** @jsxImportSource hono/jsx */

export function HistoryView() {
  return (
    <>
      <section class="panel">
        <h3>Past Analyses</h3>
        <table id="analyses-table">
          <thead>
            <tr><th class="date-col">Date</th><th>Ticker</th><th></th></tr>
          </thead>
          <tbody id="analyses-body">
            <tr><td colspan={5} class="muted">Loading…</td></tr>
          </tbody>
        </table>
      </section>

      <section class="panel" id="analysis-detail" style="display:none">
        <button class="btn-sm" data-action="closeAnalysisDetail">← Back to list</button>
        <div id="analysis-card"></div>
        <div id="analysis-full" style="display:none"><div id="analysis-content"></div></div>
      </section>

      <script src="/static/scripts/history.js" />
    </>
  );
}

