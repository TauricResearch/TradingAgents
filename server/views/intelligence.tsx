/** @jsxImportSource hono/jsx */

export function IntelligenceView() {
  return (
    <>
      <section class="panel" id="portfolio-hero">
        <h3>Portfolio Overview</h3>
        <div
          id="intel-body"
          hx-get="/api/portfolio/intelligence/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading portfolio intelligence…</div>
        </div>
      </section>
    </>
  )
}

