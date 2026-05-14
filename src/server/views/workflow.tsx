/**
 * Workflow view — shell that loads /api/workflow/html via HTMX.
 */

/** @jsxImportSource hono/jsx */

export function WorkflowView() {
  return (
    <>
      <h2>Workflow</h2>
      <div
        id="workflow-wrapper"
        hx-get="/api/workflow/html"
        hx-target="this"
        hx-trigger="load"
      >
        <div class="workflow-loading">Loading…</div>
      </div>
    </>
  )
}
