# Prompt: Reskin the TradingAgents Pro dashboard to the new design

Copy everything below into Claude Code (or hand it to a developer) from the repo root.

---

You are reskinning the existing React frontend in `frontend/` (Vite + React 19 + TypeScript + Tailwind v4). **Do not change behavior, routes, data flow, or component logic** — this is a visual/UX reskin of the existing app. All queries, stores, safety rules (DirectionBadge, honest empty states, StatusStrip semantics) stay exactly as they are.

A working HTML mockup of the target design exists ("Accops Trading Dashboard 3D.dc.html"); the specs below are extracted from it and are the source of truth.

## 1. Design tokens — replace `src/styles/globals.css` values

Light is the new default (`:root`); dark via `[data-theme="dark"]`. Keep the existing token *names* and `@theme inline` mapping so Tailwind classes keep working; only change values, and add the new ones.

Light:

```css
--bg: #eef1f7;            /* page: linear-gradient(160deg, var(--bg), #f7f9fc) */
--surface: rgba(255,255,255,0.9);   /* cards, with backdrop-filter: blur(16px) */
--surface-solid: #ffffff;           /* dialogs, sticky table headers */
--surface-2: #f4f6fa;               /* inset tiles, segmented controls */
--border: #e4e8f0;  --border-strong: #cfd6e4;
--fg: #1a2130;  --fg-muted: #5a6474;  --fg-subtle: #8a93a6;
--brand (accent): #2456c5;  --brand-strong: #1c46a6;  --brand-muted: rgba(36,86,197,0.10);
--bull: #16824a;  --bull-muted: rgba(22,130,74,0.12);
--bear: #d33b35;  --bear-muted: rgba(211,59,53,0.12);
--neutral: #b07b10;  --neutral-muted: rgba(176,123,16,0.12);
--stale: #9a8a58;  --locked: #8a93a6;  --live: #2fae66;
--navy: #2c3547;  --navy-2: #222a3b;   /* reserved accent (ticker chip) */
--shadow-card: 0 1px 2px rgba(26,33,48,0.04), 0 10px 28px -14px rgba(26,33,48,0.12);
--shadow-hover: 0 2px 4px rgba(26,33,48,0.05), 0 20px 44px -18px rgba(26,33,48,0.2);
```

Dark:

```css
--bg: #141a28 (gradient to #10151f);
--surface: rgba(30,38,55,0.9); --surface-solid: #1e2637; --surface-2: #27314b;
--border: #2b3550; --border-strong: #3a466a;
--fg: #edf1f8; --fg-muted: #a5afc4; --fg-subtle: #7c87a0;
--brand: #7d9ef2; --brand-strong: #97b2f5; --brand-muted: rgba(125,158,242,0.15);
--bull: #41bb77; --bear: #f0564f; --neutral: #e0a53a; --live: #41bb77;
--navy: #1b2232; --navy-2: #151c2a;
```

Typography: `--font-sans: "Plus Jakarta Sans", system-ui, sans-serif` (weights 400–800, self-host or Google Fonts); keep `--font-mono: "JetBrains Mono"`. Base 14px. All prices/metrics stay mono + `tabular-nums`.

Radii: cards 20px; inner tiles/inputs/buttons 10–14px; pills 9999px. KPI tiles 16px.

Card recipe (restyle `src/components/ui/card.tsx`): `background: var(--surface); backdrop-filter: blur(16px); border: 1px solid var(--border); border-radius: 20px; box-shadow: var(--shadow-card); padding: 20px 24px`. Hover (interactive cards only): `translateY(-3px)` + `--shadow-hover`, transition `transform .4s cubic-bezier(.2,.8,.2,1)`.

Card title style (CardTitle): 11px, weight 700, uppercase, `letter-spacing: 0.09em`, color `--fg-subtle` — **not** accent-colored anymore.

Background: two fixed radial blur "blobs" behind content (blue rgba(36,86,197,.09) top-right, violet rgba(122,92,240,.06) bottom-left, `filter: blur(60–70px)`, slow float keyframes, `pointer-events:none`). Respect `prefers-reduced-motion`.

## 2. App chrome

**Top bar** (`src/app/StatusStrip.tsx`) — floating white-glass bar, 18px radius, 14px page padding around the whole app (`padding:14px; gap:12px` between chrome pieces):
- Left: current page title (16px, 800) + one-line subtitle (11px, `--fg-subtle`).
- Search field (250px, radius 12, `--surface-2`, magnifier + "Search markets, runs…" + `⌘K` kbd chip) → opens the command palette.
- Right cluster: LIVE pill (bull-muted bg, pulsing 7px dot, `livePulse` keyframe, updated-time), regime/session pill, risk pill, `monitor only`/`KILL SWITCH` states, **navy ticker chip** (`--navy` bg, mono, BTC price flashes bull/bear per tick), bell button with unread badge, theme toggle. 36px square icon buttons, radius 12.
- Responsive: hide regime/session + XAU ticker below 1250px; subtitle, search and BTC chip below 980px.
- Halt banner stays above everything: `--bear` bg, white bold text, radius 16.

