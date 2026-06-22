# TradingDesk — native macOS app for TradingAgents

TradingDesk is a native macOS app (SwiftUI, macOS 14+, built with Xcode 26 /
Swift 6) that drives the existing TradingAgents engine **without modifying the
core agent graph**. It reconceives the CLI's one-shot wizard as a persistent
research workspace: a watchlist of tracked tickers, runs as permanent
documents, a decisions journal that closes the loop with realized alpha, and a
live "watch the agents work" theater.

![TradingDesk — the workspace after a completed NVDA run: the Watchlist with live decisions, the per-ticker Journal, and the Live Monitor's timeline + Agent Theater.](images/tradingdesk.png)

This document records **what** each piece is, the **logic** behind it, and
**how** it was built, so the project can be picked up cold.

---

## 1. Architecture

```
TradingDesk.app (SwiftUI)                         Docker container (python:3.12-slim)
  RootSplitView ── DockerBackendController ──────▶ desk-server (FastAPI + uvicorn)
     │  start container, poll /health                 │  desk_server.app
     │                                                 ├─ desk_adapter.diff  (snapshots → events)
  RunCoordinator ── HTTP + SSE @127.0.0.1:8765 ──────▶ ├─ TradingAgentsGraph.stream_run() (engine, unchanged graph)
     │  POST /runs · GET /runs/{id}/events (SSE)        ├─ LLM clients (18 providers) → cloud
  CapabilitiesStore / JournalStore / ReportStore       └─ dataflows (yfinance / FRED / news / …)
  KeychainStore (provider keys → injected as run env)
```

**Why a Docker backend instead of bundling Python.** The engine requires Python
≥3.10 with a heavy native dependency tree (langgraph, langchain, pandas,
yfinance, …). Shipping that as a notarized, relocatable interpreter inside the
`.app` is the single hardest packaging problem. Running the engine as a Docker
container the app starts on launch removes that problem entirely (the `.app`
stays a lightweight Swift app), gives crash isolation, and reuses the repo's
existing `Dockerfile`. The one prerequisite is Docker Desktop being installed.

**Why a local HTTP + SSE channel.** A run is a minutes-long, incrementally
streaming multi-agent pipeline. Server-Sent Events over `127.0.0.1` (loopback,
never exposed) map cleanly onto that one-directional stream and are consumed
natively by `URLSession.bytes(for:).lines`. The event payloads are the same
objects the NDJSON adapter produces, so the wire format is shared.

**Why the engine graph is untouched.** All host glue lives in two new top-level
Python packages (`desk_adapter/`, `desk_server/`) plus a small, additive set of
engine methods. The CLI and library behavior are unchanged.

---

## 2. Repository layout

| Path | Role |
|---|---|
| `desk_adapter/` | Host adapter: NDJSON event protocol + snapshot→events diff + run/introspect/resolve subcommands. Dependency-light. |
| `desk_server/` | FastAPI app served inside the Docker image; streams events over SSE and exposes read/control endpoints. |
| `macos/TradingDesk/` | The SwiftUI app (SwiftPM package) + dev build/sign scripts. |
| `packaging/` | `requirements-bundle.txt` (pruned dep set) and `build-and-save-image.sh` (bundle the engine image into the app). |
| `tradingagents/graph/trading_graph.py` | Engine: added `stream_run()` + public resolve methods (additive). |
| `tradingagents/__init__.py` | Engine: `TRADINGAGENTS_NO_DOTENV` guard (additive). |
| `tests/test_desk_*` | Unit tests for the adapter diff, protocol, and server event framing. |

---

## 3. The engine adapter (`desk_adapter/`)

### 3.1 Event protocol — `protocol.py`
- **What.** A versioned NDJSON channel: one JSON object per line, envelope
  `{v, run_id, seq, ts, type, …}`. `Emitter` serializes events; `reserve_stdout()`
  dups the real fd 1 and redirects fd 1 + `sys.stdout` to stderr.
- **Why.** The app needs an unambiguous machine channel. The engine's
  dependency tree prints stray text and warnings to stdout (verified: stray
  `print()` in several `dataflows` modules); without reserving fd 1 those would
  corrupt the stream. `seq` enables dedupe/drop-detection and SSE `Last-Event-ID`.
- **How.** `Emitter.emit(type, **fields)` writes `json.dumps(separators=(",",":"))`
  + `"\n"` to the saved fd 1; everything else is pushed to stderr. Dependency-free
  so it's importable/testable on any interpreter.

### 3.2 Snapshot → events — `diff.py`
- **What.** `SnapshotDiffer` turns consecutive `stream_mode="values"`
  whole-state snapshots into typed events: `node_status`, `report_section`,
  `agent_step`, `tool_call`, `tool_result`, `debate_turn`.
- **Why.** LangGraph streams the **entire accumulated state** each step (not
  clean deltas), so the host must diff successive snapshots to derive "what's
  new." Putting that logic once, server-side, keeps the brittle parts (dedupe
  by message id, list-or-str content, debate-count math) in one place rather
  than re-implemented in Swift.
