/** @jsxImportSource hono/jsx */

export function IntelligenceView() {
  return (
    <>
      <section class="panel" id="portfolio-hero">
        <div id="intel-loading" style="color:var(--text-dim)">Loading portfolio intelligence…</div>
        <div id="intel-body" style="display:none" />
      </section>

      <section class="panel" id="asset-class-panel">
        <h3>Asset Allocation</h3>
        <div id="asset-class-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="platforms-panel">
        <h3>Platform Breakdown</h3>
        <div id="platforms-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="governance-panel">
        <h3>Governance Alerts</h3>
        <div id="governance-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script src="/static/scripts/intelligence.js" />
    </>
  )
}

