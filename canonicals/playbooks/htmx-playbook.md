# HTMX and Hono View Rendering Playbook

Establish definitive standards for structuring server-rendered HTML views using Hono, JSX, and HTMX interactions.

## Prerequisites / Context

This playbook governs the structure of all HTML-returning endpoints and associated client-side assets. Compliance is enforced via build gates (`just check`).

The architecture mandates a three-layer pattern for HTML-returning routes:
1.  `server/lib/{route}-data.ts`: Data fetching, transformation, and caching logic.
2.  `server/views/{component}.tsx`: Presentation-only JSX components.
3.  `server/routes/{route}.tsx`: Thin route handlers wiring data to JSX and handling response type.

## Standards & Patterns

### 1. Route File Extensions

Always use the `.tsx` extension for route files that return JSX, even if they contain no JSX themselves, to ensure correct parsing by tooling.

### 2. Data Extraction Before Presentation

Always extract data-fetching and transformation logic into dedicated files within `server/lib/` before writing the corresponding JSX view component.

**Pattern:**
```typescript
// server/lib/signals-data.ts
export async function fetchSignalsWithHistory(
  ticker: string | undefined,
  platform: string | undefined,
): Promise<{ signals: Signal[]; priceData: Map<string, PriceWithHistory> }> {
  // ... data logic ...
}
```

### 3. JSX Component Structure

Define presentation logic exclusively in JSX components within `server/views/`.

**Pattern:**
```tsx
// server/views/signals-view.tsx
export function SignalsViewHtml({ signals, priceData }: Props) {
  return (
    <table id="signals-table">
      <tbody>
        {signals.map((s) => (
          <SignalRow signal={s} priceData={priceData} />
        ))}
      </tbody>
    </table>
  );
}
```

### 4. Thin Route Handlers

Route handlers must only orchestrate data fetching and response rendering.

**Pattern:**
```tsx
// server/routes/signals.tsx
import { SignalsViewHtml } from "../views/signals-view.tsx";

signalsRouter.get("/view/html", async (c) => {
  const { signals, priceData } = await fetchSignalsWithHistory(...);
  return c.html(<SignalsViewHtml signals={signals} priceData={priceData} />);
});
```

### 5. JSX Attribute Syntax

Adhere strictly to JSX conventions for HTML attributes:
*   Use **camelCase** for hyphenated or lowercase HTML attributes.
    *   Use `colSpan={7}` instead of `<td colspan="7">`.
*   The `style` attribute accepts a **string value**, not a React-style object.
    *   Use `<div style="background:#fff3cd;color:#1a1a2e">`.

### 6. DOCTYPE and Quirks Mode Prevention

Hono's `c.html()` does not emit `<!DOCTYPE html>`, forcing browsers into Quirks Mode.

*   For **full-page responses** (direct navigation), wrap the rendered JSX in `renderHtml()` to prepend the DOCTYPE declaration.
*   For **HTMX partial responses**, use `c.html()` directly, as no DOCTYPE is required.

**Implementation:**
```typescript
function renderHtml(html: string): Response {
  return new Response(`<!DOCTYPE html>\n${html}`, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
```

### 7. Page vs. Partial Rendering Utility

Use the `pageOrPartial` utility function in page routes to conditionally serve a full page or an HTMX partial.

```ts
function pageOrPartial(c: Context, view: any): Response | Promise<Response> {
  const isHtmx = c.req.header("HX-Request") === "true";
  if (isHtmx) return c.html(view);           // Partial: no Layout, no DOCTYPE
  return renderFullPage(<Layout>{view}</Layout>);  // Full page: Layout + DOCTYPE
}
```

### 8. HTMX Interaction Strategy

Use HTMX exclusively for requests that return HTML content intended for DOM swapping.

*   **Do not** use HTMX directives (`hx-get`, `hx-swap`) on endpoints that return `application/json`.
*   Use standard JavaScript `fetch()` for JSON APIs.

### 9. Dynamic Content Swapping

When dynamically injecting HTML content via `element.innerHTML = dynamicHtmlString`:

*   **Always** use data attributes for event binding, not inline `onclick` attributes.
*   Bind handlers via a single, globally wired event delegation function (`wireActions`).

**Binding Pattern:**
```tsx
// ✅ Correct: data attributes for runtime variables
html += '<button data-action="analyzeTicker" data-ticker="' + item.ticker + '">Analyze</button>';
```

**Delegation Handler Requirement:** Call the event delegation setup function (`wireActions()`) immediately after any assignment to `element.innerHTML` that injects new elements with `data-action`.

### 10. HTML String Sanitization

Sanitize all dynamic content inserted into HTML text nodes or attribute values when using string concatenation to prevent XSS and attribute breakage.

*   Define and use an HTML escaping utility (`_esc`).
*   Escape angle brackets (`<`, `>`) and ampersands (`&`).
*   Escape quotes (`"`, `'`) within attribute values.

**Pattern:**
```tsx
var _esc = function(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');};
html += '<div class="card-thesis">' + _esc(item.thesis) + '</div>';
html += '<button data-ticker="' + _esc(item.ticker) + '">Analyze</button>';
```

### 11. Database Input Sanitization

Sanitize all user-facing or AI-generated text fields before writing to the database to prevent secret leakage.

*   Apply `sanitizeForDb()` from `server/lib/sanitize.ts` to all relevant text inputs (e.g., thesis, notes) prior to database execution.