- **How.** Ports the CLI's proven derivation (`cli/main.py`:
  `classify_message_type`, `extract_content_string`, `format_tool_args`, the
  analyst-status state machine). Duck-typed on `.type`/`.content`/`.tool_calls`/
  `.tool_call_id` so it needs neither `tradingagents` nor `langchain` and runs
  under the unit tests. Tool results are matched to their call via
  `tool_call_id`; `NO_DATA_AVAILABLE` is detected from `ToolMessage` content;
  debate turns are reconstructed by diffing the speaker-prefixed `history`
  strings in `investment_debate_state` / `risk_debate_state`.

### 3.3 Run driver / introspection / env — `run.py`, `introspect.py`, `env.py`, `__main__.py`
- **What.** `python -m desk_adapter <run|capabilities|resolve>`. `run` drives a
  run and emits NDJSON; `capabilities` dumps the provider/model surface;
  `resolve` realizes pending outcomes without a paid analysis.
- **Why.** A single, thin, testable entry that the server (and a future
  subprocess fallback) reuse. `capabilities` makes the Settings UI source its
  lists from the engine so they never drift.
- **How.** `env.prepare_environment()` sets `TRADINGAGENTS_NO_DOTENV=1` and
  redirects results/cache/memory dirs **before** importing the engine.
  `introspect.build_capabilities()` reads `PROVIDER_API_KEY_ENV`,
  `OPENAI_COMPATIBLE_PROVIDERS`, `model_catalog.get_model_options`,
  `capabilities.get_capabilities`, plus the language and data-vendor lists.

---

## 4. Engine changes (additive) — `tradingagents/`
- **`TradingAgentsGraph.stream_run(company, date, asset_type)`** — a generator
  sibling of `propagate()`. **Why:** the CLI streams `graph.stream` directly and
  thereby *skips* `propagate()`'s side effects (writing `full_states_log` JSON,
  appending the decision to `trading_memory.md`, resolving prior outcomes).
  `stream_run` yields each snapshot for live UI **and** performs those side
  effects, so history/journal have a backing store. **How:** mirrors
  `_run_graph` around a `for chunk in self.graph.stream(...)` loop; the last
  values-snapshot is the final state.
- **`resolve_pending_entries()` / `resolve_all_pending()`** — public wrappers so
  the "Refresh outcomes" path doesn't call a private method.
- **`TRADINGAGENTS_NO_DOTENV` guard** in `__init__.py` — the package auto-loads
  `.env` at import; the app injects keys itself and must never pick up a stray
  `.env`, so this opt-out skips it.

---

