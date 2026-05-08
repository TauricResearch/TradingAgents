/** @jsxImportSource hono/jsx */
/**
 * Lab: Graphics Rendering Testbed for Hono JSX
 *
 * Systematically tests every category of non-ASCII symbol used across the
 * TradingAgents dashboard. Each category shows:
 *   - BROKEN: raw \uXXXX in JSX text (renders literally)
 *   - WORKING: literal character in JSX text
 *   - WORKING: JS expression {"\uXXXX"}
 *   - WORKING: HTML entity
 *
 * WHY THIS MATTERS:
 *   In Hono JSX, text between tags is emitted as literal HTML. JS string
 *   escape sequences (\u00a3, \u2192, etc.) are NOT interpreted. They are
 *   emitted as six-character strings: \ u 0 0 a 3.
 *
 *   Only inside { } expressions does JS string processing occur.
 *
 * Visit: /lab/currency
 */

import { Hono } from "hono"

const app = new Hono()

// ── Constants for test expressions ────────────────────────────────────────

const esc = {
  pound: "\u00a3",
  arrowRight: "\u2192",
  arrowLeft: "\u2190",
  play: "\u25b6",
  warning: "\u26a0",
  warningEmoji: "\u26a0\ufe0f",
  check: "\u2713",
  checkGreen: "\u2705",
  cross: "\u2715",
  diamondOpen: "\u25C7",
  diamondSolid: "\u25C6",
  clock: "\u23F1",
  emDash: "\u2014",
  dot: "\u00b7",
  plusMinus: "\u00b1",
}

const lit = {
  pound: "£",
  dollar: "$",
  euro: "€",
  yen: "¥",
  arrowRight: "→",
  arrowLeft: "←",
  play: "▶",
  warning: "⚠",
  warningEmoji: "⚠️",
  check: "✓",
  checkGreen: "✅",
  cross: "✕",
  diamondOpen: "◇",
  diamondSolid: "◆",
  clock: "⏱",
  emDash: "—",
  dot: "·",
  plusMinus: "±",
}

// ── Component: a single test row ──────────────────────────────────────────

function TestRow(props: {
  label: string
  desc: string
  expected: string
  broken: any
  literal: any
  expr: any
  entity: any
}) {
  return (
    <div class="test-row" style="border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0;">
      <h4 style="margin: 0 0 0.5rem;">{props.label}</h4>
      <p style="margin: 0 0 0.5rem; color: #666; font-size: 0.9em;">{props.desc}</p>
      <p style="margin: 0 0 0.5rem; font-family: monospace; font-size: 0.85em; color: #888;">
        Expected: <strong>{props.expected}</strong>
      </p>
      <div style="display: grid; grid-template-columns: 120px 1fr 1fr 1fr 1fr; gap: 0.5rem; font-size: 0.9em;">
        <div style="font-weight: bold; color: #555;">Method</div>
        <div style="font-weight: bold; color: #555;">Render</div>
        <div style="font-weight: bold; color: #555;">Source</div>
        <div style="font-weight: bold; color: #555;">Verdict</div>
        <div style="font-weight: bold; color: #555;">Used in views</div>

        <div style="color: #ef4444;">BROKEN</div>
        <div style="font-family: Datatype, monospace; background: #fef2f2; padding: 0.25rem; border-radius: 4px;">{props.broken}</div>
        <div style="font-family: monospace; font-size: 0.8em; color: #888;">&lt;span&gt;\\uXXXX&lt;/span&gt;</div>
        <div style="color: #ef4444; font-weight: bold;">Renders literally</div>
        <div style="font-size: 0.8em; color: #666;">portfolio-summary, intel-hero, workflow-kanban</div>

        <div style="color: #22c55e;">WORKING</div>
        <div style="font-family: Datatype, monospace; background: #f0fdf4; padding: 0.25rem; border-radius: 4px;">{props.literal}</div>
        <div style="font-family: monospace; font-size: 0.8em; color: #888;">&lt;span&gt;£&lt;/span&gt;</div>
        <div style="color: #22c55e; font-weight: bold;">Correct</div>
        <div style="font-size: 0.8em; color: #666;">Preferred for JSX text</div>

        <div style="color: #22c55e;">WORKING</div>
        <div style="font-family: Datatype, monospace; background: #f0fdf4; padding: 0.25rem; border-radius: 4px;">{props.expr}</div>
        <div style="font-family: monospace; font-size: 0.8em; color: #888;">&lt;span&gt;{"\\uXXXX"}&lt;/span&gt;</div>
        <div style="color: #22c55e; font-weight: bold;">Correct</div>
        <div style="font-size: 0.8em; color: #666;">Useful for dynamic values</div>

        <div style="color: #22c55e;">WORKING</div>
        <div style="font-family: Datatype, monospace; background: #f0fdf4; padding: 0.25rem; border-radius: 4px;">{props.entity}</div>
        <div style="font-family: monospace; font-size: 0.8em; color: #888;">&lt;span&gt;&amp;pound;&lt;/span&gt;</div>
        <div style="color: #22c55e; font-weight: bold;">Correct</div>
        <div style="font-size: 0.8em; color: #666;">Falls back to HTML entity</div>
      </div>
    </div>
  )
}

