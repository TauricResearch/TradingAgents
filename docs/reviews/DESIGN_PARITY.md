# Design Parity Audit — implementation vs "Accops Trading Dashboard 3D copy.dc.html"

**Date:** 2026-07-14 · **Ground truth:** the design-canvas mockup (source saved at
`docs/verification/design-parity/mockup-src/`, fetched from the shared claude.ai
design project with the operator's approval; rendered locally for capture parity).
**Method:** token-level diff of the mockup's `:root`/`[data-theme=dark]` blocks vs
`frontend/src/styles/globals.css`, plus a same-viewport (1440×900) screenshot matrix
of every screen in both themes — `mockup-*` vs `ours-*` (before) and `after-*`
(post-fix) in `docs/verification/design-parity/`.

## Verdict

After this pass the implementation matches the mockup on every screen and token
except the **KEEP list** below — each kept deviation is either a measured
accessibility fix or an additive feature that shipped after the mockup was drawn
(gaps v8). No safety rule was traded for pixels.

## Token diff

Light and dark base palettes match the mockup exactly (`--bg #eef1f7`,
`--surface rgba(255,255,255,0.9)`, `--brand #2456c5`/`#7d9ef2`, navy pair, radii,
card/hover shadows). Deltas:

| Token | Mockup | Ours | Resolution |
|---|---|---|---|
| `--chrome-fg`, `--chrome-fg-muted` | `#eef1f7` / 65% | missing | **FIXED** — added both themes; navy ticker chip now uses them |
| `--shadow-chrome` | heavy chrome shadow | missing | **FIXED** — added both themes |
| light `--bull/--bear/--neutral/--stale`, `--fg-subtle` | `#16824a/#d33b35/#b07b10/#9a8a58/#8a93a6` | `#157945/#c4302b/#8b610d/#766a44/#646f84` | **KEEP** — mockup values measure < 4.5:1 on their own muted/surface pairings (DESIGN_REVIEW.md contrast tables); hue preserved |
| dark `--bear` | `#f0564f` | `#f47f79` | **KEEP** — same reason (3.7:1 on dark surfaces) |
| dark `--stale`, `--locked` | `#9e8f5c/#6e7891` | `#a89050/#7c87a0` | **KEEP** — contrast-adjusted |

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

## KEEP (deliberate deviations, flagged not hidden)

- **WCAG token adjustments** (table above) — "100% match" does not override
  measured 4.5:1 contrast; the mockup's own spec lists contrast as a survival rule.
- **P&L white chip on the gradient card** — mockup paints bull-green text directly
  on the gradient (≈2.8:1); the chip keeps the tone legible.
- **Session card identity** — mockup shows `ajay.kumar`; the product has no user
  identity system (token auth only), so "Operator" stays honest.
- **Gaps-v8 additions the mockup predates** — decision-board second slot, price
  alerts panel, bet-math line, open-risk table, unrealized P&L in the positions
  badge, timezone labels on timestamps, `30m` timeframe. Additive; removed nothing.
- **Gate waterfall shows all real nodes** — the mockup collapses debaters into one
  "Debate" chip; we humanize names but never hide a gate the decision actually
  passed (honesty rule).
- **Calibration/leaderboard empty states** — mockup shows populated fixtures; ours
  refuse to fabricate numbers until samples exist.

## Evidence index

`docs/verification/design-parity/`: `mockup-{screen}-{theme}.png` (14),
`mockup-overlay-*.png` (4), `mockup-state-*.png` (4), `ours-*` before set (18),
`after-*` post-fix set (12). Mockup source under `mockup-src/`.
