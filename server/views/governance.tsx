/** @jsxImportSource hono/jsx */

export function GovernanceView() {
  return (
    <>
      <section class="panel" id="governance-panel">
        <h3>Governance — Risk Rules</h3>
        <div
          id="rules-body"
          hx-get="/api/governance/rules/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="violations-panel">
        <h3>Violations</h3>
        <div
          id="violations-body"
          hx-get="/api/governance/violations/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>
    </>
  )
}