## 5. FastAPI backend (`desk_server/`)
- **What.** A FastAPI app (`app.py`) run by `desk-server` inside the container.
  Endpoints: `GET /health`, `GET /capabilities`, `GET /journal[?ticker]`,
  `GET /reports[?ticker[&date]]`, `GET /search?q=`, `GET /prices?ticker=&days=`
  (yfinance daily closes for watchlist sparklines), `GET /openrouter/models`,
  `POST /test`, `POST /test_fred`, `POST /runs`, `POST /runs/{id}/cancel`,
  `GET /runs/{id}/state`, `GET /runs/{id}/events` (SSE).
- **Why.** Wrap the engine over localhost so the app reuses the adapter's event
  logic as SSE. `/capabilities` + `/openrouter/models` feed Settings;
  `/journal` + `/reports` back the workspace's history surfaces; `/search` backs
  the command palette's real-ticker lookup; `/test` + `/test_fred` power per-row
  connectivity checks.
- **How (`/search`).** A thin proxy of Yahoo Finance's public search endpoint
  (`query2.finance.yahoo.com/v1/finance/search`, browser UA, no key), returning
  `{results: [{symbol, name, exchange, type}]}` — real listed instruments for the
  palette. Same shape as the `/openrouter/models` proxy (`asyncio.to_thread`,
  502 on upstream failure); egress works because the container already reaches
  Yahoo for yfinance.
- **How (streaming).** `runner.run_blocking` runs the synchronous
  `graph.stream_run` on the loop's executor thread and pushes each event onto
  the run's buffer via `loop.call_soon_threadsafe`; the SSE generator
  (`events.sse_format`) drains that buffer and supports `Last-Event-ID` resume.
- **How (keys).** `POST /runs` (and `/test`) carry a `keys` map; the server
  sets those as `os.environ` entries just before constructing the graph, so the
  engine's clients (which read `os.getenv`) pick them up. Loopback-only; never
  written to disk. `build_engine_config` maps the Profile JSON onto
  `DEFAULT_CONFIG` (and skips `keys`).
- **How (Docker).** The `Dockerfile` installs `.[server]` (adds FastAPI +
  uvicorn); the `desk-server` compose service publishes `127.0.0.1:8765`, has a
  healthcheck, mounts the data volume, and accepts host-injected provider/data
  keys via `${VAR:-}` passthrough.

---

## 6. Backend lifecycle (`DockerBackendController.swift`)
- **What.** On launch the app locates Docker, ensures the engine image exists
  (loads a bundled image tar if present, else `docker compose build`), runs
  `docker compose up -d desk-server`, and polls `/health` until ready, surfacing
  each phase (`checkingDocker`/`preparingImage`/`starting`/`ready`/`failed`/
  `dockerMissing`).
- **Why.** "Launch the app, the backend just runs" — the user configures no
  Python/deps. Surfacing the phases (and a clear "Docker not available" state)
  keeps the multi-second cold start honest.
- **How.** `Process` shells out to the `docker` binary (searched across common
  paths, PATH augmented), `async` via continuations off the main actor; health
  via `URLSession`. `bundledImageTar()` enables the ship-in-app `docker load`
  path; `packaging/build-and-save-image.sh` produces that tar.

---

## 7. The workspace (the app surfaces)

### 7.1 Watchlist sidebar — `Watchlist.swift`, `WatchlistStore.swift`
- **What.** A persisted set of tracked tickers, each row showing the symbol, its
  **latest real decision** (rating chip + realized gain/loss since that date),
  and a **stale clock** when the last decision is over two weeks old; tickers
  with no runs show "no runs yet". The footer pins the **backend status** and the
  **Settings gear**. (Adding/searching now lives in the title-bar command
  palette — §7.4; the sidebar is a plain tracked list, remove via row context
  menu.)
- **Why.** The workspace's spine is the tracked ticker (the README's real loop:
  "track names, periodically re-analyze"), so the sidebar must reflect *live*
  engine state, not mock rows. Global state (backend) belongs in the sidebar
  footer, not per-ticker views.
