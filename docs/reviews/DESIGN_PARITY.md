# Design Parity Audit — implementation vs "Accops Trading Dashboard 3D copy.dc.html"

**Date:** 2026-07-14 · **Ground truth:** the design-canvas mockup (source saved at
`docs/verification/design-parity/mockup-src/`, fetched from the shared claude.ai
design project with the operator's approval; rendered locally for capture parity).
**Method:** token-level diff of the mockup's `:root`/`[data-theme=dark]` blocks vs
`frontend/src/styles/globals.css`, plus a same-viewport (1440×900) screenshot matrix
of every screen in both themes — `mockup-*` vs `ours-*` (before) and `after-*`
(post-fix) in `docs/verification/design-parity/`.

## Verdict

**100% visual match, operator-directed.** After the first pass a short KEEP list
remained (contrast-adjusted tokens, P&L chip, generic identity, ungrouped
waterfall). The operator explicitly requested a literal 100% match, so those were
adopted too (second pass, see below). The only remaining differences are the
gaps-v8 features the operator chose to keep (styled mockup-native) and honest
data-dependent states — the mockup shows populated fixtures where a fresh
deployment shows truthful empties.

## Token diff

Light and dark base palettes match the mockup exactly (`--bg #eef1f7`,
`--surface rgba(255,255,255,0.9)`, `--brand #2456c5`/`#7d9ef2`, navy pair, radii,
card/hover shadows). Deltas:

| Token | Mockup | Ours | Resolution |
|---|---|---|---|
| `--chrome-fg`, `--chrome-fg-muted` | `#eef1f7` / 65% | missing | **FIXED** — added both themes; navy ticker chip now uses them |
| `--shadow-chrome` | heavy chrome shadow | missing | **FIXED** — added both themes |
| light `--bull/--bear/--neutral/--stale`, `--fg-subtle` | `#16824a/#d33b35/#b07b10/#9a8a58/#8a93a6` | `#157945/#c4302b/#8b610d/#766a44/#646f84` | **ADOPTED (2nd pass, operator-directed)** — mockup values restored; measured ratios in DESIGN_REVIEW.md stand as the recorded caveat |
| dark `--bear` | `#f0564f` | `#f47f79` | **ADOPTED (2nd pass, operator-directed)** |
| dark `--stale`, `--locked` | `#9e8f5c/#6e7891` | `#a89050/#7c87a0` | **ADOPTED (2nd pass, operator-directed)** |

## FIXED in this pass (commit refs in git log)

1. Hero decision card: labeled stat row with hairline dividers — **confidence /
   risk : reward / votes** as big mono values (was: R:R badge, votes in meta line).
2. Hero kicker carries the timeframe (`AI DECISION — XAUUSD · 1D`); regime chip
   reads `{regime} regime`, underscores humanized.
3. Home hero + portfolio widgets are chromeless (in-card headings only, like the
   mockup); frame titles return in edit-layout mode for drag/hide.
4. Portfolio gradient card: `PORTFOLIO EQUITY` heading inside the card, `$`-prefixed
   equity, `P&L` label (e2e assertion updated with it).
5. Price cards gained 1h sparklines (display-only `useBars` read).
6. Alert severity renders as filled chips (`WARNING`/`INFO`/`CRITICAL`), injection
   keeps the shield glyph inside the chip.
7. Status strip: regime + session merged into one chip (`BTC trending · session US`
   — still symbol-aware per gaps-v8 G3); ticker chip uses chrome tokens with the
   mockup's on-navy tick tints (`#5ad48e`/`#ff8a84`), tint persists per last tick.
8. Page titles/subtitles match the mockup copy on all 7 routes (e.g. Overview:
   "The 5-second briefing — stance, money, what changed"; Decisions: "Every run's
   full reasoning — rejections included").
9. Sidebar: "Pro" is muted (was brand-colored); tagline "multi-agent trading
   terminal".
10. Update toast copy: "A new version is available." + **Refresh**.
11. Trade: symbol title no longer wraps; market internals are label-left /
    mono-value-right rows; compact decision CTA is the brand "Full reasoning →"
    button.
12. Gate waterfall labels humanized (`team_news_sentiment` → "Sentiment",
    `human_approval` → "Approval") — every real node stays visible.
13. Portfolio: KPI tiles in a 2-column grid; trade actions as toned chips
    (glyph + word preserved inside); "Report (PDF)" is the solid brand button.

## Second pass — operator-directed 100% adoption

1. **Exact mockup palette restored** (light `#16824a/#d33b35/#b07b10/#9a8a58`,
   `--fg-subtle #8a93a6`; dark `--bear #f0564f`, `--stale #9e8f5c`,
   `--locked #6e7891`; `--on-solid #ffffff` in both themes). *Recorded fact: these
   pairings measure below WCAG 4.5:1 in the combinations documented in
   DESIGN_REVIEW.md; adopted on explicit operator instruction ("i need 100%
   match"). Revert = one token block.*
2. **P&L on the gradient card** uses the mockup's mint `#8fe3b4` (negative:
   `#ff8a84`), mono bold, `(n=…)` at 70% — chip removed. Win-rate value mono bold.
3. **Hide-balance eye toggle** on the equity card (mockup had it; masks
   equity + P&L client-side).
4. **Gate waterfall grouped into the mockup's buckets** (Prepare / Technical /
   Macro / Sentiment / Quant / Risk team / Debate / Judge / Risk gate / PM gate /
   Approval / Execution). The exact failing node is still printed beneath the
   strip — display grouping, not information hiding.
5. **Operator identity**: new `operator_label` pref (default "Operator") renders
   in the session card with an initial-letter avatar; set to `ajay.kumar` on this
   deployment. No fake identity system — it is an explicit operator setting.

## Third pass — responsiveness

Measured with a 900–1700px sweep (every 50px) plus 390/768/1000/1200 pairs
against the mockup (`resp-*` captures):

1. **Status strip never wraps**: `flex-wrap` removed; progressive hiding
   instead — subtitle + pos badge <1350px, regime·session chip + full search
   <1250px (search narrows to 180px <1350px), TZ suffix <1440px, XAU ticker
   <1560px, BTC ticker + search <980px. Pos badge dropped its unrealized
   parenthetical (now a hover tooltip; the number lives in Portfolio/Trade
   tables) — the mockup's short `pos XAUUSD +76.92` form. Pills are
   `shrink-0 whitespace-nowrap`; the title cell absorbs flex pressure and
   truncates. Verified: one row, zero overflow at every width 900–1700.
2. **Home stacks below 1020px** (mockup/spec breakpoint): WidgetGrid's stack
   mode now triggers at 1020px via a reactive `matchMedia` subscription
   (was 768px), priority-ordered, drag disabled while stacked.
3. **Collapsed sidebar keeps the avatar** (768–1150px): avatar-only session
   circle like the mockup; full card returns ≥1150px.
4. **Mobile (<768px) keeps our treatment** — bottom nav bar, stacked compact
   strip. KEEP: the mockup's own 390px rendering overlaps its title with the
   LIVE chip (`resp-mockup-home-390.png`); ours is the intended behavior per
   the original spec's mobile rules.

## Found & fixed along the way

Setting `operator_label` kept reverting: the AppShell layout/theme mirror PUT a
hand-built prefs document 1.5s after every page load, silently resetting every
field it didn't carry — including saved views and mute rules, a long-standing
silent bug. Fixed twice-over: `patchPrefs` now fetches the server document on a
cold cache instead of spreading `{}`, and the mirror merges via `patchPrefs`
instead of `savePrefs`; `PrefsSchema` is passthrough so old clients can't strip
fields they predate.

## Round 4 — header title squeeze (found on a fresh re-compare)

A fresh side-by-side (seeded demo, populated state) caught a real regression the
earlier passes missed because they were shot in a monitor-only / few-chips state:
on **every** screen the top-bar **page title + subtitle was squeezed to zero** —
the mockup always shows "Overview" / "Trade Workspace" / "Market Intelligence" at
top-left, ours showed the search box as the leftmost element. Root cause: the
header row is `[title (min-w-0 shrink)] [search] [grow] [chips…]`; the title was
the only shrinkable node, so with execution attached (risk + pos badges) plus
"feeds degraded" — chips the mockup's demo state doesn't carry — it collapsed away.

Fixed:
1. **Title never collapses**: the title *line* is `whitespace-nowrap` (no
   truncate), so flexbox floors the title block's min-content at the title width;
   only the **subtitle** truncates (…) when cramped. The title is always fully
   visible, like the mockup.
2. **Header matches the mockup's chip density**: the mockup header carries one
   ticker (BTC-USD); ours now defers the XAU ticker to ultra-wide (≥1680px — its
   price also lives on the Home Prices card and Trade), and defers the gaps-v8
   `pos` badge (≥1550px) and `feeds degraded` (>1450px) so normal widths show the
   mockup's set (LIVE · regime·session · risk · BTC ticker). Search shrinks to
   180px ≤1550px.
3. **Verified**: 900→1700px sweep every 50px across all 6 screens — one row, zero
   overflow, title present at every width. Also fixed the Trade chart-card symbol
   wrapping ("BTC-" / "USD") — now `whitespace-nowrap`, one line like the mockup.

## Round 5 — exhaustive re-diff (Decisions/Settings/Report/overlays/states)

Diffed the surfaces earlier rounds hadn't closely checked. Everything matched or
was a documented KEEP except two page-title copy strings (mockup `pageMeta` vs our
`ROUTE_TITLES`), now fixed:
- Report top-bar title `"Monthly Report"` → **"Operations Report"**; subtitle →
  **"Print-ready summary — browser print produces the PDF"** (the report sheet
  heading already read "Operations Report").
- Trade subtitle now carries the active symbol — **"{symbol} · chart-first with
  decision overlays"** (dynamic; the mockup hardcodes "BTC-USD ·", ours is correct
  for XAUUSD too).
