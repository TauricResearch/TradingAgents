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
        <link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
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
            <button
              hx-get="/history"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              History
            </button>
            <button
              hx-get="/holdings"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Holdings
            </button>
            <button
              hx-get="/exits"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Exits
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
