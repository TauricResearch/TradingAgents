/**
 * Signals HTML — renders recent signal history with ticker, direction, confidence, and generated-at timestamp.
 */

/** @jsxImportSource hono/jsx */

import type { PriceWithHistory, Signal } from "../lib/signals-data.ts"
import {
  escSignals,
  fmtDateSignals,
  signalClassSignals,
  sparkline,
} from "../lib/signals-data.ts"

// ── Timeline component ──────────────────────────────────────────────────────

function SignalsTimeline({
  ticker,
  signals,
  priceData,
}: {
  ticker: string
  signals: Signal[]
  priceData: Map<string, PriceWithHistory>
}) {
  const tickerSignals = signals.filter((s) => s.ticker === ticker)
  if (tickerSignals.length === 0) return null

  const priceHist = priceData.get(ticker)
  const priceSpark = sparkline(priceHist?.history ?? null)
  const firstCls = signalClassSignals(tickerSignals[0]?.signal ?? "")

  const confValues = tickerSignals.map((s) => Math.round((s.confidence ?? 0.5) * 100))
  const confSpark = `{l:${confValues.join(",")}}`

  return (
    <>
      <div class="timeline-header">
        {priceSpark && (
          <div class="timeline-section">
            <span class="muted" style="font-size:0.75em">Price (20d)</span>
            <div class={`trend-cell ${firstCls}`}>
              <span class="trend-sparkline">{priceSpark}</span>
            </div>
          </div>
        )}
        <div class="timeline-section">
          <span class="muted" style="font-size:0.75em">Confidence</span>
          <div class={`sparkline ${firstCls}`}>{confSpark}</div>
        </div>
      </div>

      <div class="timeline-entries">
        {tickerSignals.map((s, i) => {
          const cls = signalClassSignals(s.signal)
          const pct = Math.round((s.confidence ?? 0) * 100)
          const pie = `{p:${pct}}`
          return (
            <div class={`timeline-row ${cls}`} key={i}>
              <span class="timeline-signal">{s.signal}</span>
              <span class="timeline-date date-col">{fmtDateSignals(s.date)}</span>
              <span class="datatype-pie" title={`${pct}% confidence`}>{pie}</span>
              <span class="timeline-confidence">{pct}%</span>
              {i === 0 && <span class="timeline-current">current</span>}
            </div>
          )
        })}
      </div>
    </>
  )
}

// ── Table row ───────────────────────────────────────────────────────────────

function SignalRow({
  signal,
  priceData,
}: {
  signal: Signal
  priceData: Map<string, PriceWithHistory>
}) {
  const cls = signalClassSignals(signal.signal)
  const plat = signal.platform || "unknown"
  const conf = signal.confidence != null ? `${Math.round(signal.confidence * 100)}%` : "\u2014"
  const reasoning = (signal.reasoning || "").substring(0, 100)
  const priceHist = priceData.get(signal.ticker)
  const spark = sparkline(priceHist?.history ?? null)

  return (
    <tr>
      <td>
        <span class="platform-tag">{escSignals(plat)}</span>
      </td>
      <td class="date-col">{fmtDateSignals(signal.date)}</td>
      <td class="ticker">{escSignals(signal.ticker)}</td>
      <td class={cls}>{signal.signal}</td>
      <td class={`trend-cell ${cls}`}>
        {spark ? (
          <span class="trend-sparkline">{spark}</span>
        ) : (
          <span class="muted">—</span>
        )}
      </td>
      <td>{conf}</td>
      <td
        class="muted"
        style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
        title={escSignals(signal.reasoning ?? "")}
      >
        {escSignals(reasoning)}
      </td>
    </tr>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function SignalsViewHtml({
  signals,
  priceData,
  allPlatforms,
  allTickers,
  selectedPlatform,
  selectedTicker,
}: {
  signals: Signal[]
  priceData: Map<string, PriceWithHistory>
  allPlatforms: string[]
  allTickers: string[]
  selectedPlatform: string
  selectedTicker: string
}) {
  return (
    <>
      <div
        class="form-row"
        style="margin-bottom:0.5rem"
        hx-get="/api/signals/view/html"
        hx-target="#signals-wrapper"
        hx-trigger="change"
        hx-include="this"
      >
        <select name="platform" id="signals-platform" style="max-width:150px">
          <option value="">All platforms</option>
          {allPlatforms.map((p) => (
            <option value={p} selected={p === selectedPlatform}>
              {escSignals(p)}
            </option>
          ))}
        </select>
        <select name="ticker" id="signals-ticker" style="max-width:150px">
          <option value="">All tickers</option>
          {allTickers.map((t) => (
            <option value={t} selected={t === selectedTicker}>
              {escSignals(t)}
            </option>
          ))}
        </select>
      </div>

      <table id="signals-table">
        <thead>
          <tr>
            <th>Platform</th>
            <th>Date</th>
            <th>Ticker</th>
            <th>Signal</th>
            <th>Trend</th>
            <th>Confidence</th>
            <th>Reasoning</th>
          </tr>
        </thead>
        <tbody id="signals-body">
          {signals.length === 0 ? (
            <tr>
              <td colSpan={7} class="muted">
                No signals recorded
              </td>
            </tr>
          ) : (
            signals.map((s) => (
              <SignalRow signal={s} priceData={priceData} />
            ))
          )}
        </tbody>
      </table>

      {selectedTicker && signals.some((s) => s.ticker === selectedTicker) && (
        <section class="panel" id="timeline-panel">
          <h4>Timeline: {escSignals(selectedTicker)}</h4>
          <div id="signal-timeline">
            <SignalsTimeline
              ticker={selectedTicker}
              signals={signals}
              priceData={priceData}
            />
          </div>
        </section>
      )}
    </>
  )
}