- **How.**
  - `WatchlistStore` (`@MainActor @Observable` singleton) is the source of truth:
    it holds the tracked **symbols** (persisted to `UserDefaults`, seeded with a
    default basket on first launch via `Instruments.defaultSymbols`) and a live
    `[symbol: JournalEntry]` map of the **latest decision per ticker**. `load()`
    fetches `GET /journal` (all tickers, server-sorted newest-first) once and
    keeps the first entry seen per symbol. `add`/`remove` mutate + persist the
    symbol list; the decisions always come from the engine, so the watchlist
    can't drift from reality.
  - Selection is the ticker **symbol** (a `String`), so the whole 3-pane shell is
    driven by the live list. `RootSplitView` reads `watch.tickers`
    (symbol + display name + benchmark + latest), and `.id(symbol)` recreates the
    desk/monitor cleanly per ticker.
  - Parsing is shared: `JournalEntry.from(_:)` (in `Model.swift`) is used by both
    `WatchlistStore` (latest-per-symbol) and `JournalStore` (full journal).
    `Instruments` provides client-side display name, benchmark (BTC for `-USD`,
    else SPY), and symbol normalization; the engine resolves the real identity at
    run time.
  - `List(selection:)` of `WatchlistRow`; `.safeAreaInset(.bottom)` for the
    footer. Row colors are selection-aware (see §9); the stale check parses the
    engine's ISO `yyyy-MM-dd` dates and renders "since Jun 13"-style labels.
  - **Live refresh.** When a run finishes, `RunCoordinator` reloads the store and
    posts `.runCompleted`; the just-run ticker's row updates without polling.

