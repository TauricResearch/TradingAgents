/** @jsxImportSource hono/jsx */

/**
 * About tab — project state, architecture, and quick reference.
 * Updated to reflect current working state.
 */

export function AboutView() {
  return (
    <div class="dev-dashboard">
      <section class="panel">
        <h3>System Status</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>Tab</th>
              <th>Page</th>
              <th>API</th>
              <th>Data</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            <Status tab="Portfolio"   ok page={true} data note="14 positions, live P&amp;L via /api/prices" />
            <Status tab="Analysis"    ok page={true} data note="SSE streaming, signal capture on complete" />
            <Status tab="Signals"     ok page={true} data note="37 signals, AI accuracy tracked" />
            <Status tab="History"     ok page={true} data note="4 analyses, markdown rendering" />
            <Status tab="Holdings"    ok page={true} data note="3 platforms: degiero, ibkr, test" />
            <Status tab="Workflow"    ok page={true} data note="3-column Kanban: Approved / Holdings / Pending Exit" />
            <Status tab="Exits"       ok page={true} data note="11 exit plans, live prices, two-level cache" />
            <Status tab="Prospects"   ok page={true} data note="12 prospects, HTMX form submission" />
            <Status tab="Governance"  ok page={true} data note="6 violations across platforms (per-platform rules ready)" />
            <Status tab="Benchmark"   ok page={true} data={false} note="Prices route live, portfolio value not yet wired" />
            <Status tab="Feedback"    ok page={true} data note="2 post-mortems, signal accuracy scoring" />
          </tbody>
        </table>
      </section>

      <section class="panel">
        <h3>Platform Data</h3>
        <table class="data-table">
          <thead>
            <tr><th>Platform</th><th>Positions</th><th>Type</th><th>Notes</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><code>degiero</code></td>
              <td>4 (VWCE, AAPL, MSFT, NVDA)</td>
              <td>Trading</td>
              <td class="muted">Core ETF + large-cap growth</td>
            </tr>
            <tr>
              <td><code>ibkr</code></td>
              <td>4 (AAPL 28%!, MSFT, TKA.DE, VWCE)</td>
              <td>Trading</td>
              <td class="muted">AAPL violates 15% single-name rule — governance flagged</td>
            </tr>
            <tr>
              <td><code>test</code></td>
              <td>3 (AAPL, ETH, TSLA)</td>
              <td>Edge cases</td>
              <td class="muted">Crypto (ETH), high-conviction (TSLA), multi-platform (AAPL)</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="panel">
        <h3>Key Implementation Notes</h3>
        <div class="dev-list">
          <div class="dev-item">
            <span class="tag green">LESSON</span>
            <span>Inline JS in Hono JSX views must use <code>dangerouslySetInnerHTML</code> with a plain function — not a literal script block. See <code>playbooks/htmx-playbook.md</code>.</span>
          </div>
          <div class="dev-item">
            <span class="tag green">LESSON</span>
            <span>HTMX + JSON APIs don't mix. Use <code>fetch()</code> for JSON, <code>hx-swap="none"</code> + JS handler for HTMX forms.</span>
          </div>
          <div class="dev-item">
            <span class="tag green">LESSON</span>
            <span>Never use <code>onclick</code> with JS variable interpolation. Use <code>data-action</code> + event delegation instead.</span>
          </div>
          <div class="dev-item">
            <span class="tag green">RESOLVED</span>
            <span>Exits route price fetching — parallel subprocesses now killed after 8s, two-level response cache (30s full, 60s per-ticker)</span>
          </div>
          <div class="dev-item">
            <span class="tag green">RESOLVED</span>
            <span>Flat YAML vs nested object mismatch — normalization added to <code>positions.ts</code> and <code>computeExitStatus()</code></span>
          </div>
          <div class="dev-item">
            <span class="tag green">RESOLVED</span>
            <span>HTMX <code>insertBefore</code> error — regex literals and string escapes corrupted inside <code>dangerouslySetInnerHTML</code></span>
          </div>
        </div>
      </section>

      <section class="panel">
        <h3>Next Up</h3>
        <ol class="dev-list">
          <li>Wire portfolio P&amp;L columns — connect <code>/api/prices</code> into portfolio view current values</li>
          <li>Per-platform governance rules — different limits for pension vs. trading accounts</li>
          <li>Seed script for hLedger — generate journal from DB positions once user has account credentials</li>
          <li>Analysis markdown rendering — render SSE agent reports as formatted markdown</li>
          <li>Prospects platform filter — add platform dropdown to prospects view header</li>
        </ol>
      </section>

      <section class="panel">
        <h3>Backlog</h3>
        <ul class="dev-list">
          <li>Authentication / access control</li>
          <li>Timeout handling for analyses &gt; 4 minutes (idleTimeout is 240s)</li>
          <li>Analysis history drill-down — full report with back navigation</li>
          <li>Signal accuracy tracking — correlate signals with position outcomes</li>
          <li>Portfolio vs. benchmark comparison — wire portfolio total value into benchmark route</li>
          <li>datatype.tsx JSX helper — either use or remove (currently unused)</li>
          <li>Multi-currency P&amp;L — convert all values to base currency (EUR)</li>
        </ul>
      </section>

      <section class="panel">
        <h3>Quick Commands</h3>
        <table class="data-table">
          <thead><tr><th>Command</th><th>Purpose</th></tr></thead>
          <tbody>
            <tr><td><code>bun run server/index.tsx</code></td><td>Start dashboard (port 3000)</td></tr>
            <tr><td><code>pkill -9 -f bun</code></td><td>Kill stale server processes</td></tr>
            <tr><td><code>just lint</code></td><td>Biome lint check</td></tr>
            <tr><td><code>just check</code></td><td>Full CI gate (lint + type check)</td></tr>
            <tr><td><code>just seed-db</code></td><td>Seed all test data (positions, signals, exit plans, post-mortems)</td></tr>
            <tr><td><code>just seed-test-journal</code></td><td>Generate test hLedger journal (3 platforms)</td></tr>
            <tr><td><code>TA_DASHBOARD_PORT=8080 bun run server/index.tsx</code></td><td>Start on different port</td></tr>
            <tr><td><code>just analyze TKA.DE</code></td><td>Run CLI analysis on specific ticker</td></tr>
          </tbody>
        </table>
      </section>

      <section class="panel">
        <h3>Data Layers</h3>
        <table class="data-table">
          <thead><tr><th>Layer</th><th>Location</th><th>Owner</th><th>Notes</th></tr></thead>
          <tbody>
            <tr>
              <td>Positions</td>
              <td><code>./portfolio.db</code> + <code>~/.tradingagents/positions/</code></td>
              <td>Dashboard DB + YAML exit plans</td>
              <td class="muted">SQLite for state, YAML for exit plan detail</td>
            </tr>
            <tr>
              <td>Accounting</td>
              <td><code>~/.hledger.journal</code></td>
              <td>hLedger (external)</td>
              <td class="muted">Canonical cash/asset balances; convention: <code>assets:platform:account</code></td>
            </tr>
            <tr>
              <td>Signals</td>
              <td><code>./portfolio.db</code> (signals table)</td>
              <td>Dashboard DB</td>
              <td class="muted">Captured from analysis decisions; linked to positions</td>
            </tr>
            <tr>
              <td>Analyses</td>
              <td><code>./portfolio.db</code> (analyses table)</td>
              <td>Dashboard DB</td>
              <td class="muted">JSON blob per analysis; markdown stored separately</td>
            </tr>
            <tr>
              <td>Memory</td>
              <td><code>~/.tradingagents/memory/trading_memory.md</code></td>
              <td>TradingAgents (external)</td>
              <td class="muted">Injected as position context to agents via wrap.py</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="panel">
        <h3>Reference</h3>
        <p class="muted"><code>ARCHITECTURE.md</code> — full system diagram, route table, SSE event schema</p>
        <p class="muted"><code>AGENTS.md</code> — coding rules, platform conventions, data-action delegation pattern</p>
        <p class="muted"><code>playbooks/htmx-playbook.md</code> — HTMX lessons, dangerouslySetInnerHTML gotchas, backslash escape rules</p>
        <p class="muted"><code>playbooks/just-playbook.md</code> — Justfile conventions and task recipes</p>
      </section>
    </div>
  );
}

function Status(props: {
  tab: string;
  ok: boolean;
  page: boolean;
  data: boolean;
  note: string;
}) {
  const status = props.ok && props.page && props.data
    ? { cls: "ok", label: "Working" }
    : props.ok && props.page
      ? { cls: "partial", label: "Partial" }
      : { cls: "broken", label: "Broken" };

  return (
    <tr>
      <td>{props.tab}</td>
      <td>{props.page ? "ok" : "err"}</td>
      <td>{props.ok ? "ok" : "err"}</td>
      <td>{props.data ? "ok" : "err"}</td>
      <td>
        <span class={`status-badge ${status.cls}`}>{status.label}</span>
        {" "}
        <span class="muted">— {props.note}</span>
      </td>
    </tr>
  );
}