// ── Route ─────────────────────────────────────────────────────────────────

app.get("/", (c) => {
  return c.html(
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Lab: Graphics Rendering Testbed</title>
        <style>{`
          body {
            font-family: system-ui, -apple-system, sans-serif;
            max-width: 1100px;
            margin: 2rem auto;
            padding: 1rem;
            line-height: 1.5;
          }
          h1 { border-bottom: 2px solid #333; padding-bottom: 0.5rem; }
          h2 { margin-top: 2rem; color: #333; border-bottom: 1px solid #ddd; padding-bottom: 0.25rem; }
          .why {
            background: #fafafa;
            border-left: 4px solid #3b82f6;
            padding: 1rem;
            margin: 1rem 0;
            border-radius: 0 8px 8px 0;
          }
          .why pre {
            background: #fff;
            padding: 0.5rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            overflow-x: auto;
          }
          .legend {
            display: flex;
            gap: 1rem;
            margin: 1rem 0;
            font-size: 0.9em;
          }
          .legend span { padding: 0.25rem 0.5rem; border-radius: 4px; }
          .legend .ok { background: #f0fdf4; color: #15803d; }
          .legend .fail { background: #fef2f2; color: #b91c1c; }
        `}</style>
      </head>
      <body>
        <h1>Lab: Graphics Rendering Testbed</h1>

        <div class="why">
          <h3>Why this page exists</h3>
          <p>
            Throughout the TradingAgents dashboard we use non-ASCII symbols:
            currency signs (£), checkmarks (✓), arrows (→), warning icons (⚠).
            Some render correctly; some show as literal <code>\uXXXX</code>.
          </p>
          <p>
            <strong>The rule:</strong> In Hono JSX, text between opening and closing
            tags is emitted as literal HTML. JS string escapes like <code>\u00a3</code>
            are <em>not</em> interpreted. They are emitted as six characters:
            <code>\</code> <code>u</code> <code>0</code> <code>0</code> <code>a</code> <code>3</code>.
          </p>
          <p>
            <strong>Only</strong> inside <code>{"{ }"}</code> expressions does JS string
            processing occur. So <code>{"\u00a3"}</code> works, but
            <code>\u00a3</code> in raw text does not.
          </p>
          <pre>// BROKEN — renders as literal \u00a3
&lt;span&gt;\u00a3100&lt;/span&gt;

// WORKING — JS string escape inside expression
&lt;span&gt;{"\u00a3"}100&lt;/span&gt;

// WORKING — literal character
&lt;span&gt;£100&lt;/span&gt;

// WORKING — HTML entity
&lt;span&gt;&amp;pound;100&lt;/span&gt;</pre>
        </div>

        <div class="legend">
          <span class="ok">✅ Green = renders correctly</span>
          <span class="fail">❌ Red background = renders as literal \uXXXX</span>
        </div>

        <h2>1. Currency Symbols</h2>
        <TestRow
          label="Pound £"
          desc="Used in portfolio-summary, intel-hero, intel-platforms, holdings."
          expected="£100"
          broken={<span>{esc.pound}100</span>}
          literal={<span>{lit.pound}100</span>}
          expr={<span>{esc.pound}100</span>}
          entity={<span>&pound;100</span>}
        />
        <TestRow
          label="Dollar $"
          desc="Used in ATR display, price labels."
          expected="$100"
          broken={<span>\u0024100</span>}
          literal={<span>$100</span>}
          expr={<span>{"\u0024"}100</span>}
          entity={<span>&dollar;100</span>}
        />
        <TestRow
          label="Euro €"
          desc="Used for EUR-denominated positions (TKA.DE, TKMS.DE)."
          expected="€100"
          broken={<span>\u20AC100</span>}
          literal={<span>€100</span>}
          expr={<span>{"\u20AC"}100</span>}
          entity={<span>&euro;100</span>}
        />
        <TestRow
          label="Yen ¥"
          desc="Used for JPY-denominated positions if any."
          expected="¥100"
          broken={<span>\u00A5100</span>}
          literal={<span>¥100</span>}
          expr={<span>{"\u00A5"}100</span>}
          entity={<span>&yen;100</span>}
        />

        <h2>2. Checkmarks, Crosses, Ticks</h2>
        <TestRow
          label="Tick ✓"
          desc="Used in workflow-kanban (targets hit), analysis status."
          expected="✓"
          broken={<span>{esc.check}</span>}
          literal={<span>{lit.check}</span>}
          expr={<span>{esc.check}</span>}
          entity={<span>&#10003;</span>}
        />
        <TestRow
          label="Green tick ✅"
          desc="Used in governance-view (all rules satisfied)."
          expected="✅"
          broken={<span>{esc.checkGreen}</span>}
          literal={<span>{lit.checkGreen}</span>}
          expr={<span>{esc.checkGreen}</span>}
          entity={<span>&#9989;</span>}
        />
        <TestRow
          label="Cross ✕"
          desc="Used in prospects-view (delete button), workflow reject."
          expected="✕"
          broken={<span>{esc.cross}</span>}
          literal={<span>{lit.cross}</span>}
          expr={<span>{esc.cross}</span>}
          entity={<span>&#10005;</span>}
        />

        <h2>3. Arrows & UI Icons</h2>
        <TestRow
          label="Right arrow →"
          desc="Used in prospects-view (advance stage), analysis-report (back to list)."
          expected="→"
          broken={<span>{esc.arrowRight}</span>}
          literal={<span>{lit.arrowRight}</span>}
          expr={<span>{esc.arrowRight}</span>}
          entity={<span>&rarr;</span>}
        />
        <TestRow
          label="Left arrow ←"
          desc="Used in analysis-report (back to list)."
          expected="←"
          broken={<span>{esc.arrowLeft}</span>}
          literal={<span>{lit.arrowLeft}</span>}
          expr={<span>{esc.arrowLeft}</span>}
          entity={<span>&larr;</span>}
        />
        <TestRow
          label="Play ▶"
          desc="Used in analysis-view (run analysis button)."
          expected="▶"
          broken={<span>{esc.play}</span>}
          literal={<span>{lit.play}</span>}
          expr={<span>{esc.play}</span>}
          entity={<span>&#9654;</span>}
        />

        <h2>4. Warning & Status Icons</h2>
        <TestRow
          label="Warning ⚠"
          desc="Used in workflow-kanban (near stop, watch), exit-list (time stop)."
          expected="⚠"
          broken={<span>{esc.warning}</span>}
          literal={<span>{lit.warning}</span>}
          expr={<span>{esc.warning}</span>}
          entity={<span>&#9888;</span>}
        />
        <TestRow
          label="Warning emoji ⚠️"
          desc="Used in intel-hero (negative cash banner), governance-view."
          expected="⚠️"
          broken={<span>{esc.warningEmoji}</span>}
          literal={<span>{lit.warningEmoji}</span>}
          expr={<span>{esc.warningEmoji}</span>}
          entity={<span>&#9888;&#65039;</span>}
        />
        <TestRow
          label="Clock ⏱"
          desc="Used in workflow-kanban (time stop countdown)."
          expected="⏱"
          broken={<span>{esc.clock}</span>}
          literal={<span>{lit.clock}</span>}
          expr={<span>{esc.clock}</span>}
          entity={<span>&#9201;</span>}
        />

        <h2>5. Shapes & Misc</h2>
        <TestRow
          label="Diamond open ◇"
          desc="Used in workflow-kanban (approved stage icon)."
          expected="◇"
          broken={<span>{esc.diamondOpen}</span>}
          literal={<span>{lit.diamondOpen}</span>}
          expr={<span>{esc.diamondOpen}</span>}
          entity={<span>&#9671;</span>}
        />
        <TestRow
          label="Diamond solid ◆"
          desc="Used in workflow-kanban (holdings stage icon)."
          expected="◆"
          broken={<span>{esc.diamondSolid}</span>}
          literal={<span>{lit.diamondSolid}</span>}
          expr={<span>{esc.diamondSolid}</span>}
          entity={<span>&#9670;</span>}
        />
        <TestRow
          label="Em dash —"
          desc="Used everywhere for null/missing values (fmtPnl, signal display)."
          expected="—"
          broken={<span>{esc.emDash}</span>}
          literal={<span>{lit.emDash}</span>}
          expr={<span>{esc.emDash}</span>}
          entity={<span>&mdash;</span>}
        />
        <TestRow
          label="Middle dot ·"
          desc="Used in holdings (platform detail separator)."
          expected="·"
          broken={<span>{esc.dot}</span>}
          literal={<span>{lit.dot}</span>}
          expr={<span>{esc.dot}</span>}
          entity={<span>&middot;</span>}
        />

        <h2>Conclusion</h2>
        <div class="why">
          <h3>Rule for Hono JSX</h3>
          <p>
            <strong>Never</strong> use <code>\uXXXX</code> in raw JSX text.
            It will render as six literal characters.
          </p>
          <p>
            <strong>Always</strong> use one of these three methods:
          </p>
          <ol>
            <li>
              <strong>Literal character</strong> — type £, →, ✓ directly into JSX text.
              Best for static symbols.
            </li>
            <li>
              <strong>JS expression</strong> — <code>{"\u00a3"}100</code>.
              Best when the symbol comes from a variable or formatter.
            </li>
            <li>
              <strong>HTML entity</strong> — <code>&amp;pound;</code>.
              Safe fallback, always works in browser.
            </li>
          </ol>
          <p>
            <strong>Recommended:</strong> use literal characters for all static
            symbols in views. Use JS expressions only when the symbol is
            computed dynamically (e.g. from a formatter function).
          </p>
        </div>

        <footer style="margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #ddd; color: #888; font-size: 0.85em;">
          Lab route: <code>server/routes/lab-currency.tsx</code> ·
          Not linked from nav — visit <code>/lab/currency</code> directly.
        </footer>
      </body>
    </html>,
  )
})

export default app
