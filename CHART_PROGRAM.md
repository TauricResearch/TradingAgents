# Chart Program — status ledger

The "world-class professional trading chart" brief, executed as phased deploys
(user priorities: **AI-native first**, **honest data subset** — never fake a feed).
Commits: `78a10de` (Phase 1) · `65a83dc` (Phase 2) · `237adbe` (Phase 3 start).

## Shipped and live

### Phase 1 — AI-native chart (the differentiator)
- **Decision zones on price**: every persisted run renders as a time-bounded
  entry→stop / entry→TP shaded zone with dashed invalidation, span closed by its
  linked fill / superseded by the next decision / open to the last bar.
  Backend: `GET /api/chart/annotations` ([annotations.py](tradingagents/pro/dashboard/annotations.py));
  fills join OUTCOME→TRADE→`recommendation_id`→run **exactly**, time-window
  inference only as a labeled legacy fallback.
- **Regime + confidence ribbon** pinned to the pane top, cadence printed on it.
- **Click-to-explain**: zone/marker/ribbon click → popover with verdict,
  p(win) (n, basis), votes, evidence, counterarguments, link to the decision
  page, inline ask-the-record chat.
- **AI decision replay**: as-of filtering (future stays hidden), auto-pause on
  decision bars (⏸ AI toggle), debate strip with user-driven stepping.
- **Live position**: entry line + badge rendering the SERVER's unrealized P&L.
- LWC v5 discipline: all annotation times go through `snapToBar`
  ([annotationSnap.ts](frontend/src/components/charts/annotationSnap.ts));
  x-coordinates via logical indices so spans clamp instead of vanishing.

### Phase 2 — pro mechanics
Log/linear scale toggle (persisted) · magnet mode (anchors snap to O/H/L/C) ·
measure ruler (Δprice/Δ%/Δbars, ephemeral) · crosshair OHLCV legend
(imperative DOM — mousemove never round-trips React state) · vline + arrow
drawing kinds.

### Phase 3 (partial)
Hollow candles + baseline series, persisted style picker
(candles/hollow/heikin-ashi/OHLC/line/area/baseline).

Verification each phase: full pytest (1290) + vitest (65) + Playwright e2e with
REAL canvas clicks (explain popover opens; replay hides future decisions; vline
places) + live prod checks (49 XAUUSD runs painted, exact fill link, −86.50 pnl).

## Next batch (deferred, in order of trader value)
1. **Bar paging** — `/api/bars` `end` param + `useInfiniteQuery` prepend with
   viewport preservation (unlocks >300-bar history and older annotations).
2. **Right-click context menu** — alert here / add drawing / explain nearest
   decision (reuses `findNearestRun`).
3. **Undo/redo for drawings** — zundo temporal middleware, ⌘Z/⇧⌘Z.
4. **Renko/Kagi/P&F** — deterministic BACKEND transforms (`/api/bars/transform`);
   brick sizing is a computed trading parameter (Constraint 2).
5. **Server-sync chart prefs** (indicators/volume/grid/pane factors →
   `prefs.layouts.chart`, debounced, size-budgeted — single 256KB prefs file).
6. **Ichimoku** (forward-shifted spans via whitespace axis extension) +
   **anchored VWAP** (`anchor` param, click-to-anchor).
7. Indicator templates + saved multi-chart layouts.

## Honestly out of scope (paid data — documented, never faked)
Tick/1s bars, DOM/order-flow footprints, liquidation maps, whale/ETF flows
(Tardis ~$300+/mo, CoinAPI/Amberdata ~$100s/mo, Polygon $29–199/mo).
DXY/US10Y/SILVER stay daily yfinance, labeled in `/api/symbols`.
Bar streaming: 30s poll + 5s tick morphing stands; an SSE `bar` event is a
future candidate.

## Known follow-up
- Pre-existing React "setState during render" warning from the workspace
  symbol-sync line (spawned as its own task; unrelated to the chart program).
