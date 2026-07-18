# TradingAgents Pro — Road from 82 to ⭐ (10/10)

Successor to [PRO_10X_ROADMAP.md](PRO_10X_ROADMAP.md) (58→) and [PRO_90_ROADMAP.md](PRO_90_ROADMAP.md) (74→82). Source of truth for gaps: [PRO_TRADER_REVIEW_V4.md](PRO_TRADER_REVIEW_V4.md) — 82/100 🟢, verdict: *"Fix the sentence this week; let the record and the history close the rest."*

**Honesty first.** A literal 10/10 in every category requires three things no sprint can produce: an aged, profitable track record (months of live paper trading), paid microstructure data (order flow/DOM), and breadth that accretes (indicators, symbols). This plan therefore has three lanes — **engineering** (ships now), **time** (accrues on a schedule we protect), and **money** (a decision, priced) — and it never trades honesty for a score. The engineering lane alone lands ~90–92; ⭐ is engineering + an aged record + at least one data decision.

---

## The arithmetic (from V4's scores)

| Category | R4 | Target | Lane | Levers |
|---|---|---|---|---|
| Decision Support | 8.5 | **10** | eng | R4.1 invalidation-consistency gate; mandatory invalidation_price; p(win) at n≥20 |
| AI Explainability | 9.5 | **10** | eng | R4.1 fix (the −0.5 was earned back by ask-the-record); streaming answers |
| Charting | 9 | **9.5–10** | eng (+money for 10) | Bar paging; AI-layer toggle + declutter; Ichimoku/AVWAP; undo/redo; context menu; Renko/Kagi/P&F. True 10 vs Bookmap needs L2 (money) |
| Trading Experience | 8.5 | **9.5** | eng | Manual paper ticket (V4 asked again — decision revisit); FX majors; trailing-stop viz |
| Risk Management | 9 | **9.5** | eng | stop_price in positions view → stop line + trail on chart; risk board polish |
| Speed & Workflow | 8.5 | **9.5** | eng | Streaming ask (~30s → first token <5s); paging without viewport jumps |
| Premium Feel | 8.5 | **9.5** | eng | Bell digest (kill 99+); toast persistence + undo; light-theme ribbon audit; visual pass |
| Market Intelligence | 7 | **9** | eng + money | FREE Binance funding/OI lane (no key needed); calendar consensus (vendor key decision); liquidations (paid) |
| Portfolio Management | 6 | **9–10** | **time** | Record accrual n≥20 → n≥100 with PF>1; engineering only *surfaces* it |
| Value for Money | 8 | **10** | follows | Rides everything above; $99 tier justified at n≥20 + fixes |

**Projected: engineering lane → ~90–92. + aged record (n≥20, calibration holding) → ~95. + record n≥100 PF>1 + one paid data lane → ⭐.**

---

## Phase A — The trust patch (this week; V4's "fix the sentence")

