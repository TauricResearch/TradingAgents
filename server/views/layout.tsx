/** @jsxImportSource hono/jsx */

import type { PropsWithChildren } from "hono/jsx";

interface LayoutProps extends PropsWithChildren {
  testMode?: boolean;
}

export function Layout(props: LayoutProps) {
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
        {props.testMode && (
          <div style="background:#f59e0b;color:#000;text-align:center;padding:4px;font-size:0.75em;font-weight:700;letter-spacing:0.05em">
            TEST MODE — data is isolated from production
          </div>
        )}
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
              hx-get="/intelligence"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Intelligence
            </button>
            <button
              hx-get="/workflow"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Workflow
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
            <button
              hx-get="/prospects"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Prospects
            </button>
            <button
              hx-get="/governance"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Governance
            </button>
            <button
              hx-get="/benchmark"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Benchmark
            </button>
            <button
              hx-get="/feedback"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              Feedback
            </button>
            <button
              hx-get="/about"
              hx-target="#content"
              hx-push-url="true"
              class="tab"
            >
              About
            </button>
          </nav>
        </header>
        <main id="content">{props.children}</main>
        <script
          dangerouslySetInnerHTML={{
            __html: `
function syncTab() {
  var path = window.location.pathname;
  document.querySelectorAll('.tab').forEach(function(tab) {
    tab.classList.toggle('active', tab.getAttribute('hx-get') === path);
  });
}
syncTab();
document.body.addEventListener('htmx:afterSwap', syncTab);`,
          }}
        />
      </body>
    </html>
  );
}
