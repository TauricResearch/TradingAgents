/** @jsxImportSource hono/jsx */
/**
 * VIEW SCAFFOLD — copy this to src/server/views/[name].tsx
 *
 * Rules for new views:
 * 1. If the view just displays data: use hx-get to an /api/.../html route.
 *    NO client-side JS needed.
 * 2. If the view needs client interactivity (SSE, complex forms, drag-drop):
 *    Put the JS in src/server/static/scripts/[name].js and reference with <script src>.
 * 3. NEVER use dangerouslySetInnerHTML for scripts.
 * 4. NEVER define function xxxScript() in a view file.
 * 5. NEVER use <script>{`...`}</script> literal blocks.
 *
 * This scaffold shows the HTMX partial pattern (default).
 * For the external-JS pattern, see playbooks/htmx-playbook.md.
 */

export function NewView() {
  return (
    <>
      <section class="panel">
        <h3>Page Title</h3>
        <div
          hx-get="/api/ROUTE/html"
          hx-target="this"
          hx-trigger="load"
        >
          <div class="muted">Loading…</div>
        </div>
      </section>
    </>
  );
}