**A1. R4.1 — invalidation direction-consistency gate (the headline).**
Root cause: reflection writes invalidation prose *before* the judge decides; a direction flip leaves contradictory text and a null `invalidation_price` on the ticket.
- In the pipeline (nodes.py), after the judge: if reflection's invalidation direction contradicts the verdict (SELL + "close below X invalidates the long" pattern), **regenerate** the invalidation via a targeted structured call against the final direction — or, if regeneration fails, **suppress the prose** and state "invalidation restated after direction change" rather than display a contradiction.
- Make `invalidation_price` **required for directional recommendations** at the portfolio-manager step: derive from the final thesis (judge's invalidation level), validated by the existing `_validate_invalidation()` geometry. A directional ticket with null invalidation_price becomes a contract violation → run rejects rather than ships prose-only invalidation.
- Regression test: replay run `39a7db07`'s shape (bullish-leaning reflection + SELL verdict) → assert regenerated/suppressed prose + non-null price.

**A2. R4.2 — replay pause paints the zone one bar late.** Use snapped times in the as-of filter (same `snapToBar` comparison the pause logic uses) so the paused decision's zone/marker is visible at the pause moment.

**A3. R4.3 — name the gating event.** Rejection payload already knows the stage; extend event-gate rejections to carry the event title + time (`rejection.detail`), render it in the chart popover and decision card ("✕ event_gate · FOMC 14:00 ET").

**A4. Bell digest — kill the 99+.** Badge caps at a meaningful number; consecutive info-grade run notes auto-collapse into one daily digest row; "mark all read below warning" one-click. (Grouping exists; this is policy + badge math.)

**A5. Alert toast: 6s + persistent confirmation** in the alerts panel (row highlight), plus an Undo in the toast.

*Gate: full suites + one live run observed with consistent invalidation → deploy → spot-check on prod.*

## Phase B — History + interrogation speed (next)

**B1. Bar paging.** `/api/bars` gains `end` (epoch, exclusive; cache key gains end-bucket; MAX_LIMIT stays 1000). Frontend `useInfiniteQuery` prepend with `setVisibleLogicalRange` preservation; annotations re-snap after prepend (older decisions surface — the record becomes archaeology). This single item removes V4's "biggest remaining charting gap."

**B2. Streaming ask-the-record.** SSE or chunked responses for `/api/runs/{id}/ask`; first tokens <5s, spinner shows model progress. (V4: "the slowest interaction on the platform.")

**B3. AI-layer control.** Toolbar toggle to hide/show the annotations layer; density rule: when >N zones share the viewport, collapse superseded spans to entry ticks, full zones only for open/closed-with-fill (V4 frustration #9/#10).

## Phase C — Charting breadth (the TradingView parity push)

- **Ichimoku** with real 26-bar forward shift (whitespace axis extension — designed in CHART_PROGRAM.md).
- **Anchored VWAP**: click-anchored, computed server-side (`anchor` param).
- **Indicator templates** (named sets in prefs) + **chart-prefs server sync** (indicators/volume/grid/pane factors → `prefs.layouts.chart`, debounced, size-budgeted).
- **Undo/redo** for drawings (zundo temporal, ⌘Z/⇧⌘Z) + **right-click context menu** (alert here / add drawing / explain nearest decision — reuses `findNearestRun`).
- **Renko/Kagi/P&F** as deterministic backend transforms (`/api/bars/transform`; Constraint 2 — brick sizing is a trading parameter).
- Trailing-stop visualization: add `stop_price` to `open_positions_view`; chart draws the stop line and its movement over time.

## Phase D — Intelligence lanes

- **Free lane (no key, ship it):** Binance futures funding rate + open interest for BTC/ETH/SOL (public REST, keyless — same vendor discipline as existing Binance spot feed). Surfaces V4's missing funding/OI honestly at zero cost. Crypto-sentiment agents gain two real feeds.
- **Key decision (user):** calendar consensus/previous/actual needs a licensed vendor key (FMP/TradingEconomics). Priced, documented, not faked.
- **Paid lane (user decision, unblocks Charting 10 + Intel 10):** liquidation maps + L2/order-flow — Tardis ~$300+/mo, CoinAPI/Amberdata ~$100s/mo. The plan treats this as a tier decision, not a default.
- **FX majors** (EURUSD/GBPUSD/USDJPY via OANDA — token already supported): widens the tradeable universe and the scanner.

## Phase E — The record (time lane; engineering only protects it)

- **Milestones surfaced, not manufactured:** ticket p(win) at n≥20; Record page banners at n≥20 / n≥50 / n≥100 with calibration-vs-diagonal and PF net of costs; per-symbol breakdown.
- **Loop hygiene:** the hourly loop keeps accruing; nothing in Phases A–D may disturb cadence or discipline (rejections are wins for the record's honesty).
- **Cadence:** re-review (R5) after Phases A–B ship; R6 after C–D; expect ⭐ consideration only when the Record page itself clears its own "proven" bar.

## Deliberately out (still)
Manual live-order execution, simulated tick/DOM data, any faked feed, seconds timeframes without a vendor that supplies them. **User decisions locked (18 Jul): the manual paper ticket stays skipped** — the product remains a pure decision terminal (the AI trades, the human supervises); **data lanes stay free-only** — keyless Binance funding/OI ships, calendar-vendor keys and paid L2 remain documented options with prices, not defaults.

## Execution status (18 Jul 2026)

**Shipped + verified live** (from the V4 82/100 base):
- **Phase A — trust patch** (`bb0b052`): R4.1 invalidation direction-consistency (verified live: a fresh SELL now carries a non-null, correctly-sided invalidation), R4.2 replay-pause paint, R4.3 gating-event names, bell digest (99+ → warnings-only badge), alert toast 6s+undo.
- **Phase B — history + speed** (`2c135d6`): bar paging (`/api/bars?end=` + infinite prepend, verified older windows), streaming ask (first byte ~2.2s vs ~30s, verified live), AI-layer toggle + density declutter.
- **Phase C batch 1** (`19f0364`): position stop line + **autoscale guard** (a real robustness fix — a stale/mismatched position price no longer distorts the chart), drawing undo/redo (⌘Z/⇧⌘Z + toolbar), right-click context menu.
- **Phase C batch 2** (`dcb4c83`): indicator templates + chart-prefs cross-device sync (`prefs.layouts.chart`).

**Remaining (documented, harder batch):**
- **Ichimoku (forward-shifted cloud)** — deferred a 4th time on purpose: the honest senkou-span projection needs the `indicator_series_view` time contract to emit future timestamps (it currently zips values to bar times with `strict=True`) + frontend whitespace axis-extension. Real work, modest marginal score; tenkan/kijun/chikou (no forward shift) could ship first if charting breadth is reprioritized.
- **Anchored VWAP** — reuses `_vwap_series` with a click-set anchor; needs a click-anchor tool mode + dynamic indicator-request plumbing (the indicators hook uses a fixed names list).
- **Renko/Kagi/P&F** — deterministic backend transforms (`/api/bars/transform`, Constraint 2); new synthetic-bar infra.

These three are the canvas/series-contract-heavy items; batched separately so they don't hold up the verified wins above.

## Verification discipline (unchanged)
Every phase: backend `~/.venvs/tradingagents-pro/bin/python -m pytest -q` + ruff; frontend `tsc -b`, lint, vitest, Playwright with real clicks; deploy via `scripts/deploy_cloud_run.sh`; then live verification on prod (the review only credits what it can click). Score movement is claimed only by the next review round, never by the changelog.
