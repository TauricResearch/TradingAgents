/**
 * Feedback view — shell that loads /api/feedback/html via HTMX.
 */

/** @jsxImportSource hono/jsx */

export function FeedbackView() {
  return (
    <>
      <section class="panel" id="feedback-overview">
        <h3>Feedback Loop</h3>
        <div class="muted">
          Track signal accuracy and learn from exited positions.
          Post-mortems are generated when you close a position and record the outcome.
        </div>
      </section>

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
