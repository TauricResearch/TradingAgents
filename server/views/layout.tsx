/** @jsxImportSource hono/jsx */

import type { PropsWithChildren } from "hono/jsx";

export function Layout(props: PropsWithChildren) {
  return (
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>TradingAgents Dashboard</title>
        <link rel="stylesheet" href="/static/style.css" />
        <script src="https://unpkg.com/htmx.org@2.0.4" />
      </head>
      <body>
        <header>
          <h1>TradingAgents</h1>
          <nav id="tabs">
            <button
              hx-get="/portfolio"
              hx-target="#content"
              hx-push-url="true"
              class="tab active"
            >
              Portfolio
            </button>
            <button
              hx-get="/analyze"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Analysis
            </button>
            <button
              hx-get="/signals"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Signals
            </button>
          </nav>
        </header>
        <main id="content">{props.children}</main>
        <script
          dangerouslySetInnerHTML={{
            __html: `
document.body.addEventListener('htmx:afterSwap', function() {
  const path = window.location.pathname;
  document.querySelectorAll('.tab').forEach(function(tab) {
    tab.classList.toggle('active', tab.getAttribute('hx-get') === path);
  });
});`,
          }}
        />
      </body>
    </html>
  );
}