**Sidebar** (`src/app/Sidebar.tsx`) — white-glass panel, 216px, radius 20:
- Wordmark "TradingAgents Pro" + tagline; section labels `MENU` / `SYSTEM` (10px, 700, tracking 0.12em).
- Items: icon (19px lucide) + 13px/600 label, radius 12, padding 9px 12px. Active = solid `--brand`, white text, shadow `0 8px 18px -8px rgba(36,86,197,0.6)`. Hover = `--surface-2`. Trade item carries a live-pulse dot.
- Bottom: session card (`--surface-2`, radius 14): purple-gradient avatar circle (linear-gradient(135deg,#7a5cf0,#5b3fd6)), username, green "Session Active" row.
- Below 1150px collapse to 72px icon-only (hide labels/user text, show hairline separators). Keep the existing mobile bottom-bar behavior if present.

## 3. Screens (keep all existing data wiring)

**Home** — replace the react-grid-layout skin, keep WidgetGrid mechanics (drag/hide/presets). Layout: 2-column grid `1.55fr / 1fr`, 14px gaps, stacking below 1020px.
- Decision hero: kicker "AI DECISION — {symbol} · {tf}" + regime pill; big BUY chip (28px/800 in `--bull-muted` rounded 14, inset 1px bull ring); stats row separated by hairline left-borders (confidence 24px mono, R:R, votes ▲–▼); **level ladder**: TP3/TP2/TP1/ENTRY/STOP as 8px rounded progress bars (bull gradient widths ~92/66/38%, ENTRY brand ~24%, STOP bear ~12%) with mono price + %·size columns; invalidation note in borderless `--neutral-muted` rounded 12; footer meta + primary CTA "Open full reasoning →" (brand button, radius 12, shadow).
- Portfolio card: brand gradient (135deg `--brand` → #1a3f96), white text, equity 34px mono, P&L/win-rate row, inset translucent "Backtest equity" sparkline strip, ghost white "Open portfolio →".
- Price cards: symbol + LIVE/EOD pill, 17.5px mono price (tick-flash color), 30d sparkline, source line.
- Alerts: severity as small pills (WARNING neutral-muted / INFO brand-muted), divided rows.
- Since you left / What's next / Watchlist: same content, new card skin; watchlist rows get a 2-letter tile (`--surface-2`, radius 10) before the symbol.

**Trade** — grid `1fr / 320px` (stacks <1100px). Chart card: symbol 18px/800 + live pill (REPLAY badge in neutral-muted while replaying); segmented controls for timeframes and series styles (container `--surface-2` radius 12, active segment = white/`--surface-solid` chip with brand text + small shadow); Indicators dropdown, Compare toggle, full-screen button; replay controls row (play/pause/step/speed 1–10×/scrubber/exit + "replayed history — live ticks suspended"); drawing toolbar column (select/trend/hline, count, clear); chart area on `--surface-2` radius 16 with dashed level lines ending in white-on-color mono chips (TP bull, ENTRY brand, STOP bear); EMA line = `--brand`. Right rail: compact decision card + internals as label/value rows on `--surface-2` tiles (radius 14).

**Decisions** — grid `250px / 1fr / 310px` (stacks <1100px). Run rail cards radius 14 (selected = brand border + `--brand-muted`); filter pills (active = solid brand); Run button opens the run dialog; verdict card shows the pipeline-progress chip while running; gate waterfall pills in bull-muted with check icons; consensus bar 22px rounded with inset shadow; debate timeline with 3px team-colored left borders and mono citation chips; evidence sections with hoverable data-ref chips (`--surface-2`, mono, `title` tooltip); calibration SVG (brand points, hollow = insufficient sample) + leaderboard table.

**Portfolio** — equity card with "simulation — not live P&L" dashed stale pill, curve + optional drawdown pane on `--surface-2`, MC p5/p50/p95/P(loss) row; 6 KPI tiles (radius 16, 9.5px ellipsized labels, 16.5px mono values, 2-col → 3-col under 1100px); trades table with action pills and "view reasoning →" links; Report (PDF) button = brand primary → `/report`; journal lessons (mistake/win pills) + integrity card.

**Intel** — regime board strip; 5 metric group cards (2-col) of `--surface-2` tiles incl. "Gold positioning & vol" as honest empty state; correlations matrix (strong |r|≥.5 colored bull/bear); calendar; feed coverage (dashed stale chips for degraded, lock rows + provider pills for unsubscribed).

**Settings** — max-width 680px stack: Appearance + preset buttons as solid-brand-when-active segments; data connections (mono input); saved views; muted types; kill-switch card with `rgba(211,59,53,0.35)` border, HALT confirmation reveal unchanged.

**Report** (`/report`) — centered 760px sheet on `--surface-solid`, radius 20, generous 36/40 padding; print CSS hides all chrome and flattens the sheet (no border/shadow).

## 4. Overlays

- **Command palette**: dimmed blurred backdrop `rgba(16,21,31,0.45)`; panel 540px, radius 18, top 88px; input row with esc chip; grouped items with kbd chips; existing cmdk wiring.
- **Notification center**: right slide-over inset 10px, radius 18 (floating, not full-bleed); unread cards = `--surface-2` + strong border; mark-read/mute-type/mark-all.
- **Run pipeline dialog** + **Shortcuts cheatsheet**: centered `--surface-solid` dialogs, radius 18; pair/timeframe as solid-brand segmented buttons; progress box in `--brand-muted` mono.
- **Auth gate**: token card centered on the page gradient, brand Unlock button, lock-icon "Your security is our priority" footer.
- **Update toast**: bottom-right floating card, brand Refresh button.

## 5. Rules that must survive the reskin

- Direction always renders via `<DirectionBadge>` (glyph + word + color). Never color alone.
- Every widget keeps its empty / degraded / error / locked states; stale = dashed `--stale` border treatment.
- Status strip + halt banner remain outside any layout grid and non-customizable.
- No behavior changes to stores, queries, SSE, shortcuts (`⌘K`, `g`-chords, `1–7`, `⇧D`, `f`, `?`, `/`).
- `prefers-reduced-motion` disables blob float, pulses, and hover lifts.
- Contrast: verify all pill text on muted backgrounds meets 4.5:1 in both themes.

Work screen by screen (globals → chrome → Home → Trade → Decisions → Portfolio → Intel → Settings → Report → overlays), keeping Storybook stories and tests passing (`npm test`, `npm run e2e`); visual snapshots may be updated.