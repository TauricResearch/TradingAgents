/**
 * StockCard component — server-rendered, no client JS.
 *
 * Props:
 *   ticker, price, changePct, sparkline, indicators, signal,
 *   gatesPassed, gatesTotal, firstFailure, exitStatus, actions
 */

import type { IndicatorSnapshot, ScanResult } from "../../lib/indicators.ts"
import { computeSnapshot, evaluateScan, type OHLCVBar } from "../../lib/indicators.ts"

export interface StockCardData {
  ticker: string
  platform: string
  isHolding: boolean
  quantity?: number
  avgCost?: number
  currentPrice: number | null
  changePct: number | null
  lastPriceDate: string | null
  sparkline: number[]
  indicators: IndicatorSnapshot | null
  signal: "buy" | "no_buy" | "sell" | null
  gatesPassed: number
  gatesTotal: number
  firstFailure: string | null
  exitStatus: string | null
}

export interface StockCardProps {
  card: StockCardData
}

// ── Sparkline SVG ──────────────────────────────────────────────

function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  if (data.length < 2) return <div style="height:32px" />
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const W = 100
  const H = 32
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * W
      const y = H - ((v - min) / range) * (H - 4) - 2
      return `${x},${y}`
    })
    .join(" ")
  const color = positive ? "#22c55e" : "#ef4444"
  const fillPoints = `0,${H} ${points} ${W},${H}`

  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      <polygon points={fillPoints} fill={color} fill-opacity="0.15" />
      <polyline points={points} fill="none" stroke={color} stroke-width="1.5" stroke-linejoin="round" />
    </svg>
  )
}

// ── Gate pill ────────────────────────────────────────────────

function GatePill({ label, value, passed }: { label: string; value: string | number; passed: boolean }) {
  const color = passed ? "#22c55e" : "#ef4444"
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0", fontSize: "12px" }}>
      <span style={{ color: "#888" }}>{label}</span>
      <span style={{ color }}>
        {passed ? "✓" : "✗"} {value}
      </span>
    </div>
  )
}

// ── Signal badge ─────────────────────────────────────────────

function SignalBadge({ signal, gatesPassed, gatesTotal, firstFailure, exitStatus }: {
  signal: string; gatesPassed: number; gatesTotal: number; firstFailure: string | null; exitStatus: string | null
}) {
  const map: Record<string, { bg: string; color: string; label: string }> = {
    buy: { bg: "#22c55e", color: "#fff", label: "BUY" },
    sell: { bg: "#ef4444", color: "#fff", label: "SELL" },
    no_buy: { bg: "#888", color: "#fff", label: "NO-BUY" },
  }
  const s = map[signal] ?? { bg: "#888", color: "#fff", label: "NO-BUY" }

  return (
    <div style={{
      display: "flex", gap: "8px", alignItems: "center",
      padding: "6px 10px", background: s.bg, color: s.color,
      borderRadius: "4px", fontWeight: 700, fontSize: "13px"
    }}>
      <span style={{ fontSize: "16px" }}>{signal === "buy" ? "🟢" : signal === "sell" ? "🔴" : "⚪"}</span>
      <span>{s.label}</span>
      <span style={{ fontWeight: 400, fontSize: "11px", opacity: 0.8 }}>
        {gatesPassed}/{gatesTotal}
      </span>
    </div>
  )
}

// ── Main StockCard component ─────────────────────────────────

