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

      <script src="/static/scripts/feedback.js" />
    </>
  );
}

