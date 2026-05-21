# Brief: Stock Card Component

**Date:** 2026-05-21
**Status:** Open

---

## Task: Stock Card View

**Objective:** Replace the table-based positions view and prospects pipeline with unified card components showing price, indicators, signal, and actions for each stock.

## What

- [ ] `src/server/views/components/StockCard.tsx` — reusable card component
- [ ] `src/server/routes/stocks.tsx` — API route serving card data (prices + indicators + signal)
- [ ] `GET /api/stocks` — returns cards for all positions + watchlist items
- [ ] `GET /api/stocks/html` — server-rendered card grid HTML for HTMX
- [ ] `src/server/views/stocks-view.tsx` — full stocks page wrapping the card grid
- [ ] Nav link to `/stocks` in the main layout

## Card Anatomy

Each card shows:

```
┌─────────────────────────────┐
│ SPY        🟢  ·  SPY       │  ← ticker + freshness badge
│ $582.34  +1.2%              │  ← price + day change (colour coded)
│ ▁▂▃▅▆▇█▇▆▅▃▂▁              │  ← sparkline (SVG, 20pts, green/red)
├─────────────────────────────┤
│ RSI      28.4                │  ← key indicator (RSI, ADX, MACD hist)
│ ADX      22.1  ● trending   │
│ MA20     583.12  ✓ above    │
│ MA150    545.00  ✓ above    │  ← structural trend guard (always shown)
│ Vol      62M  ✓ confirmed   │
├─────────────────────────────┤
│ Signal  🟢 BUY              │  ← scan signal: BUY / NO-BUY / SELL
│ Gates   5/6  G3 failed      │  ← gate summary + first failure
│ Exit    CLEAR               │  ← exit trigger status
├─────────────────────────────┤
│ [Analyze]  [Sell]           │  ← actions (context: holdings or watchlist)
└─────────────────────────────┘
```

**Card states:**
- `buy` — green signal border, BUY badge
- `no_buy` — neutral border, NO-BUY badge + failing gate listed
- `sell` — red signal border, SELL badge + trigger listed
- `stale` — muted card if no recent price data

**Indicator strip** (top): always RSI, ADX, MA20, MA150, Vol. MACD in a tooltip or expandable section.

**Signal section** (middle): scan engine result + gate pass count + first failure reason.

**Actions** (bottom): `[Analyze]` always present. `[Buy]` for watchlist items. `[Sell]` for holdings.

## How to Verify

- [ ] Run `just dev` — navigate to `/stocks`, see card grid for SPY/QQQ/IWM (if prices synced)
- [ ] Card shows correct price from `prices` table
- [ ] Sparkline renders from price history
- [ ] RSI/ADX/MA values shown (from `indicator_readings` table)
- [ ] Signal badge shows BUY/NO-BUY/sell
- [ ] `[Analyze]` links to `/analyze?ticker=SPY`
- [ ] `[Buy]`/`[Sell]` shown based on context (watchlist vs position)
- [ ] Stale card shown when price data is missing
- [ ] `just check` passes (biome + tsc)

## Technical Notes

- **Depends on SCAN-001** — indicator_readings table (S03) must be complete before this is fully live. Cards gracefully degrade: show price + sparkline even if indicator_readings is empty.
- **HTMX swap** — `GET /api/stocks/html` returns the card grid. Refresh interval: every 60s.
- **Datatype font** — all numeric values use `font-family: Datatype, monospace; font-feature-settings: 'calt' 1, 'liga' 1`.
- **Responsive** — cards stack 1-column on mobile, 2-3 columns on desktop via CSS grid.
- **No client-side JS** — all rendering server-side. HTMX handles refresh only.
- **Data source priority**: `indicator_readings` table (written by scan engine) → compute fresh from `prices` table → fallback to null.

## Dependencies

- `src/server/lib/indicators.ts` — for live indicator computation (SCAN-001-S01)
- `indicator_readings` table — for cached indicator values (SCAN-001-S03)
- `prices` table — for price + sparkline data (PRICES-001 — done)
- `positions` table — to distinguish holdings from watchlist items
- `watchlist` table — to include prospects in card grid

---

## Done

- [ ] StockCard component with all anatomy sections
- [ ] API route returning card data + HTML
- [ ] Stocks page at `/stocks`
- [ ] Nav link in layout
- [ ] Graceful degradation with empty indicator data
- [ ] just check passes