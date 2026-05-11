/** @jsxImportSource hono/jsx */
/**
 * Alerts dashboard view — list + create form.
 * Renders server-side, HTMX partial refresh for table.
 */

import type { AlertRule, TriggeredAlert } from "../lib/types.ts"

const dot: Record<string, string> = {
  critical: "🔴",
  warning: "🟡",
  info: "🔵",
  ok: "⚪",
}

const CONDITION_EXAMPLES: Record<string, string> = {
  price_below: '{"type":"price_below","threshold":100}',
  price_above: '{"type":"price_above","threshold":200}',
  pct_change_day: '{"type":"pct_change_day","threshold":5}',
  pct_change_week: '{"type":"pct_change_week","threshold":10}',
  price_cross: '{"type":"price_cross","threshold":150,"direction":"down"}',
}

function TriggeredBadge({ ta }: { ta: TriggeredAlert }) {
  const pct = ta.pctChange != null ? ` (${ta.pctChange >= 0 ? "+" : ""}${ta.pctChange.toFixed(1)}%)` : ""
  const price = ta.currentPrice != null ? `£${ta.currentPrice.toFixed(2)}` : "?"
  return (
    <span class={`signal-badge signal-badge-${ta.alert.severity}`} title={ta.message}>
      {dot[ta.alert.severity] ?? "⚪"} {ta.alert.name}: {price}{pct}
    </span>
  )
}