### 12. Client-Side JavaScript Management

All non-trivial client-side JavaScript must reside in external files within `server/static/scripts/`.

*   Load common utilities once in `Layout.tsx` via `<script src="/static/scripts/common.js" />`.
*   Load view-specific scripts once per view component via `<script src="/static/scripts/view-name.js" />`.
*   **Never** use inline `<script>` tags or `dangerouslySetInnerHTML` for JavaScript logic.

### 13. Static Asset Serving Configuration

Configure Hono's static file serving middleware using an absolute root path and path rewriting.

```typescript
import { serveStatic } from "hono/bun";
import { resolve } from "node:path";

const staticDir = resolve(import.meta.dir, "static");

app.use("/static/*", serveStatic({
  root: staticDir,
  rewriteRequestPath: (path) => path.replace(/^\/static/, ""),
  onFound: (_path, c) => {
    c.header("Cache-Control", "public, max-age=31536000, immutable");
  },
}));
```

### 14. Unicode Character Handling in Injected JS

When injecting JavaScript strings via `dangerouslySetInnerHTML`, never use Python string escape sequences like `'\\n'` or `'\\u20AC'`. These sequences are rendered literally, corrupting the JS syntax.

*   Write actual UTF-8 bytes for special characters (e.g., `€` instead of `\u20AC`).
*   Use regex literals (`/\s/`) instead of string literals (`'\\s'`) for patterns.
*   Use `String.fromCharCode(code)` for characters that must be constructed dynamically.

### 15. Datatype Font Rendering

If rendering content styled with the Datatype font, ensure the containing element has the required CSS feature settings applied: `font-feature-settings: 'calt' 1, 'liga' 1`.

## Forbidden Patterns

| Pattern | Rationale | Correct Alternative |
| :--- | :--- | :--- |
| Inline `<script>{...}</script>` | Hono HTML-encodes quotes, breaking JS syntax. | Extract to `server/static/scripts/*.js` and use `<script src>`. |
| `dangerouslySetInnerHTML={{ __html: ... }}` for scripts | Non-cacheable, duplicates code, bypasses linting. | Extract to external JS file. |
| `hx-get` on JSON endpoints | HTMX swaps raw JSON into the DOM, breaking layout. | Use standard `fetch()` for JSON APIs. |
| React-style `style={{...}}` | Hono JSX requires string values for the `style` attribute. | Use `<div style="color:red;">`. |
| HTML attribute lowercase (`colspan`) | JSX requires camelCase for compatibility. | Use `colSpan={value}`. |
| Inline `onclick="FUNC(' + var + ')"` | Causes complex escaping issues when building HTML via string concatenation. | Use `data-action` attributes with global event delegation. |
| Defining helpers inside loops | `var` hoisting causes helpers to be `undefined` when first called. | Define helper functions outside the loop scope. |

## Edge Cases

### `var` Hoisting in Loops

When using `var` to define helper functions inside a `for` loop, hoisting means the variable exists but is `undefined` until the assignment executes. If the helper is called earlier in the same loop body, it throws.

```js
// ❌ Broken — _e defined inside loop, called before assignment
for (const item of items) {
  html += _e(item.text);   // _e is undefined here
  var _e = function(s){...};  // hoisted but unassigned
}

// ✅ Correct — helper defined outside the loop
var _e = function(s){...};
for (const item of items) {
  html += _e(item.text);  // OK
}
```

### String `split('\n')` vs Actual Newlines

When building HTML strings dynamically, a literal backslash-n in a JavaScript string is two characters (`\` + `n`), not a newline (`\n`).

```js
// ❌ Literal backslash+n — not a newline
var short = item.lesson.split('\n')[0];  // looks for two chars: \ and n

// ✅ Regex with real newline or template literal
var short = item.lesson.split(/\r?\n/)[0];  // matches actual \n or \r\n
```

## Quick Reference

| Pattern | Trigger | Action |
| :--- | :--- | :--- |
| Direct Browser Navigation | No `HX-Request` header | Use `pageOrPartial` → `renderHtml()` → Full Page |
| HTMX Request | `HX-Request: true` header present | Use `pageOrPartial` → `c.html()` → Partial View |
| JSON API Interaction | Endpoint returns `application/json` | Use JavaScript `fetch()` |
| Dynamic HTML Injection | Building HTML via string concatenation | Use `_esc()` utility on all dynamic text/attributes. |
| Client Scripting | Any non-trivial client behavior required | Extract to `server/static/scripts/*.js` and load via `<script src>`. |

## Validation / How to Verify Compliance

1.  **Build Gate Check:** Execute `just check`. This validates against banned inline script patterns in view files.
2.  **Static Asset Check:** Verify that all JavaScript logic is external. Inspect `server/views/*.tsx` for any `<script>` tags or `dangerouslySetInnerHTML` blocks containing JavaScript logic.
3.  **DOCTCYPE Check:** Inspect the source of any direct URL navigation (e.g., `/portfolio`) to confirm the response begins with `<!DOCTYPE html>`.
4.  **Static Serving Check:** Verify asset serving configuration by checking HTTP response codes for static files:
    ```bash
    curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/static/style.css
    # Expected output: 200
    ```
5.  **Sanitization Check:** Review database interaction points in route handlers and seed scripts to confirm `sanitizeForDb()` is applied before writing user/AI content.