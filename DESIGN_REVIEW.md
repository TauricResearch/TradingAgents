# Design Review — "Accops" light-glass reskin

**Scope reviewed:** commits `2d73063..1edf2ba` (34 files) against [IMPLEMENTATION_PROMPT.md](IMPLEMENTATION_PROMPT.md).
**Baseline:** `55dde8b` (last pre-reskin commit — the branch has no `main` merge-base for this work).
**Method:** independent hunk-by-hunk diff audit (fresh-context agent, no implementation history), static grep sweep, measured WCAG contrast audit (computed, not eyeballed), 64-shot screenshot matrix (8 routes × 2 themes × 1440/1200/1000/390 px) against the seeded demo server, scripted functional checks (overlays, keyboard loop, focus, reduced-motion, print, forced halt state), full test gates.
**Note on provenance:** `IMPLEMENTATION_PROMPT.md` did not exist in the repo; the spec was recovered verbatim (10,422 chars) from the session transcript and committed alongside this review. The reviewer is the implementer; the diff audit was therefore delegated to a fresh-context agent and every claim below is backed by a measurement, a test, or a screenshot in `docs/verification/reskin-review/`.

## 1. Verdict

**Ship with nits** — after fixing the contrast blockers found by this review (fixed in the same commit as this report; all measurements below marked *fixed* re-verified post-fix).

The diff upholds "no behavior change": no queries, stores (beyond the operator-approved theme default), SSE, routing, shortcuts, handlers, or safety semantics changed. All 66 testids, `role="alert"` banners, and honesty labels survive. All test gates green: 28 vitest, 36 Playwright e2e, 1167 backend pytest, bundle 170,863 gz < 200 KB budget.

## 2. Blockers (all fixed in this review's commit)

| # | Finding | Measured | Fix | After |
|---|---------|----------|-----|-------|
| B1 | `--fg-subtle` on `--surface-2` failed both themes (explicit checklist item). Affects StatCard labels, tile captions, rail timestamps. | light 2.85, dark 3.58 | light `#8a93a6`→`#646f84`, dark `#7c87a0`→`#93a0bb` | 4.68 / 4.91 |
| B2 | **Dark-mode safety chrome unreadable**: dark `--accent/--bear/--neutral` are light-valued, so `text-white` on solid fills failed — halt banner (white/`#f47f79` = 2.57), arming banner (2.18), Emergency Flatten button, primary buttons, sidebar active item, Decisions filter pills, hero CTA. The pre-reskin dark design used near-black text on these (~5:1), so this was a genuine regression. | 2.18–2.61 | new `--on-solid` token (`#ffffff` light / `#10151f` dark) applied at all 8 solid-fill sites | 7.00–8.37 |
| B3 | Home portfolio gradient card in dark started at `var(--brand)` = `#7d9ef2` → white equity figure at 2.61. | 2.61 | gradient pinned to literal `#2456c5→#1a3f96` (identical in light; deep blue in dark) | 6.54 |
| B4 | Chart TP/ENTRY/STOP price-line axis chips: LWC default white label text on token colors failed in dark (white/bull `#41bb77` = 2.44). | 2.44–2.61 | `axisLabelTextColor: colors.onSolid` on all three `createPriceLine` sites | 7.0+ |
| B5 | Dark `--stale` on surface marginal fail. | 4.40 | `#9e8747`→`#a89050` | 4.95 |

Post-fix contrast table (26 pairs, both themes, incl. every muted pill, `--fg-subtle`/`--surface-2`, all solid fills, navy ticker): **all ≥ 4.5:1**. Script + raw numbers: review transcript; spot-check with the values in `globals.css` comments.

## 3. Out-of-scope defect found (NOT a reskin regression)

Navigating Home → Trade → Portfolio → Trade in one SPA session crashes the Workspace to its error boundary ("Value is undefined" at `removeSeries`; "Object is disposed"). **Reproduced identically on the pre-reskin build at `55dde8b`** (worktree build, same Playwright sequence), so it predates the reskin. Filed as a follow-up task with repro steps; suspects are the chart lifecycle in `useLightweightChart.ts` / `PriceChart.tsx` rebuild-vs-dispose ordering. Direct URL loads and single Trade visits are unaffected (which is why the 36-test e2e suite never hit it).

## 4. Spec deviations (intentional, disclosed)