function AlertsTable({ alerts, triggered }: { alerts: AlertRule[]; triggered: TriggeredAlert[] }) {
  const triggeredIds = new Set(triggered.map((t) => t.alert.id))

  if (alerts.length === 0) {
    return (
      <div class="muted" style="padding:1rem;text-align:center">
        No alert rules defined. Use the form below to create one.
      </div>
    )
  }

  return (
    <div style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            <th>Ticker</th>
            <th>Severity</th>
            <th>Condition</th>
            <th>Channel</th>
            <th>On</th>
            <th>Last Fired</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody hx-get="/api/alerts/table" hx-trigger="every 60s" hx-swap="innerHTML">
          {alerts.map((a) => {
            const isTriggered = triggeredIds.has(a.id)
            const ta = triggered.find((t) => t.alert.id === a.id)
            const lastTriggered = a.lastTriggered ? new Date(a.lastTriggered).toLocaleDateString("en-GB") : "—"

            return (
              <tr class={isTriggered ? "row-triggered" : ""}>
                <td>{a.id}</td>
                <td>{a.name}</td>
                <td><code>{a.ticker ?? <span class="muted">—</span>}</code></td>
                <td>{dot[a.severity] ?? "⚪"} {a.severity}</td>
                <td><code style="font-size:0.8em;word-break:break-all">{JSON.stringify(a.condition)}</code></td>
                <td>{a.channel}</td>
                <td>{a.enabled ? "✓" : "✗"}</td>
                <td>{lastTriggered}</td>
                <td>
                  {isTriggered
                    ? <TriggeredBadge ta={ta!} />
                    : <span class="muted signal-badge signal-badge-ok">✓ ok</span>}
                </td>
                <td>
                  <button
                    class="btn-small btn-danger"
                    hx-delete={`/api/alerts/${a.id}`}
                    hx-target="closest tr"
                    hx-swap="delete"
                    title="Delete alert"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CreateForm() {
  return (
    <div class="panel" id="alerts-create-panel">
      <h4 style="margin-bottom:0.75rem">Create Alert Rule</h4>
      <form
        hx-post="/api/alerts"
        hx-target="#alerts-table-wrapper"
        hx-swap="innerHTML"
        {...{ "hx-on::after-request": "if(event.detail.successful) this.reset()" }}
      >
        <div class="form-grid" style="grid-template-columns:1fr 1fr;gap:0.5rem">

          <label class="form-label">
            Name *
            <input name="name" type="text" placeholder="e.g. NVDA drop alert" required />
          </label>

          <label class="form-label">
            Ticker
            <input
              name="ticker"
              type="text"
              placeholder="e.g. NVDA (leave blank for portfolio-level)"
            />
          </label>

          <label class="form-label" style="grid-column:1/-1">
            Condition (JSON) *
            <select
              id="condition-type-select"
              style="margin-bottom:0.25rem"
              onchange={`
                var map = {"price_below":"{\\"type\\":\\"price_below\\",\\"threshold\\":100}","price_above":"{\\"type\\":\\"price_above\\",\\"threshold\\":200}","pct_change_day":"{\\"type\\":\\"pct_change_day\\",\\"threshold\\":5}","pct_change_week":"{\\"type\\":\\"pct_change_week\\",\\"threshold\\":10}","price_cross":"{\\"type\\":\\"price_cross\\",\\"threshold\\":150,\\"direction\":\"down\"}"};
                var val = map[this.value] || "";
                document.getElementById("condition-value").value = val;
              `}
            >
              <option value="price_below">Price ≤ threshold</option>
              <option value="price_above">Price ≥ threshold</option>
              <option value="pct_change_day">Daily % change ≥ threshold</option>
              <option value="pct_change_week">Weekly % change ≥ threshold</option>
              <option value="price_cross">Price crosses threshold (with direction)</option>
            </select>
            <textarea
              id="condition-value"
              name="condition"
              rows={3}
              required
              placeholder='{"type":"price_below","threshold":100}'
              style="font-family:monospace;font-size:0.85em"
            />
          </label>

          <label class="form-label">
            Severity
            <select name="severity">
              <option value="warning" selected>warning</option>
              <option value="critical">critical</option>
              <option value="info">info</option>
            </select>
          </label>

          <label class="form-label">
            Channel
            <select name="channel">
              <option value="telegram" selected>telegram</option>
              <option value="email">email (not implemented)</option>
              <option value="webhook">webhook (not implemented)</option>
              <option value="none">none</option>
            </select>
          </label>

          <label class="form-label" style="grid-column:1/-1">
            Custom Message (optional)
            <input
              name="message"
              type="text"
              placeholder="Override default message"
            />
          </label>

        </div>
        <div style="margin-top:0.75rem;display:flex;gap:0.5rem;align-items:center">
          <button type="submit" class="btn-primary">Create Alert</button>
          <span id="create-result" />
        </div>
      </form>
    </div>
  )
}

export function AlertsView() {
  return (
    <div
      hx-get="/api/alerts/view/html"
      hx-target="this"
      hx-trigger="load"
    >
      <div class="muted">Loading alerts…</div>
    </div>
  )
}

export function AlertsContent({ alerts, triggered }: { alerts: AlertRule[]; triggered: TriggeredAlert[] }) {
  const triggeredCount = triggered.length

  return (
    <>
      {triggeredCount > 0 && (
        <div class="alert-banner" style="margin-bottom:1rem">
          <strong>🔴 {triggeredCount} alert{triggeredCount !== 1 ? "s" : ""} triggered</strong>
          <div style="margin-top:0.5rem;display:flex;flex-wrap:wrap;gap:0.5rem">
            {triggered.map((ta) => <TriggeredBadge ta={ta} />)}
          </div>
          <form
            hx-post="/api/alerts/check/fire"
            hx-target="this"
            hx-swap="innerHTML"
            style="margin-top:0.5rem"
          >
            <button type="submit" class="btn-small btn-danger">
              Send Telegram Notifications
            </button>
          </form>
        </div>
      )}

      <section class="panel" id="alerts-rules-panel">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
          <h3>Alert Rules</h3>
          <button
            class="btn-small"
            hx-get="/api/alerts/table"
            hx-target="table tbody"
            hx-swap="innerHTML"
            title="Refresh"
          >
            ↻ Refresh
          </button>
        </div>
        <div id="alerts-table-wrapper">
          <AlertsTable alerts={alerts} triggered={triggered} />
        </div>
      </section>

      <CreateForm />
    </>
  )
}
