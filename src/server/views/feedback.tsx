/** @jsxImportSource hono/jsx */

export function FeedbackView() {
  return (
    <>
      <section class="panel" id="accuracy-panel">
        <h3>Signal Accuracy</h3>
        <div
          id="accuracy-body"
          hx-get="/api/feedback/accuracy/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="correlations-panel">
        <h3>Signal × Position Correlation</h3>
        <div
          id="correlations-body"
          hx-get="/api/feedback/with-positions/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="post-mortems-panel">
        <h3>Post-Mortems</h3>
        <div
          id="post-mortems-body"
          hx-get="/api/feedback/post-mortems/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>
    </>
  )
}