| Spec item | Implemented | Evidence |
|---|---|---|
| Palette values: light bull `#16824a`, bear `#d33b35`, neutral `#b07b10`, stale `#9a8a58`; dark bear `#f0564f` | WCAG-adjusted: `#157945`, `#c4302b`, `#8b610d`, `#766a44`; dark bear `#f47f79` — the spec's own rule 6 (4.5:1 on muted pills) failed with its literal values (4.14/3.97/3.23/3.41; dark bear 3.74). Hue preserved, minimal shifts. This review further adjusted `--fg-subtle` (both), dark `--stale`, and added `--on-solid` (see Blockers). | contrast tables above |
| Home: 2-col `1.55fr/1fr` CSS grid | react-grid-layout widgets approximating that ratio; drag/hide/presets mechanics preserved (spec requires keeping WidgetGrid mechanics — the two goals conflict; mechanics won) | `desktop-*-home.png` |
| Top bar: "Search field (250px)" | A 250 px button styled as a field that opens the palette (spec's stated behavior). Not a focusable text input. | `desktop-light-home.png` |
| Responsive hiding at 1250/980 px | Implemented, but in the ~980–1120 px window the right cluster wraps to a second row ("nothing wraps" checklist item). Renders cleanly (flex-wrap, no overflow/clipping). | `narrow-light-home.png` |
| Theme persistence | One-time forced migration: a user's previously persisted explicit dark choice is reset to light once (persist `version: 1` + `migrate`). Operator-approved. Migrate provably preserves all other persisted keys. | diff audit |
| Ladder bar widths "~92/66/38%" | 92/65/38/24/12 hardcoded decorative ranks (bars never encode price — by design, honest) | `desktop-light-home.png` |
| ConnPill "updated-time" | Time only; the word "updated" was dropped | nit N4 |

Verified compliant (not deviations): Workspace symbol title 18 px/800 normal-case is the spec's own Trade exception; hover lift only on `interactive` cards matches spec §1; card titles 11 px uppercase `--fg-subtle`; `font-display: swap` present for both font families (no invisible-text period).

## 5. Nits — all addressed in the follow-up commit (except 8, environmental)

1. **Portfolio snapshot CTA clipped** by the default Home widget height — FIXED: default/min layout height 6→7 / 5→6 (persisted user layouts unaffected).
2. **Home P&L lost its bull/bear tone** on the gradient card — FIXED: toned chip (white base, bull/bear text — legible on the gradient in both themes); plain white kept for the null case.
3. **Hero DecisionCard dropped the sr-only Level/Price/Detail headers** — FIXED: sr-only header line restored in the ladder.
4. ConnPill timestamp lost the word "updated" — FIXED: wording restored.
5. `drawings/primitive.ts` old-palette fallback constants + never-overridden `fibFill` — FIXED: fallbacks aligned to the current palette, and `PriceChart` now passes a theme-derived `fibFill` via `setDrawings`.
6. Two same-labeled search buttons in the DOM — FIXED: the <981 px icon variant is labeled "Search (Cmd+K)" (distinct from the field's "Search and commands (Cmd+K)").
7. Agent leaderboard clipping in the 310 px rail — FIXED: horizontal scroll instead of clipping; hit-rate cell nowrap.
8. Console `wss://stream.binance.com` warnings on this network — WON'T FIX: geo-blocked environment; the transport fallback is pre-existing, deliberate, and surfaced honestly via "degraded" chips. Zero app errors/warnings otherwise in both themes across all 7 routes.

## 6. Behavior & safety checklist results

- **DirectionBadge everywhere** — hero chip wraps `DirectionBadge` (glyph+word+color); run-rail, ticker, consensus all use it. PASS (diff audit + screenshots).
- **Honest states** — EOD dashed stale pills, "waiting for first tick", "monitor mode", calibration "needs scored outcomes", Intel locked rows, quarantine badge all render. PASS (`desktop-light-home.png`, `desktop-dark-decisions.png`, `*-intel.png`).
- **Status strip + halt banner outside the grid, non-customizable** — AppShell order unchanged; forced-halt render verified in both themes with `role="alert"` (`extra-halt-{light,dark}.png`). PASS.
- **Shortcuts** — ⌘K, palette filter, Esc, g-chords, timeframe `4`→1h (`aria-pressed=true`), ⇧D theme flip (`data-theme` light↔dark), `f` native fullscreen on/off, `?` cheatsheet: all PASS (scripted; the three Trade-page checks pass in a clean flow and only fail downstream of the §3 pre-existing crash).
- **Overlays** — palette, notification center, run dialog (radix `aria-labelledby`, focus trapped over 12 Tabs, Esc closes), cheatsheet: PASS (`extra-overlay-*.png`).
- **Reduced motion** — blob `animation: none`, pulse/lift durations 0.01 ms under `prefers-reduced-motion: reduce`. PASS.
- **Print** — `/report` print emulation hides header/nav/blobs, white body. PASS (`extra-report-print.png`).
- **Focus visible** on segments/icon buttons; icon-only buttons carry aria-labels ("Toggle theme", "Notifications (n)", "Full screen (f)", "Search and commands"). PASS.
- **Tests** — 28 vitest, 36 e2e (6 skipped: iPhone/webkit profile, as always), 1167 backend pytest, tsc/eslint clean, bundle 170,863 gz. PASS.
- **Grep sweep** — no old GitHub-palette hexes outside nit 5, no `dark:` utilities, no Inter/Roboto refs, chart gradients token-derived. PASS.

## 7. Evidence index

`docs/verification/reskin-review/` — 71 PNGs, captured from the seeded demo (`scripts/pro_dashboard_demo.py`), post-fix:
- `{desktop,laptop,narrow,mobile}-{light,dark}-{home,workspace-gold,workspace-btc,decisions,portfolio,intel,settings,report}.png` — the 64-shot matrix (1440/1200/1000/390 px)
- `extra-halt-{light,dark}.png` — forced halt banner (injected `/api/status`)
- `extra-overlay-{palette,notifications,rundialog,cheatsheet}.png`
- `extra-report-print.png` — print emulation

Reviewed-by: Claude (Fable 5), 2026-07-13.
