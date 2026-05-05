/** @jsxImportSource hono/jsx */

export function GovernanceView() {
  return (
    <>
      <section class="panel" id="governance-panel">
        <h3>Governance — Risk Rules</h3>
        <div id="rules-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <section class="panel" id="violations-panel">
        <h3>Violations</h3>
        <div id="violations-body">
          <div class="muted">Loading…</div>
        </div>
      </section>

      <script src="/static/scripts/governance.js" />
    </>
  );
}
