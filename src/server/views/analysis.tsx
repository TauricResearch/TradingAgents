/** @jsxImportSource hono/jsx */

export function AnalysisView() {
  return (
    <>
      <section class="panel">
        <h3>Run New Analysis</h3>
        <form id="analysis-form">
          <div class="form-row">
            <input name="ticker" placeholder="Ticker (e.g. TKA.DE)" required id="analysis-ticker" />
            <input name="date" type="date" id="analysis-date" />
            <select name="debates" id="analysis-debates">
              <option value="1">1 round — quick check</option>
              <option value="2">2 rounds — standard</option>
              <option value="3" selected>3 rounds — thorough</option>
              <option value="4">4 rounds — deep</option>
              <option value="5">5 rounds — exhaustive</option>
            </select>
          </div>
          <div class="form-row">
            <label><input type="checkbox" name="analysts" value="market" checked /> Market</label>
            <label><input type="checkbox" name="analysts" value="news" checked /> News</label>
            <label><input type="checkbox" name="analysts" value="fundamentals" checked /> Fundamentals</label>
          </div>
          <div id="position-context-banner" class="banner" style="display:none">
            ⚠ <span id="position-context-text" />
          </div>
          <button type="submit" id="run-analysis-btn">▶ Run Analysis</button>
        </form>
      </section>

      <section class="panel" id="analysis-progress" style="display:none">
        <h3>Live Progress</h3>
        <div id="sse-events" />
      </section>

      <section class="panel" id="analysis-output" style="display:none">
        <h3>Analysis Output</h3>
        <div id="markdown-output" />
      </section>

      <script src="/static/scripts/analysis.js" />
    </>
  );
}

