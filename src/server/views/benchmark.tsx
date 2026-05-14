/**
 * Benchmark view — shell that loads /api/benchmark/table via HTMX.
 */

/** @jsxImportSource hono/jsx */

export function BenchmarkView() {
  return (
    <>
      <section class="panel" id="benchmark-panel">
        <h3>Benchmark — Portfolio vs. {process.env.BENCHMARK || "VWCE.DE"}</h3>
        <div
          id="benchmark-body"
          hx-get="/api/benchmark/table"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>
    </>
  )
}

