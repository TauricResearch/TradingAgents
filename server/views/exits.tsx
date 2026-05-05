/** @jsxImportSource hono/jsx */

export function ExitsView() {
  return (
    <>
      <section class="panel" id="exits-panel">
        <h3>Exit Plans</h3>
        <div
          id="exits-body"
          hx-get="/api/positions/exits/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>
    </>
  )
}