### 7.2 Ticker Desk: Journal + Library — `Workspace.swift`, `Library.swift`
- **What.** A segmented Library/Journal view. **Journal** = the ticker's
  decisions (rating, realized raw %/alpha, holding days, or "pending — resolves
  on next run"). **Library** = saved run documents; opening one shows the full
  report (7 sections + bull/bear and 3-way risk transcripts + final decision) in
  a reader sheet.
- **Why.** Closes the loop the CLI throws away: every run is a permanent,
  re-openable document, and every decision auto-resolves to realized alpha on a
  later same-ticker run.
- **How.** `JournalStore` fetches `/journal`, `ReportStore` fetches `/reports`
  (list) and a single doc; both are held by `TickerDeskView` (keyed on the
  selected **symbol**) and preloaded on ticker selection (so switching tabs never
  refetches/flashes). Data is always live — a ticker with no runs shows an
  explicit "No decisions yet" state rather than mock rows. The desk re-pulls on
  `.runCompleted` (posted by `RunCoordinator`) so a finished run shows up
  immediately, plus a manual refresh button.

### 7.3 Live Monitor + Agent Theater — `LiveMonitor.swift`, `RunCoordinator.swift`
- **What.** Press **Run analysis** → a pipeline rail lights up per node, a stats
  bar ticks (llm calls / tools / tokens / elapsed), and the **Agent Theater**
  streams each agent step, tool call/result (amber on `NO_DATA`), and debate
  turn as it happens.
- **Why.** The "watch the agents research and debate" experience (the headline
  feature), built on the real node-granular stream.
- **How.** `RunCoordinator` POSTs `/runs` then consumes
  `GET /runs/{id}/events` via `URLSession.bytes(...).lines`, decoding each
  `data:` line and projecting it onto `@Observable` state via a single
  `apply(event)` mutator.
- **Run end / cancel.** A run always resolves to a **terminal node** drawn as the
  last row of the timeline: **Done** (green check + rating), **Cancelled** (muted
  stop), or **Failed** (red). When the run ends, `RunCoordinator` records a
  `terminalAt` timestamp and the per-node `elapsed(for:now:)` clamps to it, so the
  node that was in flight stops counting (and its dot drops from a pulsing accent
  to a static muted dot) instead of ticking forever. **Cancel actually stops the
  backend**: `desk_server` registers a `CancelCallbackHandler` that raises
  `RunCancelled` at the next LLM/tool/chain boundary once `handle.cancelled` is
  set, so a Stop aborts the in-flight node within one call (seconds) rather than
  running the whole multi-call node to completion; the in-flight call already on
  the wire finishes, but no new one starts.

### 7.4 Command palette — `SpotlightSearch.swift`, `SearchModel.swift`
- **What.** A search in the title bar (a "Search something…" trigger, or ⌘K)
  that opens a popover with one field over three result kinds: **Tickers** (real
  companies/symbols — hovering a row reveals an "add to watchlist" button, a
  green check if already tracked), **Runs**, and **Decisions** (click to jump —
  a run opens its full document, a decision opens the ticker's Journal).
- **Why.** One place to both *grow* the watchlist (search any real listed
  instrument, not just type a guessed symbol) and *navigate* existing work
  (jump to a past run/decision) — the workspace's Cmd-K spine.
- **How.**
  - `SearchModel` (`@MainActor @Observable`): **tickers** come from a debounced
    (250 ms) live `GET /search` so each keystroke hits Yahoo at most once;
    **runs** (`/reports`) and **decisions** (`/journal`) are loaded once when the
    palette opens (`loadCorpus`) and filtered client-side by symbol/date, so
    those are instant and offline-after-open.
  - `SearchTrigger` is a title-bar toolbar item (`.principal`); clicking it
    presents `CommandPalette` as a `.popover(arrowEdge: .bottom)` anchored right
    below. The palette's field keeps the fuller "Jump to ticker, run or decision"
    placeholder; results render in a plain `VStack` (not a `ScrollView`, which
    reports ~0 height inside a popover and collapses), tickers capped to 8.
  - **Deep-linking.** `RootSplitView` owns `deskTab` + `pendingRunDate`; a pick
    sets the selection and those, then `TickerDeskView(tab:openRunDate:)` (bound)
    applies them even when the target ticker is already selected, and
    `LibraryView` auto-opens the matching run document (retrying once its
    `/reports` list arrives).
- **Constraint (macOS 26).** The trigger can't be perfectly chrome-free: Tahoe
  wraps any title-bar control in a Liquid-Glass capsule. An arrowless
  custom-overlay dropdown was prototyped to avoid the popover arrow/pill but
  abandoned — the toolbar capsule reappears regardless and anchoring a custom
  panel under a toolbar item is brittle — so the popover is the pragmatic choice.

---

## 8. Settings, Profiles, Keychain — `SettingsView.swift`, `SettingsStore.swift`, `CapabilitiesStore.swift`, `KeychainStore.swift`
- **What.** A centered modal sheet: provider picker, deep/quick model dropdowns
  (live from the engine, incl. the OpenRouter catalog), analyst toggles, a
  **Research depth** section (a Shallow/Medium/Deep/Custom preset plus separate
  **Debate rounds** and **Risk rounds** steppers, 1–20), trade date, output
  language, per-provider API key + FRED key with **per-row connectivity test
  buttons**, an appearance switch, and a **Save** button (edits are a draft until
  saved).
- **Why.** Retires the hardcoded demo config; "configure nothing but your key."
  Sourcing lists from `/capabilities` keeps the UI from drifting from the engine.
- **How.**
  - `SettingsStore` (singleton, `@Observable`) persists the active Profile in
    `UserDefaults`; `RunCoordinator.buildBody()` maps it + Keychain keys into the
    `POST /runs` body.
  - `CapabilitiesStore` loads `/capabilities` + `/openrouter/models`; `ModelField`
    renders a Picker for catalog models or a text field for custom-only providers.
  - The **Debate rounds** / **Risk rounds** steppers map to the engine's
    `max_debate_rounds` / `max_risk_discuss_rounds` (one round = 2 bull/bear turns,
    resp. all three risk analysts speak once); the Shallow/Medium/Deep preset sets
    both to 1/3/5 and reads "Custom" when they diverge. The old single "research
    depth" (`cfg.depth`) migrates into both round counts on first launch.
  - `ConnectivityButton` calls `/test` (model: builds the client + pings) or
    `/test_fred` (validates the FRED key against the FRED API) and shows
    idle/testing/ok/failed.
  - `KeychainStore` stores keys as generic passwords (this-device-only); the run
    request carries them — they never touch disk.
  - The API-key rows are borderless native fields (label left, left-aligned
    secure entry, test button right), centered per row.
- **Reactive Run gate.** `SettingsStore.providerReady` (refreshed at launch and
  on Save) disables **Run analysis** with a "Set API key" hint until the chosen
  provider's key is present.

---

## 9. UI polish (the fixes)
- **Backend status footer** — global status pinned to the sidebar bottom (one
  compact line + gear), blending with the translucent sidebar (no opaque bar).
- **Smooth sidebar collapse/expand** — replaced hard `.frame(minWidth:)` on
  columns/window with `.navigationSplitViewColumnWidth` + a `.defaultSize`, so
  the columns animate without fighting `windowResizability(.contentMinSize)`.
- **No Journal↔Library flash** — the report store is preloaded by `TickerDeskView`
  rather than refetched on each tab switch.
- **No row-switch glitch** — `TickerDeskView`/`LiveMonitorView` get `.id(ticker.id)`
  so they recreate cleanly per ticker (no previous-ticker data bleeding in).
- **Readable selected rows** — row content flips to white only on the active
  accent selection (`isSelected && controlActiveState != .inactive`), staying
  legible on the blue highlight; semantic colors elsewhere adapt to dark/light.
- **Dark / light / system appearance** — applied app-wide via
  `NSApp.appearance` (set at launch and on change) so every window **and** sheet
  updates uniformly (deep `preferredColorScheme` + a sheet updated only part of
  the window).
- **No launch-time Keychain prompt / hang** — `KeychainStore.has` is an
  existence-only query (no `kSecReturnData`, `kSecUseAuthenticationUIFail`), so
  the launch-time key-status refresh never reads the secret, never prompts, and
  never blocks the main actor. (Previously `has` round-tripped through `get`,
  whose `kSecReturnData` triggered a synchronous Keychain dialog on a rebuilt
  binary, stalling the launch task before the watchlist could load.) The actual
  value is read — with a possible one-time prompt — only when a run starts. The
  launch task also loads the watchlist *before* the key refresh, so live data is
  never gated on Keychain.

---

## 10. Dev code-signing (`scripts/dev-signing-setup.sh`)
- **What.** Creates a stable self-signed **"TradingDesk Dev"** code-signing
  identity in a dedicated keychain; `make-preview-app.sh` signs the preview app
  with it.
- **Why.** Ad-hoc signing changes the binary's cdhash every rebuild, so the
  app's Keychain item ACLs never match → macOS re-prompts for keychain access on
  every build. A stable identity keeps the code identity (and ACLs) constant →
  no repeated prompts. **Verified:** key reads back across a rebuild with no
  prompt. (The real Xcode target uses a Developer ID instead.)
- **How.** A self-signed code-signing cert (system LibreSSL `.p12` — homebrew
  OpenSSL 3's MAC is unreadable by `security import`) is imported into a
  dedicated keychain whose **known** password backs `set-key-partition-list`, so
  codesign runs non-interactively without the login-keychain password.

---

## 11. Event protocol reference

Envelope: `{ "v":1, "run_id", "seq", "ts", "type", … }`. SSE frames are
`id: <seq>\ndata: <json>\n\n`.

| `type` | key fields | drives |
|---|---|---|
| `handshake` | `schema_version, pid` | first line / version check |
| `warming` | `phase` | cold-start indicator |
| `started` | `ticker, asset_type, trade_date, analysts, profile_name, max_debate_rounds, max_risk_discuss_rounds, benchmark` | pipeline rail + counters |
| `node_status` | `node, group, state` | rail spinners/checks |
| `report_section` | `section, title, markdown, finalized, sentiment_score?` | report sections |
| `agent_step` | `node, role, text, text_kind, is_final` | Theater action cards |
| `tool_call` | `node, call_id, name, args` | provenance |
| `tool_result` | `call_id, name, ok, preview, full, data_status` | provenance (amber on `no_data`) |
| `debate_turn` | `debate, round, index, speaker, text, is_judge` | live debate |
| `stats` | `llm_calls, tool_calls, tokens_in, tokens_out, elapsed_s` | stats/cost bar |
| `done` / `error` / `cancelled` | `rating, run_dir` / `scope, message` / `at_node` | terminal handling |

---

## 12. Build & run (dev)

```bash
# 1. One-time: stable signing identity (stops keychain re-prompts)
bash macos/TradingDesk/scripts/dev-signing-setup.sh

# 2. Backend image + container
docker compose build desk-server
docker compose up -d desk-server          # http://127.0.0.1:8765

# 3. Build, sign, and launch the preview app
bash macos/TradingDesk/scripts/make-preview-app.sh
open macos/TradingDesk/.build/TradingDesk.app
# (or just `swift build` / `swift run` from macos/TradingDesk/)
```

Python adapter/server unit tests (run on any interpreter):
`PYTHONPATH=. python3 tests/test_desk_adapter_diff.py` (and `_protocol`, `test_desk_server_events`).

---

## 13. Known constraints / dev caveats
- **Docker Desktop is required** on the user's Mac; the app detects it and
  guides if missing.
- **Cancel is prompt but not instantaneous** — a `CancelCallbackHandler` raises
  at the next LLM/tool/chain boundary, so the in-flight call already on the wire
  finishes (it can't be interrupted mid-request) but no new call starts; the run
  then resolves to a `cancelled` terminal node. This is seconds, not the minutes
  a whole multi-call node would take.
- **Outcome resolution is lazy + same-ticker** — a pending decision resolves on
  the next run of that ticker (or via the resolve-only pass).
- **A/B compare across configs is deferred** — `store_decision` refuses a second
  pending entry per `[date|ticker]` and `_log_state` overwrites per ticker+date;
  a parallel app-owned store is needed first.
- **Dev build only:** the preview app is the SwiftPM target (not a distributable
  bundle); the OpenRouter model dropdown lists all ~340 models (a searchable
  picker is a future refinement).
- **Display names are a small client-side map.** Adds now carry a real symbol
  (the command palette sources live `/search` Yahoo results), but the display
  *name* falls back to the symbol for instruments outside `Instruments.names`;
  the engine resolves the canonical identity at run time.
- **The palette searches a loaded corpus for runs/decisions.** Tickers are a live
  debounced `/search`, but runs/decisions are the full `/reports` + `/journal`
  sets loaded once when the palette opens and filtered client-side (fine at this
  scale; a server-side query would be needed at large history sizes).
- **The title-bar search isn't perfectly chrome-free on macOS 26** — see §7.4:
  Tahoe wraps toolbar controls in a Liquid-Glass capsule, and the results popover
  keeps its arrow.

---

## 14. Roadmap (not yet built)
- Server-side ticker resolution/validation (a `/resolve` endpoint) so adds are
  checked against a real listing and carry the engine's canonical name.
- A/B compare-across-configs (needs the app-owned run store).
- Simulated/true token-by-token streaming in the Theater (engine `stream_mode=messages`).
- Xcode app target → Developer ID signing, notarization, Sparkle auto-update,
  and bundling the engine image for first-launch `docker load`.

---

## 15. Design system — "calm native pro" polish (`DesignSystem.swift`, `Components.swift`)

A cohesive visual language applied across every surface, in light **and** dark.
Reference: a warm, layered, first-party-Apple feel (soft card selection, pastel
chips, sparklines, a refined timeline Live Monitor).

- **Tokens (`DesignSystem.swift`).** `Color(light:dark:)` builds dynamic colors
  via `NSColor(name:dynamicProvider:)` (no asset catalog needed for the SwiftPM
  target; re-resolves when `NSApp.appearance` changes). `Palette` is the single
  source of truth: warm `surface`/`surfaceRaised`/`surfaceSunken`/`selection`/
  `separator`, one swappable **`accent`** (swap to rebrand), harmonized status
  (`positive`/`negative`/`warning`/`running`/`neutral`) and `gain(_:)`. A named
  `Tint` scale (`chipFill`/`cardFill`/`hover`/`track`) replaces the old ~9 ad-hoc
  opacity literals; `Space` (4/8 grid) and `Radius` standardize layout; a small
  type ramp adds `monospacedDigit()` to all numerals.
- **Components (`Components.swift`).** `PrimaryButtonStyle` (soft accent-fill Run),
  `DestructiveButtonStyle` (outlined Stop), `IconButtonStyle` (gear/refresh/+),
  all with hover/press states; `SegmentedTabs` (a custom pill control with a
  `matchedGeometryEffect` slide, replacing the stock `.segmented` Picker for
  Library/Journal); `PremiumEmptyState` (tinted icon medallion + title + message
  + optional CTA, replacing the four stock `ContentUnavailableView`s); `Sparkline`.
  `Theme.swift`'s `RatingChip` is now a pastel fill + same-hue text (the old
  white-on-accent contrast bug is gone since selection is a soft card).
- **Watchlist (`Watchlist.swift`).** A `List` with custom rows that draw their
  own soft-card selection (no system highlight); each row shows the symbol, a
  stale `Nd` badge, a pastel rating chip (or a pulsing **"● running"** indicator
  while that ticker is being analyzed — driven by a `.runStateChanged`
  notification → a `runningSymbols` set in `RootSplitView`), and a **price
  sparkline** (trend-colored) fed by `/prices` (`WatchlistStore` fetches a 30-day
  close series per symbol concurrently). Swipe a row left (or right-click) to
  **delete** or **★ star**; starred symbols pin to the top (persisted in
  `WatchlistStore.pinned`). Per-ticker journal/report stores are cached in
  `DeskStores` so switching back to a ticker is instant (no empty-state flash);
  run state is cached per symbol in `RunRegistry` so a run survives ticker
  switches.
- **Ticker Desk (`Workspace.swift`, `Library.swift`).** `SegmentedTabs`, big
  date + chip journal rows with signed/`monospacedDigit` α, card-style Library
  rows, and a refined `RunDocumentView` reader (accent section titles, 680-pt
  reading width).
- **Live Monitor (`LiveMonitor.swift`).** Redesigned as the showcase: a
  **pipeline timeline** (9 grouped stages with a spine, status dots — a
  `.symbolEffect(.pulse)` accent dot for the active stage, green for completed —
  per-stage elapsed `m:ss`, and **debate round counters** `k/n`); a slim
  **cost/stats meter** (`N llm calls · Xk tokens` + `$cost` + a soft-budget bar
  when `est_cost_usd` is present, else a live elapsed timer); a **gated idle
  hero** (`PremiumEmptyState`: "Set your API key" / "Waiting for the backend" /
  "Ready to run"); and the **Agent Theater feed** as tinted `.card()` rows with
  insert transitions and an emphasized active card. A 1 Hz `TimelineView` drives
  the live timers. `RunCoordinator` gained per-node start/end times, debate
  round/max tracking, and `est_cost_usd` capture.
- **Verified** on screen in both light and dark across every pane. (The live
  timeline/feed/cost-meter render during a run; the gated hero is shown until an
  API key is set.)
