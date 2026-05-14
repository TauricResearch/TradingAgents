/**
 * Feedback HTML — renders post-mortem results: signal accuracy, position outcomes, and notes.
 */

/** @jsxImportSource hono/jsx */

import type { SignalAccuracy, PostMortem, TickerCorrelation } from "../lib/feedback-data.ts"

// ── Accuracy panel ──────────────────────────────────────────────────────────────

export function AccuracyPanel({ accuracy }: { accuracy: SignalAccuracy }) {
  if (!accuracy || accuracy.totalSignals === 0) {
    return <div class="muted">No post-mortems yet. Exit a position to generate one.</div>
  }

  return (
    <>
      <div class="accuracy-summary">
        <div class={`accuracy-score ${accuracy.accuracyPct >= 60 ? "positive" : "negative"}`}>
          {accuracy.accuracyPct}% accuracy ({accuracy.correctSignals}/{accuracy.totalSignals})
        </div>
      </div>

      {accuracy.bySignalType && Object.keys(accuracy.bySignalType).length > 0 && (
        <table class="data-table">
          <thead>
            <tr>
              <th>Exit Trigger</th>
              <th>Signals</th>
              <th>Correct</th>
              <th>Accuracy</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(accuracy.bySignalType).map(([type, d]) => (
              <tr>
                <td>{type}</td>
                <td>{d.total}</td>
                <td>{d.correct}</td>
                <td class={d.pct >= 60 ? "positive" : "negative"}>{d.pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

// ── Post-mortems ────────────────────────────────────────────────────────────────

export function PostMortemsList({ mortems }: { mortems: PostMortem[] }) {
  if (!mortems || mortems.length === 0) {
    return <div class="muted">No post-mortems yet.</div>
  }

  return (
    <>
      {mortems.map((pm) => {
        const signalClass = pm.aiSignalCorrect ? "positive" : "negative"
        const signalIcon = pm.aiSignalCorrect ? "\u2705" : "\u274c"
        return (
          <div class="post-mortem-card">
            <div class="pm-header">
              <span class="ticker">{pm.ticker}</span>
              <span class="pm-date">{pm.exitDate}</span>
            </div>
            <div class="pm-thesis">{pm.thesis}</div>
            <div class="pm-outcome">
              <span>Thesis: {pm.thesisPlayedOut ? "\u2705" : "\u274c"}</span>
              <span>
                AI signal: <span class={signalClass}>{signalIcon}</span>
              </span>
              <span>Exit: {pm.exitTrigger}</span>
            </div>
            {pm.lesson && <div class="pm-lesson">{pm.lesson}</div>}
          </div>
        )
      })}
    </>
  )
}

// ── Correlations table ──────────────────────────────────────────────────────────

export function CorrelationsTable({
  data,
}: {
  data: {
    correlations: TickerCorrelation[]
    summary: { total: number; accurate: number; accuracy: number }
  }
}) {
  if (!data.correlations || data.correlations.length === 0) {
    return <div class="muted">No signals recorded yet.</div>
  }

  const summary = data.summary
  const accCls = summary.accuracy >= 60 ? "positive" : "negative"

  return (
    <>
      <div class="accuracy-summary" style="margin-bottom:1rem">
        <span>Signal accuracy: </span>
        <span class={`accuracy-score ${accCls}`}>{summary.accuracy}%</span>
        <span class="muted">
          {" "}
          ({summary.accurate}/{summary.total} buy/sell signals with positions)
        </span>
      </div>

      <table class="data-table" style="font-size:0.85em">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Latest Signal</th>
            <th>Platform</th>
            <th>Position</th>
            <th>Entry</th>
            <th>P&amp;L</th>
            <th>Signal Outcome</th>
          </tr>
        </thead>
        <tbody>
          {data.correlations.map((c) => {
            const plat = c.signals[0]?.platform ?? "unknown"
            const sCls = c.signalOutcome.includes("success")
              ? "positive"
              : c.signalOutcome.includes("failure")
                ? "negative"
                : c.signalOutcome === "hold"
                  ? "status-hold"
                  : "muted"
            const pnlCls =
              c.outcomePct != null
                ? c.outcomePct >= 0
                  ? "positive"
                  : "negative"
                : "muted"
            const pnlStr =
              c.outcomePct != null
                ? `${(c.outcomePct >= 0 ? "+" : "") + c.outcomePct.toFixed(1)}%`
                : "\u2014"
            const sigCls = c.latestSignal.includes("buy")
              ? "status-buy"
              : c.latestSignal.includes("sell")
                ? "status-sell"
                : "status-hold"

            return (
              <tr key={c.ticker}>
                <td class="ticker">{c.ticker}</td>
                <td class={sigCls}>{c.latestSignal}</td>
                <td>
                  <span class="platform-tag">{plat}</span>
                </td>
                {c.position ? (
                  <>
                    <td>
                      {c.position.quantity} shares @ &pound;{c.position.avg_cost.toFixed(2)}{" "}
                      <span class="muted">(GBP)</span>
                    </td>
                    <td>{c.position.entry_date}</td>
                    <td class={`pnl-cell ${pnlCls}`}>{pnlStr}</td>
                  </>
                ) : (
                  <>
                    <td class="muted">—</td>
                    <td class="muted">—</td>
                    <td class="muted">—</td>
                  </>
                )}
                <td class={sCls}>{c.signalOutcome}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </>
  )
}