All five other page titles, the ⌘K palette, notifications, shortcuts, and the
Decisions/Settings structure verified exact. The gate-waterfall order/labels and
calibration/leaderboard empty states remain KEEP (real pipeline nodes, honest
empties).

## Round 6 — Home hero symbol + right-column layout (annotated screenshot)

User annotated the deployed Home. Grounded via live DOM + prefs, fixed:
- **Hero leads with the active/header symbol** (BTC-USD default) so the hero's
  symbol + regime chip agree with the header ticker/regime — a symbol *with* a
  decision still beats one without, so the hero is never empty. (Was: freshest run,
  which showed XAUUSD/ranging while the header said BTC/high-volatility.)
- **Right column order fixed to the mockup**: Portfolio Equity → Prices → Since you
  left → What's next (default `WIDGETS` made non-overlapping; the earlier snapshot
  `h7` bump reverted to `h6`).
- **Portfolio Equity card fills its cell** (`h-full flex flex-col`, backtest strip
  `flex-1`) — no more dead white space below it when there's no backtest.
- **Stale saved layout reset**: `LAYOUT_VERSION` bump drops a user's persisted
  `overrides` on hydrate (client + server prefs mirror) so the corrected defaults
  show — the root cause of the user's Prices-at-the-bottom + gap view.

## KEEP (remaining, by design)

- **Gaps-v8 additions the mockup predates** — decision-board second slot, price
  alerts panel, bet-math line, open-risk table, unrealized P&L in the positions
  badge, timezone labels on timestamps, `30m` timeframe. Additive; removed nothing.
- **Calibration/leaderboard empty states** — mockup shows populated fixtures; ours
  refuse to fabricate numbers until samples exist.

## Evidence index

`docs/verification/design-parity/`: `mockup-{screen}-{theme}.png` (14),
`mockup-overlay-*.png` (4), `mockup-state-*.png` (4), `ours-*` before set (18),
`after-*` post-fix set (12). Mockup source under `mockup-src/`.