export function StockCard({ card }: StockCardProps) {
  const {
    ticker, platform, isHolding, quantity, avgCost,
    currentPrice, changePct, lastPriceDate,
    sparkline, indicators,
    signal, gatesPassed, gatesTotal, firstFailure, exitStatus,
  } = card

  const isStale = currentPrice === null
  const isPositive = (changePct ?? 0) >= 0

  const signalBorder = signal === "buy" ? "#22c55e" : signal === "sell" ? "#ef4444" : "#888"
  const borderColor = isStale ? "#555" : signalBorder

  return (
    <div style={{
      border: `1px solid ${borderColor}`,
      borderRadius: "6px",
      background: "#fff",
      overflow: "hidden",
      opacity: isStale ? 0.6 : 1,
      minWidth: "260px",
      fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif",
    }}>
      {/* Header */}
      <div style={{ padding: "12px 14px 8px", borderBottom: "1px solid #f0f0f0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontWeight: 700, fontSize: "15px" }}>{ticker}</span>
          {isHolding
            ? <span style={{ fontSize: "10px", background: "#e8f5e9", color: "#2e7d32", padding: "2px 6px", borderRadius: "3px" }}>HOLDING</span>
            : <span style={{ fontSize: "10px", background: "#fff3e0", color: "#e65100", padding: "2px 6px", borderRadius: "3px" }}>WATCH</span>}
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "baseline", marginTop: "4px" }}>
          <span style={{ fontFamily: "Datatype, 'SF Mono', monospace", fontSize: "18px", fontWeight: 700 }}>
            {currentPrice !== null ? `$${currentPrice.toFixed(2)}` : "—"}
          </span>
          {changePct !== null && (
            <span style={{ fontSize: "12px", color: isPositive ? "#22c55e" : "#ef4444", fontFamily: "Datatype, monospace" }}>
              {isPositive ? "+" : ""}{changePct.toFixed(1)}%
            </span>
          )}
        </div>
        {lastPriceDate && (
          <div style={{ fontSize: "10px", color: "#aaa", marginTop: "2px" }}>
            {lastPriceDate}
          </div>
        )}
      </div>

      {/* Sparkline */}
      <div style={{ padding: "8px 14px", borderBottom: "1px solid #f0f0f0" }}>
        <Sparkline data={sparkline} positive={isPositive} />
      </div>

      {/* Indicator strip */}
      {indicators && (
        <div style={{ padding: "8px 14px", borderBottom: "1px solid #f0f0f0" }}>
          <GatePill label="RSI(14)" value={indicators.rsi_14.toFixed(1)} passed={indicators.rsi_14 < 30} />
          <GatePill label="ADX(14)" value={indicators.adx_14.toFixed(1)} passed={indicators.adx_14 > 20} />
          <GatePill label="MA20" value={indicators.ma_20.toFixed(2)} passed={indicators.ma_20 !== null && (currentPrice ?? 0) > indicators.ma_20} />
          <GatePill label="MA150" value={indicators.ma_150.toFixed(2)} passed={indicators.ma_150 !== null && (currentPrice ?? 0) > indicators.ma_150} />
          <GatePill label="MACD hist" value={indicators.macd_histogram.toFixed(3)} passed={indicators.macd_histogram > 0} />
        </div>
      )}

      {/* Signal */}
      {signal && (
        <div style={{ padding: "8px 14px", borderBottom: "1px solid #f0f0f0", display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
          <SignalBadge
            signal={signal}
            gatesPassed={gatesPassed}
            gatesTotal={gatesTotal}
            firstFailure={firstFailure}
            exitStatus={exitStatus}
          />
          {exitStatus && exitStatus !== "clear" && (
            <span style={{ fontSize: "11px", color: "#ef4444" }}>⚠ {exitStatus}</span>
          )}
        </div>
      )}

      {/* Actions */}
      <div style={{ padding: "8px 14px", display: "flex", gap: "6px" }}>
        <a
          href={`/analyze?ticker=${ticker}`}
          style={{ flex: 1, padding: "6px 8px", background: "#f0f0f0", color: "#333", textDecoration: "none", textAlign: "center", borderRadius: "4px", fontSize: "12px", fontWeight: 600 }}
        >
          Analyze
        </a>
        {isHolding
          ? <button
              style={{ flex: 1, padding: "6px 8px", background: "#fee2e2", color: "#dc2626", border: "none", borderRadius: "4px", fontSize: "12px", fontWeight: 600, cursor: "pointer" }}
              hx-post={`/api/positions/exits/${ticker}`}
              hx-target="closest .stock-card"
              hx-swap="outerHTML"
            >
              Sell
            </button>
          : <button
              style={{ flex: 1, padding: "6px 8px", background: "#dcfce7", color: "#16a34a", border: "none", borderRadius: "4px", fontSize: "12px", fontWeight: 600, cursor: "pointer" }}
              hx-post={`/api/watchlist/add/${ticker}`}
              hx-target="closest .stock-card"
              hx-swap="outerHTML"
            >
              Buy
            </button>}
      </div>
    </div>
  )
}

// ── Stock card grid ──────────────────────────────────────────

export function StockCardGrid({ cards }: { cards: StockCardData[] }) {
  if (cards.length === 0) {
    return (
      <div style={{ textAlign: "center", color: "#888", padding: "40px" }}>
        <p>No positions or watchlist items.</p>
        <p style={{ fontSize: "12px", marginTop: "8px" }}>Add positions via the Portfolio tab or add watchlist items.</p>
      </div>
    )
  }
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
      gap: "16px",
      padding: "16px",
    }}>
      {cards.map((card) => (
        <div key={card.ticker} class="stock-card">
          <StockCard card={card} />
        </div>
      ))}
    </div>
  )
}