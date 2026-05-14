/**
 * Signals view — shell that loads /api/signals/view/html via HTMX.
 */

/** @jsxImportSource hono/jsx */

export function SignalsView() {
  return (
    <>
      <section class="panel" id="signals-panel">
        <h3>Signal History</h3>
        <div
          id="signals-wrapper"
          hx-get="/api/signals/view/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>
    </>
  )
}

