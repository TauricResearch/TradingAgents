## ARCH-HARDEN-001: S01 — Flense and Harden + @lib/ Path Aliases

Two logical commits — S01 closure + the prerequisite alias pass:

### Commit 1: Flense and Harden ([4fd4225](https://github.com/pjsvis/TradingAgents/commit/4fd42251bf9225cb50016db4de092381b276c65f))

**Phase 1 — Flense:**

- Delete `registry-types.ts` (confirmed zero imports)
- Merge `benchmark.ts` + `benchmark-data.ts` — absorb batchFetchPrices, getLivePortfolioValue, portfolio types; retain `computeReturns` (correctly uses `_currentPortfolioValue` vs the duplicate `computePeriodReturns` which ignored it); add alias for backwards compat
- Merge `feedback.ts` + `feedback-data.ts` — absorb computeCorrelations, fetchPriceForTicker, DB types; section headers to document the two distinct concerns (post-mortem files vs live SQLite signals)
- Merge `governance.ts` + `governance-data.ts` — absorb checkGovernance; trivial
- Update all 3 routes + 3 views to import from merged files

**Phase 2 — Harden:**

- Move `settings.ts` + `settings.json` + `types.ts` to `src/lib/` (canonical shared layer)
- Fix `__dirname` -> `import.meta.dir` (fileURLToPath) in canonical settings.ts
- Fix hardcoded `localhost:3000` -> `cfg.app.dashboardPort` in status.ts
- Fix 15 CLI command import paths to `src/lib/`
- Update server lib files to use `../../lib/types` (6 files: benchmark, feedback, intel-prices, alerts-engine, alerts-db, telegram)
- Add `src/lib/**/*.ts` to tsconfig.server.json include

**Phase 3 — Gates:**

- Create `scripts/check-import-boundaries.ts` (CLI-server boundary gate)
- Wire check-import-boundaries into `just check`
- Wire `reg-enrich.ts --apply` into `just check`
- Add `--fix` to `reg-sync.ts` in `just check`
- Remove `|| true` escape hatch from `td-orphans.ts`

### Commit 2: Path Aliases ([ede5330](https://github.com/pjsvis/TradingAgents/commit/ede5330b3a067ac468e44b2ae6f0b541a5414bd9))

Replace all cross-tier relative imports to `src/lib/` with `@lib/` aliases:

| Layer | Files |
| --- | --- |
| tsconfig.json + tsconfig.server.json | Added `"@lib/*": ["src/lib/*"]` |
| src/lib/settings.d.ts | Module declarations: `src/lib/*` -> `@lib/*` |
| src/server/lib/ | 11 files — `../../lib/types` -> `@lib/types`, `../../lib/db` -> `@lib/db` |
| src/server/routes/ | 9 files — `@lib/db`, `@lib/settings` |
| src/server/views/ | 1 file — `@lib/types` |
| src/cli/commands/ | 16 files — all cross-tier imports to `src/lib/` |

### Exit Criteria

- `just check` passes: YES
- `bun scripts/check-import-boundaries.ts` -> "Import boundaries: no violations": YES
- 15 CLI commands import from `@lib/` not `src/server/lib/`: YES
- No relative cross-tier imports to `src/lib/` remain: YES

### What's Next

S02 (Python Bridge hardening) can start once this is approved. S02, S04, S05, S06 all depend on S01 being in main.

## Summary by CodeRabbit

- **New Features**
	- Add portfolio data import/export commands; improved analysis run with heartbeat, layered timeouts and retry for Python bridge; live portfolio valuation, feedback correlations, and governance-check endpoints.
- **Refactor**
	- Centralized shared configuration/types/db surface and consolidated data logic; many CLI/route modules now use unified imports.
- **Chores**
	- Added import-boundary checks, TS path aliases, and updated settings/type metadata; clarified alert and CLI help/descriptions.

---

## Comments

> **qodo-code-review** · 2026-05-14
> 
> ### Qodo reviews are paused for this user.
> 
> Troubleshooting steps vary by plan [Learn more →](https://docs.qodo.ai/review-eligibility)
> 
> **On a Teams plan?**  
> Reviews resume once this user has a paid seat *and* their Git account is linked in Qodo.  
> [Link Git account →](https://app.qodo.ai/)
> 
> **Using GitHub Enterprise Server, GitLab Self-Managed, or Bitbucket Data Center?**  
> These require an Enterprise plan - Contact us  
> [Contact us →](https://app.qodo.ai/)

> **coderabbitai** · 2026-05-14
> 
> Warning
> 
> ## Rate limit exceeded
> 
> `@pjsvis` has exceeded the limit for the number of commits that can be reviewed per hour. Please wait **46 minutes and 35 seconds** before requesting another review.
> 
> You’ve run out of usage credits. Purchase more in the [billing tab](https://app.coderabbit.ai/settings/subscription?tab=usage&tenantId=62afbac9-050a-45c6-9d0b-3b42ecfa4f91).
> 
> ⌛ How to resolve this issue?
> 
> After the wait time has elapsed, a review can be triggered using the `@coderabbitai review` command as a PR comment. Alternatively, push new commits to this PR.
> 
> We recommend that you space out your commits to avoid hitting the rate limit.
> 
> 🚦 How do rate limits work?
> 
> CodeRabbit enforces hourly rate limits for each developer per organization.
> 
> Our paid plans have higher rate limits than the trial, open-source and free plans. In all cases, we re-allow further reviews after a brief timeout.
> 
> Please see our [FAQ](https://docs.coderabbit.ai/faq) for further information.
> 
> ℹ️ Review info ⚙️ Run configuration
> 
> **Configuration used**: defaults
> 
> **Review profile**: CHILL
> 
> **Plan**: Pro
> 
> **Run ID**: `82abc27d-8a5d-42c3-83ae-3ca2614c8a03`
> 
> 📥 Commits
> 
> Reviewing files that changed from the base of the PR and between [7fa3d04](https://github.com/pjsvis/TradingAgents/commit/7fa3d042a415d9d62b89a56cb70a166d713929d2) and [ec70301](https://github.com/pjsvis/TradingAgents/commit/ec7030199cd90a74da9d6f5467cf9cba61f93dad).
> 
> 📒 Files selected for processing (5)
> - `briefs/brief-add-bridge-tests-2026-05-14.md`
> - `hledger.just`
> - `justfile`
> - `tests/bridge.test.ts`
> - `tests/test_analyze_stream.py`
> 
> 📝 Walkthrough
> 
> ## Walkthrough
> 
> Consolidates shared config/types under `src/lib` with TS path aliases, inlines multiple `-data.ts` layers into primary modules (benchmark, feedback, governance), updates many imports to `@lib/*`, adds import-boundary checks, new registry CLI, Python subprocess helpers, and refreshes code-index metadata and CI recipes.
> 
> ## Changes
> 
> **Shared Library Infrastructure & Path Alias Setup**
> 
> | Layer / File(s) | Summary |
> | --- | --- |
> | **Centralized settings module**   `src/lib/settings.json`, `src/lib/settings.ts`, `src/lib/settings.d.ts` | Adds JSON defaults, env-overrides, TA\_ROOT-aware path helpers, and exports frozen `cfg` with a typed ambient declaration. |
> | **Shared type definitions**   `src/lib/types.ts` | Introduces `PriceResult`, alert types (`AlertConditionType`, `AlertCondition`, `AlertRule`, `TriggeredAlert`) and re-exports benchmark types for cross-module usage. |
> | **TypeScript path alias configuration**   `tsconfig.json`, `tsconfig.server.json`, `src/lib/package.json` | Adds `baseUrl` and `paths` alias mapping `@lib/*` → `src/lib/*`; adds `src/lib/package.json` types entry. |
> 
> **Data Access Layer Consolidation**
> 
> | Layer / File(s) | Summary |
> | --- | --- |
> | **Benchmark pricing and portfolio valuation**   `src/server/lib/benchmark.ts`, (deleted) `src/server/lib/benchmark-data.ts` | Deletes `benchmark-data.ts` and moves/implements `batchFetchPrices`, `getLivePortfolioValue`, and portfolio types into `benchmark.ts`; adds Python-backed batched price fetch with caching and GBP conversion/FX handling. |
> | **Signal feedback and correlation computation**   `src/server/lib/feedback.ts`, (deleted) `src/server/lib/feedback-data.ts` | Deletes `feedback-data.ts`; inlines live-correlation types and logic into `feedback.ts`, adds `fetchPriceForTicker` (Python-backed, cached) and `computeCorrelations()` that queries DB, fetches prices (including FX), computes per-position PnL/pct and signal outcomes. |
> | **Governance rules and portfolio checks**   `src/server/lib/governance.ts`, (deleted) `src/server/lib/governance-data.ts` | Removes `governance-data.ts` and adds `checkGovernance(platform?)` to `governance.ts`, using `getHoldings()` to compute allocations, run rules, and suggest rebalances. |
> | **Registry type definitions removed**   (deleted) `src/server/lib/registry-types.ts` | Removes JSONL registry record shape interfaces (briefs/debriefs/decisions/playbooks). |
> 
> **Import Wiring Migration Across CLI & Server**
> 
> | Layer / File(s) | Summary |
> | --- | --- |
> | **CLI command imports unified**   `src/cli/commands/*.ts`, `src/cli/main.ts` | Rewires many CLI commands to use `@lib/db`, `@lib/settings`, and `@lib/types` aliases instead of deep relative imports; adds `data` subcommand and new `data-export`/`data-import` commands; several commands emit deprecation notices or add process timeouts. |
> | **Server route imports unified**   `src/server/routes/*` | Routes updated to import `DatabaseFactory`/`cfg` via `@lib/*` aliases; benchmark/feedback/governance routes now reference consolidated modules rather than removed `-data.ts` files. |
> | **Server library & view imports updated**   `src/server/lib/*`, `src/server/views/*`, `src/server/index.tsx` | Library modules and views switch to `@lib/*` aliases; type-only imports updated to new shared types; `intel-prices`/other modules now use the new subprocess helper. |
> 
> **Python subprocess & price helpers**
> 
> | Layer / File(s) | Summary |
> | --- | --- |
> | **Subprocess runner & venv resolver**   `src/server/lib/subprocess.ts` | Adds `venvPython()` to locate project venv python, `runPython()` to spawn with timeout and capture output, and `runPythonJson()` wrapper returning parsed JSON or `null`. |
> | **Price fetchers use subprocess helper**   `src/server/lib/benchmark.ts`, `src/server/lib/feedback.ts`, `src/server/lib/intel-prices.ts` | Price-fetch logic updated to use `venvPython()`/`runPython*` patterns and batch/spawn Python `scripts/py/get_price.py` with caching and timeouts.\*/ |
> 
> **Development Tooling & Metadata**
> 
> | Layer / File(s) | Summary |
> | --- | --- |
> | **Import boundary enforcement & registry CLI**   `scripts/check-import-boundaries.ts`, `scripts/reg.ts`, `justfile` | Adds import-boundary checker enforcing silo rules and a unified `scripts/reg.ts` dispatcher; `justfile` `check` recipe now runs import-boundary, registry enrichment (`reg.ts enrich --apply`) and `reg.ts sync --fix`, and makes `td-orphans` a hard-fail. |
> | **Code registry metadata refresh**   `code/INDEX.jsonl` | Updates per-file summaries and server view HTMX targets; adds `server/lib/subprocess.ts` entry; removes `server/lib/registry-types.ts` entry; expands CLI command descriptions and marks import-related deprecations. |
> 
> ## Sequence Diagram(s)
> 
> sequenceDiagram
>     participant CLI as CLI Command
>     participant DB as SQLite Database
>     participant Batch as Batch Price Fetcher
>     participant Python as Python Script
>     participant Cache as Price Cache
>     participant Portfolio as Portfolio Calculator
> 
>     CLI->>DB: Query open positions
>     activate DB
>     DB-->>CLI: positions\[\]
>     deactivate DB
> 
>     CLI->>Batch: batchFetchPrices(tickers)
>     activate Batch
>     
>     Batch->>Cache: Check cached prices
>     activate Cache
>     Cache-->>Batch: cached prices
>     deactivate Cache
>     
>     Batch->>Python: Spawn process with tickers
>     activate Python
>     Python-->>Batch: {ticker: {price, currency}}
>     deactivate Python
>     
>     Batch->>Cache: Update cache until EOD
>     activate Cache
>     Cache-->>Batch: OK
>     deactivate Cache
>     
>     Batch-->>CLI: Map<ticker, PriceResult>
>     deactivate Batch
> 
>     CLI->>Portfolio: Convert to GBP with FX rates
>     activate Portfolio
>     Portfolio->>DB: Fetch FX rates (GBP/EUR, GBP/USD)
>     activate DB
>     DB-->>Portfolio: fxRates
>     deactivate DB
>     
>     Portfolio-->>CLI: {total, positions\[\], fxRates}
>     deactivate Portfolio
> 
> Loading
> 
> sequenceDiagram
>     participant Route as Feedback Route
>     participant DB as SQLite Database
>     participant Correlator as Correlation Engine
>     participant Fetcher as Price Fetcher
>     participant Python as Python Script
>     participant Result as Result Aggregator
> 
>     Route->>Correlator: computeCorrelations()
>     activate Correlator
>     
>     Correlator->>DB: Query open positions
>     activate DB
>     DB-->>Correlator: positions\[\]
>     deactivate DB
>     
>     Correlator->>DB: Query signals (recent)
>     activate DB
>     DB-->>Correlator: signals\[\]
>     deactivate DB
>     
>     Correlator->>Fetcher: Fetch prices for tickers + FX
>     activate Fetcher
>     
>     Fetcher->>Python: Spawn price script
>     activate Python
>     Python-->>Fetcher: price, currency
>     deactivate Python
>     
>     Fetcher-->>Correlator: Map<ticker, PriceResult>
>     deactivate Fetcher
>     
>     Correlator->>Result: Compute PnL, pct, signalOutcome
>     activate Result
>     Result-->>Correlator: CorrelationResult{correlations\[\], accuracy}
>     deactivate Result
>     
>     Correlator-->>Route: {correlations, accuracy}
>     deactivate Correlator
> 
> Loading
> 
> ## Estimated code review effort
> 
> 🎯 4 (Complex) | ⏱️ ~60 minutes
> 
> ## Possibly related PRs
> 
> - [pjsvis/TradingAgents#13](https://github.com/pjsvis/TradingAgents/pull/13): Related to registry/enrichment tooling and `just check` recipe changes referenced by this PR.
> - [pjsvis/TradingAgents#6](https://github.com/pjsvis/TradingAgents/pull/6): Touches the same server view HTMX endpoint wiring that this PR updates in metadata and view references.
> - [pjsvis/TradingAgents#8](https://github.com/pjsvis/TradingAgents/pull/8): Related to prior `cfg`/settings centralization and consumers updated here.
> 
> ## Poem
> 
> > 🐰 I hopped through imports, neat and bright,  
> > Moved configs home where paths feel right.  
> > Python spawned, hearts kept a-beat,  
> > Boundaries checked on every street.  
> > A carrot of types, tidy and light.
> 
> ✨ Finishing Touches 🧪 Generate unit tests (beta)
> - [ ] Create PR with unit tests
> - [ ] Commit unit tests in branch `feat/arch-hardening-s01-flense-harden`

> **coderabbitai** ·
> 
> **Actionable comments posted: 4**
> 
> 🧹 Nitpick comments (4)
> 
> > src/lib/settings.ts (1)
> > 
> > > `119-119`: *⚡ Quick win*
> > > 
> > > **Use the JSON default instead of hardcoding the port.**
> > > 
> > > The fallback value `3000` is hardcoded here but defined as `"3000"` in `settings.json` (line 16). If the default port needs to change, both files must be updated. Other settings on adjacent lines correctly reference `DEFAULTS` (e.g., line 118 uses `DEFAULTS.defaults.benchmarkTicker`).
> > > 
> > > ♻️ Proposed fix
> > > ```diff
> > > -    dashboardPort: optionalNum(process.env.TA_DASHBOARD_PORT ?? process.env.PORT, 3000),
> > > +    dashboardPort: optionalNum(
> > > +      process.env.TA_DASHBOARD_PORT ?? process.env.PORT,
> > > +      parseInt(DEFAULTS.defaults.dashboardPort, 10),
> > > +    ),
> > > ```
> > > 🤖 Prompt for AI Agents
> > > 
> > > ```
> > > Verify each finding against current code. Fix only still-valid issues, skip the
> > > rest with a brief reason, keep changes minimal, and validate.
> > > 
> > > In \`@src/lib/settings.ts\` at line 119, Replace the hardcoded fallback 3000 for
> > > dashboardPort with the JSON default from DEFAULTS; update the call to
> > > optionalNum in the dashboardPort initialization so it uses
> > > Number(DEFAULTS.defaults.port) (or equivalent numeric coercion) as the default
> > > value instead of 3000, ensuring the DEFAULTS.defaults.* value is used
> > > consistently with other settings like benchmarkTicker.
> > > ```
> > src/server/lib/feedback.ts (2)
> > 
> > > `232-262`: *⚖️ Poor tradeoff*
> > > 
> > > **Consider consolidating price-fetching logic.**
> > > 
> > > `fetchPriceForTicker()` spawns `scripts/py/get_price.py` and caches results. Similar logic exists in `src/server/lib/portfolio-data.ts` (`batchFetchPrices`, lines 49–96) and potentially in `src/server/lib/intel-prices.ts`. Consider extracting a shared price-fetching utility to avoid duplication and ensure cache consistency across modules.
> > > 
> > > 🤖 Prompt for AI Agents
> > > 
> > > ```
> > > Verify each finding against current code. Fix only still-valid issues, skip the
> > > rest with a brief reason, keep changes minimal, and validate.
> > > 
> > > In \`@src/server/lib/feedback.ts\` around lines 232 - 262, Current price-fetching
> > > and caching logic is duplicated across fetchPriceForTicker (in feedback.ts),
> > > batchFetchPrices (in portfolio-data.ts) and intel-prices.ts; extract a single
> > > shared module (e.g., price-fetcher) that centralizes priceCache, the Python
> > > spawn + timeout/error/JSON parsing logic, endOfToday expiry logic, and exports
> > > functions like fetchPriceForTicker and batchFetchPrices; then replace the
> > > implementations in feedback.ts, portfolio-data.ts, and intel-prices.ts to import
> > > and use those shared exports (keep the same function names: fetchPriceForTicker,
> > > batchFetchPrices, and the centralized priceCache) so all callers share one cache
> > > and identical error/timeout behavior.
> > > ```
> > > 
> > > ---
> > > 
> > > `298-306`: *💤 Low value*
> > > 
> > > **Inconsistent variable naming for FX rates.**
> > > 
> > > The FX rate variables mix casing conventions:
> > > 
> > > - Line 302: `gbpeur` (lowercase)
> > > - Line 303: `gbpUSD` (mixed case)
> > > - Line 304: `gbpPerEur`
> > > - Line 305: `gbpPerUsd`
> > > 
> > > Standardize to either `gbpEur`/`gbpUsd` or `gbpEUR`/`gbpUSD` for consistency.
> > > 
> > > 🤖 Prompt for AI Agents
> > > 
> > > ```
> > > Verify each finding against current code. Fix only still-valid issues, skip the
> > > rest with a brief reason, keep changes minimal, and validate.
> > > 
> > > In \`@src/server/lib/feedback.ts\` around lines 298 - 306, The FX rate variables use
> > > inconsistent casing; rename them consistently (e.g., change gbpeur -> gbpEur and
> > > gbpUSD -> gbpUsd) and keep the derived names consistent (gbpPerEur and
> > > gbpPerUsd); update the declarations where fetchPriceForTicker is used and
> > > replace all references to gbpeur, gbpUSD, gbpPerEur, and gbpPerUsd throughout
> > > the file (or module) so the code uses gbpEur, gbpUsd, gbpPerEur, gbpPerUsd
> > > consistently.
> > > ```
> > src/server/lib/benchmark.ts (1)
> > 
> > > `183-184`: *💤 Low value*
> > > 
> > > **Optional: drop redundant FX tickers from the batch.**
> > > 
> > > Only the `=X`\-suffixed pairs are consumed at lines 189–194; `"GBPEUR"` and `"GBPUSD"` (without suffix) are fetched but never read, doubling the FX-related python spawns each call. Worth tightening if this path is on a hot route.
> > > 
> > > 🔧 Proposed fix
> > > ```diff
> > > -  const fxPairs = ["GBPEUR=X", "GBPUSD=X", "GBPEUR", "GBPUSD"]
> > > +  const fxPairs = ["GBPEUR=X", "GBPUSD=X"]
> > > ```
> > > 🤖 Prompt for AI Agents
> > > 
> > > ```
> > > Verify each finding against current code. Fix only still-valid issues, skip the
> > > rest with a brief reason, keep changes minimal, and validate.
> > > 
> > > In \`@src/server/lib/benchmark.ts\` around lines 183 - 184, The batch is including
> > > redundant FX tickers ("GBPEUR" and "GBPUSD") that are never consumed later,
> > > causing extra python spawns; update the fxPairs used to build allTickers so it
> > > only contains the "=X" suffixed symbols (e.g., change fxPairs to ["GBPEUR=X",
> > > "GBPUSD=X"]) or filter out non-"=X" entries before spreading into allTickers
> > > (look for fxPairs and allTickers in this file and adjust the population logic
> > > accordingly) so only the consumed FX tickers are fetched.
> > > ```
> 🤖 Prompt for all review comments with AI agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> Inline comments:
> In \`@src/cli/commands/status.ts\`:
> - Line 36: The status output is still hardcoded to use :3000 which can mismatch
> cfg.app.dashboardPort; update the code that formats the server URL (the string
> used/returned in the status command in src/cli/commands/status.ts, around the
> logic that constructs the dashboard URL and the fetch call using
> cfg.app.dashboardPort) to use cfg.app.dashboardPort instead of the literal 3000
> so the displayed URL and any links align with the configured dashboardPort.
> 
> In \`@src/server/index.tsx\`:
> - Around line 13-14: Update the inconsistent import in src/server/index.tsx by
> replacing the relative import of DatabaseFactory (import { DatabaseFactory }
> from "../lib/db.ts") with the project alias import (import { DatabaseFactory }
> from "@lib/db"); locate the DatabaseFactory import in that file and switch to
> the \`@lib/db\` module (omit the .ts extension if other files use the alias without
> it) so it matches other files using \`@lib/\`* aliases.
> 
> In \`@src/server/lib/benchmark.ts\`:
> - Around line 175-178: The SQLite REAL columns (positions.quantity and
> positions.avg_cost) are being returned as strings but typed as numbers in
> PortfolioPosition; update the code that reads rows from DatabaseFactory.get()
> (the variable rows and any downstream calculations that compute
> costValueGbp/currentValueGbp) to explicitly parseFloat() the REAL fields before
> any arithmetic or assignment back into the position objects (normalize at the DB
> boundary), and apply the same parseFloat() normalization to the other occurrence
> around the block that calculates values (the code referenced at ~218-226) so all
> numeric math operates on actual numbers rather than strings.
> - Around line 139-142: Replace the system "python3" spawn with the project's
> virtualenv Python by calling venvPython() (i.e., spawn(venvPython(), [script,
> ticker], { env: {...}, timeout: 12000 })) so get_price.py runs with yfinance
> installed (this mirrors fetchBenchmarkPrices); also make the child-process error
> path non-silent by logging/propagating stderr or the parsed JSON error from
> get_price.py in the existing child output/error handler so ImportError messages
> (e.g., {"error":"yfinance not installed"}) are surfaced instead of causing
> getLivePortfolioValue to silently fall back to hardcoded FX; update the spawn
> invocation and the child output/error handling in the same block where the
> current spawn call exists.
> 
> ---
> 
> Nitpick comments:
> In \`@src/lib/settings.ts\`:
> - Line 119: Replace the hardcoded fallback 3000 for dashboardPort with the JSON
> default from DEFAULTS; update the call to optionalNum in the dashboardPort
> initialization so it uses Number(DEFAULTS.defaults.port) (or equivalent numeric
> coercion) as the default value instead of 3000, ensuring the DEFAULTS.defaults.*
> value is used consistently with other settings like benchmarkTicker.
> 
> In \`@src/server/lib/benchmark.ts\`:
> - Around line 183-184: The batch is including redundant FX tickers ("GBPEUR" and
> "GBPUSD") that are never consumed later, causing extra python spawns; update the
> fxPairs used to build allTickers so it only contains the "=X" suffixed symbols
> (e.g., change fxPairs to ["GBPEUR=X", "GBPUSD=X"]) or filter out non-"=X"
> entries before spreading into allTickers (look for fxPairs and allTickers in
> this file and adjust the population logic accordingly) so only the consumed FX
> tickers are fetched.
> 
> In \`@src/server/lib/feedback.ts\`:
> - Around line 232-262: Current price-fetching and caching logic is duplicated
> across fetchPriceForTicker (in feedback.ts), batchFetchPrices (in
> portfolio-data.ts) and intel-prices.ts; extract a single shared module (e.g.,
> price-fetcher) that centralizes priceCache, the Python spawn +
> timeout/error/JSON parsing logic, endOfToday expiry logic, and exports functions
> like fetchPriceForTicker and batchFetchPrices; then replace the implementations
> in feedback.ts, portfolio-data.ts, and intel-prices.ts to import and use those
> shared exports (keep the same function names: fetchPriceForTicker,
> batchFetchPrices, and the centralized priceCache) so all callers share one cache
> and identical error/timeout behavior.
> - Around line 298-306: The FX rate variables use inconsistent casing; rename
> them consistently (e.g., change gbpeur -> gbpEur and gbpUSD -> gbpUsd) and keep
> the derived names consistent (gbpPerEur and gbpPerUsd); update the declarations
> where fetchPriceForTicker is used and replace all references to gbpeur, gbpUSD,
> gbpPerEur, and gbpPerUsd throughout the file (or module) so the code uses
> gbpEur, gbpUsd, gbpPerEur, gbpPerUsd consistently.
> ```
> 🪄 Autofix (Beta)
> 
> Fix all unresolved CodeRabbit comments on this PR:
> 
> - [ ] Push a commit to this branch (recommended)
> - [ ] Create a new PR with the fixes
> 
> ---
> 
> ℹ️ Review info ⚙️ Run configuration
> 
> **Configuration used**: defaults
> 
> **Review profile**: CHILL
> 
> **Plan**: Pro
> 
> **Run ID**: `c0021a25-f4e4-4db7-9599-4ded948548ed`
> 
> 📥 Commits
> 
> Reviewing files that changed from the base of the PR and between [66a5ea6](https://github.com/pjsvis/TradingAgents/commit/66a5ea600f55d388b9b3e9441b5785b1eb6b69ff) and [ede5330](https://github.com/pjsvis/TradingAgents/commit/ede5330b3a067ac468e44b2ae6f0b541a5414bd9).
> 
> 📒 Files selected for processing (61)
> - `code/INDEX.jsonl`
> - `justfile`
> - `scripts/check-import-boundaries.ts`
> - `src/cli/commands/alerts-check.ts`
> - `src/cli/commands/alerts-create.ts`
> - `src/cli/commands/alerts-delete.ts`
> - `src/cli/commands/alerts-list.ts`
> - `src/cli/commands/benchmark.ts`
> - `src/cli/commands/buylist.ts`
> - `src/cli/commands/execute.ts`
> - `src/cli/commands/export.ts`
> - `src/cli/commands/import.ts`
> - `src/cli/commands/plan.ts`
> - `src/cli/commands/portfolio.ts`
> - `src/cli/commands/research.ts`
> - `src/cli/commands/signals.ts`
> - `src/cli/commands/spreadbets.ts`
> - `src/cli/commands/status.ts`
> - `src/cli/commands/trades.ts`
> - `src/cli/commands/watchlist.ts`
> - `src/lib/package.json`
> - `src/lib/settings.d.ts`
> - `src/lib/settings.json`
> - `src/lib/settings.ts`
> - `src/lib/types.ts`
> - `src/server/index.tsx`
> - `src/server/lib/alerts-db.ts`
> - `src/server/lib/alerts-engine.ts`
> - `src/server/lib/benchmark-data.ts`
> - `src/server/lib/benchmark.ts`
> - `src/server/lib/feedback-data.ts`
> - `src/server/lib/feedback.ts`
> - `src/server/lib/governance-data.ts`
> - `src/server/lib/governance.ts`
> - `src/server/lib/intel-compute.ts`
> - `src/server/lib/intel-prices.ts`
> - `src/server/lib/portfolio-data.ts`
> - `src/server/lib/prospects-data.ts`
> - `src/server/lib/registry-types.ts`
> - `src/server/lib/signals-data.ts`
> - `src/server/lib/telegram.ts`
> - `src/server/lib/workflow-data.ts`
> - `src/server/routes/alerts.tsx`
> - `src/server/routes/analyses-common.ts`
> - `src/server/routes/analyses-db.tsx`
> - `src/server/routes/analyses-fs.ts`
> - `src/server/routes/analysis.ts`
> - `src/server/routes/benchmark.tsx`
> - `src/server/routes/feedback.tsx`
> - `src/server/routes/governance.tsx`
> - `src/server/routes/holdings.tsx`
> - `src/server/routes/portfolio-balance.ts`
> - `src/server/routes/portfolio.tsx`
> - `src/server/routes/trade-plan.tsx`
> - `src/server/routes/workflow.tsx`
> - `src/server/views/alerts-view.tsx`
> - `src/server/views/benchmark-view.tsx`
> - `src/server/views/feedback-view.tsx`
> - `src/server/views/governance-view.tsx`
> - `tsconfig.json`
> - `tsconfig.server.json`
> 💤 Files with no reviewable changes (4)
> - src/server/lib/registry-types.ts
> - src/server/lib/benchmark-data.ts
> - src/server/lib/governance-data.ts
> - src/server/lib/feedback-data.ts

> **coderabbitai** ·
> 
> **Actionable comments posted: 13**
> 
> ♻️ Duplicate comments (1)
> 
> > src/server/lib/benchmark.ts (1)
> > 
> > > `137-157`: *⚠️ Potential issue* | *🟠 Major* | *⚡ Quick win*
> > > 
> > > **Don't mask `get_price.py` failures as missing quotes.**
> > > 
> > > This subprocess path only buffers `stdout` and resolves `{ price: null }` on any non-JSON output, so dependency/script failures are indistinguishable from a legitimate “no quote” result. That silently pushes `getLivePortfolioValue()` onto partial pricing and default FX. As per coding guidelines, "Never hide errors from the UI; propagate actual error message and hint (e.g., 'OPENROUTER\_API\_KEY not configured')".
> > > 
> > > 🤖 Prompt for AI Agents
> > > 
> > > ```
> > > Verify each finding against current code. Fix only still-valid issues, skip the
> > > rest with a brief reason, keep changes minimal, and validate.
> > > 
> > > In \`@src/server/lib/benchmark.ts\` around lines 137 - 157, The current spawn of the
> > > Python script (venvPython() + spawn) only reads stdout and swallows any parse
> > > failures into a silent {price: null}; instead buffer stderr as well and
> > > propagate parse or runtime errors instead of hiding them: add a let stderr = ""
> > > and child.stderr.on("data", ...) to capture errors, then in child.on("close",
> > > (code) => { try JSON.parse(stdout) ... } catch (err) { reject or resolve with an
> > > error indicator containing stderr, exit code and stdout (e.g., return [ticker, {
> > > price: null, currency: "USD", error: \`get_price.py failed: ${err.message ||
> > > code} - ${stderr.trim() || stdout.trim()}\` }]) } ), and also change
> > > child.on("error", (err) => ...) to include the err.message; keep priceCache.set
> > > only when a valid price is parsed. This ensures spawn/venvPython(), child
> > > stderr, priceCache.set and callers like getLivePortfolioValue() receive
> > > meaningful error details instead of silently using defaults.
> > > ```
> 🤖 Prompt for all review comments with AI agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> Inline comments:
> In \`@scripts/py/analyze_stream.py\`:
> - Around line 283-298: Create the TradingAgentsGraph instance before calling
> propagate(), inject position context into that graph's memory_log via
> _inject_position_context, then run propagate() on the same instance so the
> injected memory entry affects final_state/decision; specifically, replace the
> separate graph_for_context fork with constructing TradingAgentsGraph(analysts,
> config=config, debug=False) once (use the same variable name used later), check
> graph.memory_log._log_path before calling
> _inject_position_context(graph.memory_log, ticker=args.ticker,
> context=args.position_context, date=args.date), and then call graph.propagate()
> to produce final_state and decision from the enriched memory.
> 
> In \`@src/cli/commands/analyze.ts\`:
> - Around line 62-63: The CLI currently appends a stale "--debrief" flag to the
> flags array (const flags: string[] = [ticker, "--timeout", String(timeout),
> "--heartbeat-interval", "15"]) while analyze_stream.py no longer accepts it;
> remove any conditional push of "--debrief" (the if (debrief)
> flags.push("--debrief") branch) so the CLI stops sending that argument, or
> alternatively re-add parsing for "--debrief" in analyze_stream.py to accept and
> handle the option—update either the flags construction in analyze.ts or the
> argparse configuration in analyze_stream.py accordingly.
> - Around line 82-105: The current code reads proc.stdout in an async loop then
> awaits proc.stderr only after stdout completes, which delays heartbeat updates;
> change the logic to consume proc.stderr concurrently with proc.stdout (e.g.,
> start a parallel async task/Promise that reads proc.stderr as a stream and
> parses heartbeat JSON lines as they arrive), keep the existing stdout loop that
> decodes chunks with decoder and pushes to chunks, and ensure the stderr reader
> does not await until after stdout finishes but runs alongside it (use
> Promise.all or spawn two async iterators) so heartbeat handling (parsing JSON,
> checking parsed.event === "heartbeat" and writing the heartbeat message) happens
> live.
> 
> In \`@src/cli/commands/data-export.ts\`:
> - Around line 134-138: Replace the production CLI console.log calls with
> process.stdout.write: in the data-export command where the success message uses
> console.log(\`✓ Exported ${positions.length} positions, ${accounts.length}
> accounts to ${args.file}\`) and the branch that prints output
> (console.log(output)), change both to process.stdout.write(...) so the CLI
> follows repo logging policy; update the prints in the data-export.ts command
> handler where positions, accounts, args.file and output are used.
> 
> In \`@src/cli/commands/data-import.ts\`:
> - Around line 114-164: Replace all console.log and console.error calls in this
> command handler with stdout/stderr writes: use process.stdout.write(...) for
> normal output (ensure you include trailing "\n" where console.log added one) and
> process.stderr.write(...) for error messages (replacing console.error). Update
> every usage around the rows print loop, header/footer messages, the dry-run
> notice (args.dryRun), and the final summary (e.g., the blocks that currently
> call console.log and console.error when printing rows, "No valid rows...", the
> dry-run warning, and the "Imported X/Y" line); keep the exact formatted strings
> and paddings and retain the try/catch logic around stmt.run and the inserted
> counter, only changing the output calls.
> - Around line 146-155: Remove any console.log calls in the production CLI
> command (the loop over rows in src/cli/commands/data-import.ts) so no debug
> prints remain in the production path; then validate numeric parsing before
> calling stmt.run by converting r.quantity and r.avg_cost to Numbers (instead of
> silent parseInt/parseFloat), checking Number.isFinite for each, and throwing a
> descriptive error if invalid, otherwise pass the validated numeric values to
> stmt.run (the same invocation that currently uses parseInt/parseFloat).
> 
> In \`@src/cli/commands/status.ts\`:
> - Line 76: The status string uses a nested template literal—rewrite the
> construction of the status line (the expression that currently references
> serverRunning and cfg.app.dashboardPort) so it does not contain a back-ticked
> template inside another; for example build the text with a single template
> literal or with string concatenation using serverRunning ? "✓ Running on :" +
> cfg.app.dashboardPort : "✗ Not running", updating the place where the status
> array/variable is assembled (the expression referencing serverRunning and
> cfg.app.dashboardPort) to remove the inner \`\` \`...\` \`\`.
> 
> In \`@src/server/lib/benchmark.ts\`:
> - Around line 130-152: The cache currently only stores price so cache hits
> always return currency "USD"; update the cache entry stored/retrieved by
> priceCache (used in the code around priceCache.get(ticker) and
> priceCache.set(ticker, ...)) to include and preserve the original currency field
> (e.g., store { price, currency, expires }), change the cache read path that
> currently returns { price: cached.price, currency: "USD" } to return
> cached.currency instead, and when setting the cache in the child.on("close")
> handler include data.currency (falling back to "USD" only if missing). Also
> update the cache entry type definition in src/server/lib/cache.ts to include the
> currency property so types align.
> - Around line 119-121: The script path is computed from projectRoot :=
> dirname(dirname(python)) but when python comes from a virtualenv (venvPython())
> that yields the .venv folder, so script points to .venv/scripts/py/get_price.py;
> change how projectRoot is derived so it resolves the repository root (e.g.,
> compute projectRoot = dirname(dirname(dirname(python))) when python is like
> .../.venv/bin/python, or alternatively use process.cwd() to get the repo root),
> then recompute script = join(projectRoot, "scripts", "py", "get_price.py") so
> spawn(...) executes the real repository script rather than the .venv copy.
> 
> In \`@src/server/lib/intel-prices.ts\`:
> - Around line 20-25: projectRoot is computed incorrectly from venvPython():
> dirname(dirname(python)) ends up inside the .venv directory so script =
> join(projectRoot, "scripts", "py", "get_price.py") points to .venv/scripts/...
> which doesn't exist; fix by computing project root one level higher (e.g. use
> dirname(dirname(dirname(python))) or otherwise walk up an extra directory from
> the path returned by venvPython()) and then rebuild script using that corrected
> projectRoot before calling spawn; update the code that sets projectRoot (and any
> comments) to reference venvPython(), projectRoot and script so the subprocess
> points to <project-root>/scripts/py/get_price.py.
> 
> In \`@src/server/lib/subprocess.ts\`:
> - Around line 72-89: The projectRoot calculation in runPython uses
> dirname(dirname(import.meta.filename)) which yields src/server instead of the
> repository root; update the projectRoot computation to call dirname three times
> (i.e., dirname(dirname(dirname(import.meta.filename)))) so the default cwd
> points to the project root when opts.cwd is not provided; adjust the projectRoot
> variable inside the runPython function accordingly (referencing projectRoot,
> runPython, and import.meta.filename).
> 
> In \`@src/server/routes/analysis.ts\`:
> - Around line 272-280: The error SSE payloads currently send \`{ message, stderr
> }\` and must be normalized to the \`{ error, detail, hint }\` contract; add a small
> helper (e.g., formatErrorEvent or normalizeErrorPayload) that returns { error,
> detail, hint } and use it wherever you call stream.writeSSE with event: "error"
> (search for stream.writeSSE(...) error branches in this module) — replace
> existing JSON.stringify payloads with JSON.stringify(formatErrorEvent("short
> message", "more detail or stderr slice", "suggested hint")) and apply the same
> change to the other two error branches noted so all error emissions are
> consistent.
> - Around line 241-299: The jsTimeout timer is only cleared in the abort handler,
> causing a timer leak when the child process closes successfully, fails
> non-retry, or emits an error; add a single finish() helper that clears
> jsTimeout, calls persistState, and then resolves the outer promise, and replace
> all direct resolve()/persistState() calls in the child.on("close") and
> child.on("error") flows (and the retry branch that ultimately finishes) to call
> finish() instead; ensure finish() is used by runChild’s error/close handling and
> by the abort handler to avoid double-finalization.
> 
> ---
> 
> Duplicate comments:
> In \`@src/server/lib/benchmark.ts\`:
> - Around line 137-157: The current spawn of the Python script (venvPython() +
> spawn) only reads stdout and swallows any parse failures into a silent {price:
> null}; instead buffer stderr as well and propagate parse or runtime errors
> instead of hiding them: add a let stderr = "" and child.stderr.on("data", ...)
> to capture errors, then in child.on("close", (code) => { try JSON.parse(stdout)
> ... } catch (err) { reject or resolve with an error indicator containing stderr,
> exit code and stdout (e.g., return [ticker, { price: null, currency: "USD",
> error: \`get_price.py failed: ${err.message || code} - ${stderr.trim() ||
> stdout.trim()}\` }]) } ), and also change child.on("error", (err) => ...) to
> include the err.message; keep priceCache.set only when a valid price is parsed.
> This ensures spawn/venvPython(), child stderr, priceCache.set and callers like
> getLivePortfolioValue() receive meaningful error details instead of silently
> using defaults.
> ```
> 🪄 Autofix (Beta)
> 
> Fix all unresolved CodeRabbit comments on this PR:
> 
> - [ ] Push a commit to this branch (recommended)
> - [ ] Create a new PR with the fixes
> 
> ---
> 
> ℹ️ Review info ⚙️ Run configuration
> 
> **Configuration used**: defaults
> 
> **Review profile**: CHILL
> 
> **Plan**: Pro
> 
> **Run ID**: `f4715082-1112-4515-a95f-a931f4e8fa56`
> 
> 📥 Commits
> 
> Reviewing files that changed from the base of the PR and between [ede5330](https://github.com/pjsvis/TradingAgents/commit/ede5330b3a067ac468e44b2ae6f0b541a5414bd9) and [7fa3d04](https://github.com/pjsvis/TradingAgents/commit/7fa3d042a415d9d62b89a56cb70a166d713929d2).
> 
> 📒 Files selected for processing (23)
> - `ARCHITECTURE.md`
> - `briefs/brief-harden-python-bridge-2026-05-14.md`
> - `code/INDEX.jsonl`
> - `justfile`
> - `scripts/barnacle-scan.ts`
> - `scripts/py/analyze_stream.py`
> - `scripts/reg.ts`
> - `src/cli/commands/analyze.ts`
> - `src/cli/commands/data-export.ts`
> - `src/cli/commands/data-import.ts`
> - `src/cli/commands/data.ts`
> - `src/cli/commands/export.ts`
> - `src/cli/commands/import.ts`
> - `src/cli/commands/research.ts`
> - `src/cli/commands/status.ts`
> - `src/cli/main.ts`
> - `src/lib/settings.ts`
> - `src/server/index.tsx`
> - `src/server/lib/benchmark.ts`
> - `src/server/lib/feedback.ts`
> - `src/server/lib/intel-prices.ts`
> - `src/server/lib/subprocess.ts`
> - `src/server/routes/analysis.ts`
> 💤 Files with no reviewable changes (1)
> - scripts/barnacle-scan.ts
> ✅ Files skipped from review due to trivial changes (1)
> - briefs/brief-harden-python-bridge-2026-05-14.md
> 🚧 Files skipped from review as they are similar to previous changes (5)
> - src/server/index.tsx
> - src/cli/commands/import.ts
> - src/lib/settings.ts
> - code/INDEX.jsonl
> - src/server/lib/feedback.ts

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🟠 Major* | *🏗️ Heavy lift*
> 
> **Inject position context before `propagate()` runs.**
> 
> This write happens after `graph.propagate()` has already produced `final_state` and `decision`, so the analysis never sees the injected memory entry. Right now it only mutates the log for a later run. Please construct the graph up front, inject into that graph’s `memory_log`, and then run `propagate()` on the same instance.
> 
> As per coding guidelines, "Position context in `scripts/py/analyze_stream.py` is injected via the memory log; wrap, don't fork the tradingagents logic".
> 
> 🧰 Tools 🪛 Ruff (0.15.12)
> 
> \[error\] 297-298: `try`\-`except`\-`pass` detected, consider logging the exception
> 
> (S110)
> 
> ---
> 
> \[warning\] 297-297: Do not catch blind exception: `Exception`
> 
> (BLE001)
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@scripts/py/analyze_stream.py\` around lines 283 - 298, Create the
> TradingAgentsGraph instance before calling propagate(), inject position context
> into that graph's memory_log via _inject_position_context, then run propagate()
> on the same instance so the injected memory entry affects final_state/decision;
> specifically, replace the separate graph_for_context fork with constructing
> TradingAgentsGraph(analysts, config=config, debug=False) once (use the same
> variable name used later), check graph.memory_log._log_path before calling
> _inject_position_context(graph.memory_log, ticker=args.ticker,
> context=args.position_context, date=args.date), and then call graph.propagate()
> to produce final_state and decision from the enriched memory.
> ```

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🟠 Major* | *⚡ Quick win*
> 
> **Remove the stale `--debrief` flag or add parser support back.**
> 
> `analyze_stream.py` no longer accepts `--debrief`, so `trading analyze <ticker> --debrief` will exit with an argparse error before any analysis runs. Either stop passing the flag here or restore the option on the Python side.
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/cli/commands/analyze.ts\` around lines 62 - 63, The CLI currently appends
> a stale "--debrief" flag to the flags array (const flags: string[] = [ticker,
> "--timeout", String(timeout), "--heartbeat-interval", "15"]) while
> analyze_stream.py no longer accepts it; remove any conditional push of
> "--debrief" (the if (debrief) flags.push("--debrief") branch) so the CLI stops
> sending that argument, or alternatively re-add parsing for "--debrief" in
> analyze_stream.py to accept and handle the option—update either the flags
> construction in analyze.ts or the argparse configuration in analyze_stream.py
> accordingly.
> ```

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🟠 Major* | *⚡ Quick win*
> 
> **Consume `stderr` concurrently if you want live heartbeats.**
> 
> The heartbeat parsing runs only after the `stdout` loop completes, so progress updates are buffered until the child exits. Read `proc.stderr` in parallel with `proc.stdout` (for example via `Promise.all`) so long analyses keep updating the terminal while they run.
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/cli/commands/analyze.ts\` around lines 82 - 105, The current code reads
> proc.stdout in an async loop then awaits proc.stderr only after stdout
> completes, which delays heartbeat updates; change the logic to consume
> proc.stderr concurrently with proc.stdout (e.g., start a parallel async
> task/Promise that reads proc.stderr as a stream and parses heartbeat JSON lines
> as they arrive), keep the existing stdout loop that decodes chunks with decoder
> and pushes to chunks, and ensure the stderr reader does not await until after
> stdout finishes but runs alongside it (use Promise.all or spawn two async
> iterators) so heartbeat handling (parsing JSON, checking parsed.event ===
> "heartbeat" and writing the heartbeat message) happens live.
> ```

> **coderabbitai** · 2026-05-14
> 
> *🛠️ Refactor suggestion* | *🟠 Major* | *⚡ Quick win*
> 
> **Replace `console.log` with stdout writes in production CLI path.**
> 
> Please switch these success/output prints to `process.stdout.write(...)` to satisfy repo logging policy.
> 
> 💡 Suggested patch
> ```diff
> -      console.log(
> -        \`✓ Exported ${positions.length} positions, ${accounts.length} accounts to ${args.file}\`,
> -      )
> +      process.stdout.write(
> +        \`✓ Exported ${positions.length} positions, ${accounts.length} accounts to ${args.file}\n\`,
> +      )
>      } else {
> -      console.log(output)
> +      process.stdout.write(output)
>      }
> ```
> 
> As per coding guidelines, `src/**/*.{ts,tsx,js}`: Remove all `console.log` from production paths before merging; debug logging is acceptable.
> 
> 📝 Committable suggestion
> 
> > ‼️ **IMPORTANT**  
> > Carefully review the code before committing. Ensure that it accurately replaces the highlighted code, contains no missing lines, and has no issues with indentation. Thoroughly test & benchmark the code to ensure it meets the requirements.
> 
> Suggested change
> 
> |  | console.log( |
> | --- | --- |
> |  | \`✓ Exported ${positions.length} positions, ${accounts.length} accounts to ${args.file}\`, |
> |  | ) |
> |  | } else { |
> |  | console.log(output) |
> |  | process.stdout.write( |
> |  | \`✓ Exported ${positions.length} positions, ${accounts.length} accounts to ${args.file}\\n\`, |
> |  | ) |
> |  | } else { |
> |  | process.stdout.write(output) |
> |  | } |
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/cli/commands/data-export.ts\` around lines 134 - 138, Replace the
> production CLI console.log calls with process.stdout.write: in the data-export
> command where the success message uses console.log(\`✓ Exported
> ${positions.length} positions, ${accounts.length} accounts to ${args.file}\`) and
> the branch that prints output (console.log(output)), change both to
> process.stdout.write(...) so the CLI follows repo logging policy; update the
> prints in the data-export.ts command handler where positions, accounts,
> args.file and output are used.
> ```

> **coderabbitai** · 2026-05-14
> 
> *🛠️ Refactor suggestion* | *🟠 Major* | *⚡ Quick win*
> 
> **Remove `console.log` usage in this production command path.**
> 
> Please replace these `console.log` calls with stdout writes (or approved debug-only logging) to align with repo policy.
> 
> As per coding guidelines, `src/**/*.{ts,tsx,js}`: Remove all `console.log` from production paths before merging; debug logging is acceptable.
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/cli/commands/data-import.ts\` around lines 114 - 164, Replace all
> console.log and console.error calls in this command handler with stdout/stderr
> writes: use process.stdout.write(...) for normal output (ensure you include
> trailing "\n" where console.log added one) and process.stderr.write(...) for
> error messages (replacing console.error). Update every usage around the rows
> print loop, header/footer messages, the dry-run notice (args.dryRun), and the
> final summary (e.g., the blocks that currently call console.log and
> console.error when printing rows, "No valid rows...", the dry-run warning, and
> the "Imported X/Y" line); keep the exact formatted strings and paddings and
> retain the try/catch logic around stmt.run and the inserted counter, only
> changing the output calls.
> ```

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🟠 Major* | *⚡ Quick win*
> 
> **Cache the quote currency with the cached price.**
> 
> Line 133 reconstructs every cache hit as `currency: "USD"`. After the first fetch, any EUR or other non-USD instrument is converted with the wrong FX rate on subsequent requests, so `currentPriceGbp` and the portfolio total can be materially wrong until cache expiry.
> 
> 🔧 Preserve the original currency in cache
> ```diff
> -            if (cached && cached.expires > now && cached.price !== null) {
> -              resolve([ticker, { price: cached.price, currency: "USD" }])
> +            if (cached && cached.expires > now && cached.price !== null) {
> +              resolve([ticker, { price: cached.price, currency: cached.currency ?? "USD" }])
>                return
>              }
> @@
> -                if (data.price != null) {
> -                  priceCache.set(ticker, { price: data.price, expires: endOfToday() })
> +                if (data.price != null) {
> +                  priceCache.set(ticker, {
> +                    price: data.price,
> +                    currency: data.currency ?? "USD",
> +                    expires: endOfToday(),
> +                  })
>                  }
> ```
> 
> You'll also need to extend the cache entry type in `src/server/lib/cache.ts`.
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/server/lib/benchmark.ts\` around lines 130 - 152, The cache currently only
> stores price so cache hits always return currency "USD"; update the cache entry
> stored/retrieved by priceCache (used in the code around priceCache.get(ticker)
> and priceCache.set(ticker, ...)) to include and preserve the original currency
> field (e.g., store { price, currency, expires }), change the cache read path
> that currently returns { price: cached.price, currency: "USD" } to return
> cached.currency instead, and when setting the cache in the child.on("close")
> handler include data.currency (falling back to "USD" only if missing). Also
> update the cache entry type definition in src/server/lib/cache.ts to include the
> currency property so types align.
> ```

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🔴 Critical* | *⚡ Quick win*
> 
> **Critical: projectRoot resolves to .venv directory, not project root.**
> 
> Line 23 computes `projectRoot` as `dirname(dirname(python))`. Since `venvPython()` returns `/path/to/project/.venv/bin/python3`:
> 
> - `dirname(python)` = `/path/to/project/.venv/bin`
> - `dirname(dirname(python))` = `/path/to/project/.venv` ← **wrong!**
> 
> Line 24 then constructs `script` as `join(projectRoot, "scripts", "py", "get_price.py")`, which produces:  
> `/path/to/project/.venv/scripts/py/get_price.py`
> 
> This path does not exist—scripts live at `<project-root>/scripts/`, not inside `.venv/`. The subprocess will fail to find the script at runtime.
> 
> 🐛 Proposed fix: walk up three levels from venv Python
> ```diff
> const python = venvPython()
> -    // scripts/py/get_price.py is at <project-root>/scripts/py/get_price.py
> -    // venvPython() walks up to project root, so dirname(dirname(python)) = project-root
> -    const projectRoot = dirname(dirname(python))
> +    // venvPython() returns <project>/.venv/bin/python3
> +    // dirname 3x: .venv/bin/python3 → .venv/bin → .venv → project-root
> +    const projectRoot = dirname(dirname(dirname(python)))
>      const script = join(projectRoot, "scripts", "py", "get_price.py")
> ```
> 📝 Committable suggestion
> 
> > ‼️ **IMPORTANT**  
> > Carefully review the code before committing. Ensure that it accurately replaces the highlighted code, contains no missing lines, and has no issues with indentation. Thoroughly test & benchmark the code to ensure it meets the requirements.
> 
> Suggested change
> 
> |  | const python \= venvPython() |
> | --- | --- |
> |  | // scripts/py/get\_price.py is at <project\-root>/scripts/py/get\_price.py |
> |  | // venvPython() walks up to project root, so dirname(dirname(python)) = project-root |
> |  | const projectRoot \= dirname(dirname(python)) |
> |  | const script \= join(projectRoot, "scripts", "py", "get\_price.py") |
> |  | const child \= spawn(python, \[script, ticker\], { |
> |  | const python \= venvPython() |
> |  | // venvPython() returns <project\>/.venv/bin/python3 |
> |  | // dirname 3x: .venv/bin/python3 → .venv/bin → .venv → project-root |
> |  | const projectRoot \= dirname(dirname(dirname(python))) |
> |  | const script \= join(projectRoot, "scripts", "py", "get\_price.py") |
> |  | const child \= spawn(python, \[script, ticker\], { |
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/server/lib/intel-prices.ts\` around lines 20 - 25, projectRoot is computed
> incorrectly from venvPython(): dirname(dirname(python)) ends up inside the .venv
> directory so script = join(projectRoot, "scripts", "py", "get_price.py") points
> to .venv/scripts/... which doesn't exist; fix by computing project root one
> level higher (e.g. use dirname(dirname(dirname(python))) or otherwise walk up an
> extra directory from the path returned by venvPython()) and then rebuild script
> using that corrected projectRoot before calling spawn; update the code that sets
> projectRoot (and any comments) to reference venvPython(), projectRoot and script
> so the subprocess points to <project-root>/scripts/py/get_price.py.
> ```

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🔴 Critical* | *⚡ Quick win*
> 
> 🧩 Analysis chain
> 
> 🏁 Script executed:
> 
> ```shell
> #!/bin/bash
> # Description: Verify project structure and calculate correct dirname depth
> 
> echo "=== Verify .venv location ==="
> fd -t d -d 1 '^\.venv$'
> 
> echo ""
> echo "=== Verify scripts location ==="
> fd -t d -d 1 '^scripts$'
> 
> echo ""
> echo "=== Check subprocess.ts location ==="
> fd -t f 'subprocess.ts$'
> 
> echo ""
> echo "=== Recommended fix ==="
> echo "From subprocess.ts at src/server/lib/subprocess.ts:"
> echo "  - Need 3 dirname calls to reach project root"
> echo "From venvPython() return .venv/bin/python3:"
> echo "  - Need 3 dirname calls to reach project root"
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 644
> 
> ---
> 
> 🏁 Script executed:
> 
> ```shell
> cat -n src/server/lib/subprocess.ts | head -95 | tail -30
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 1155
> 
> ---
> 
> 🏁 Script executed:
> 
> ```shell
> rg 'venvPython' -B 3 -A 3
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 9553
> 
> ---
> 
> 🏁 Script executed:
> 
> ```shell
> rg "runPython\(" -A 2 --type ts
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 1196
> 
> ---
> 
> 🏁 Script executed:
> 
> ```shell
> fd -t d -H '\.venv$' -d 1
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 46
> 
> ---
> 
> 🏁 Script executed:
> 
> ```shell
> sed -n '/^export function venvPython/,/^}/p' src/server/lib/subprocess.ts
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 679
> 
> ---
> 
> 🏁 Script executed:
> 
> ```shell
> rg 'findProjectRoot' -B 2 -A 5
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 29500
> 
> ---
> 
> 🏁 Script executed:
> 
> ```shell
> fd -t d -H '\.venv$'
> ```
> 
> Repository: pjsvis/TradingAgents
> 
> Length of output: 46
> 
> ---
> 
> **Fix: projectRoot calculation needs three `dirname` calls, not two.**
> 
> Line 79 computes `projectRoot` as `dirname(dirname(import.meta.filename))`, which resolves to `src/server` instead of the project root. This breaks relative script paths passed to `runPython()`.
> 
> Given `import.meta.filename` = `/path/to/project/src/server/lib/subprocess.ts`:
> 
> - `dirname(filename)` = `/path/to/project/src/server/lib`
> - `dirname(dirname(filename))` = `/path/to/project/src/server` ← **wrong**
> - `dirname(dirname(dirname(filename)))` = `/path/to/project` ← **correct**
> 
> Current code survives only because callers use `findProjectRoot()` + `join()` to construct absolute paths before invoking `runPython()`. However, the docstring shows intended usage with relative paths (`"scripts/py/get_price.py"`), which would fail with the current `cwd` default.
> 
> Proposed fix
> ```diff
> -  const projectRoot = dirname(dirname(import.meta.filename))
> +  const projectRoot = dirname(dirname(dirname(import.meta.filename)))
> ```
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/server/lib/subprocess.ts\` around lines 72 - 89, The projectRoot
> calculation in runPython uses dirname(dirname(import.meta.filename)) which
> yields src/server instead of the repository root; update the projectRoot
> computation to call dirname three times (i.e.,
> dirname(dirname(dirname(import.meta.filename)))) so the default cwd points to
> the project root when opts.cwd is not provided; adjust the projectRoot variable
> inside the runPython function accordingly (referencing projectRoot, runPython,
> and import.meta.filename).
> ```

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🟠 Major* | *⚡ Quick win*
> 
> **Clear `jsTimeout` on every completion path.**
> 
> `jsTimeout` is only cancelled in the abort handler. Success, non-retry failure, and child-process error paths all resolve without clearing it, so each completed request leaves a 250s timer alive and that callback can still fire against an already-finished stream. A single `finish()` helper that clears the timeout before `resolve()` would avoid the leak and double-finalization.
> 
> Suggested shape
> ```diff
> -    await new Promise<void>((resolve) => {
> +    await new Promise<void>((resolve) => {
>        let child: ReturnType<typeof spawn> | null = null
>        let timedOut = false
> +      let finished = false
> +
> +      const finish = () => {
> +        if (finished) return
> +        finished = true
> +        clearTimeout(jsTimeout)
> +        resolve()
> +      }
> 
>        function runChild(retry: boolean) {
>          if (abortController.signal.aborted || timedOut) {
> -          resolve()
> +          finish()
>            return
>          }
> ...
>          child.on("close", (code) => {
>            if (abortController.signal.aborted || timedOut) {
> -            resolve()
> +            finish()
>              return
>            }
> ...
>            if (code === 0 || code === null) {
>              persistState()
> -            resolve()
> +            finish()
>              return
>            }
> ...
>              .catch(() => {})
> -            resolve()
> +            finish()
>              return
>            }
> ...
>          child.on("error", (err) => {
>            persistState()
>            stream
>              .writeSSE({ event: "error", data: JSON.stringify({ message: err.message }) })
>              .catch(() => {})
> -          resolve()
> +          finish()
>          })
>        }
> ...
> -        resolve()
> +        finish()
>        }, 250_000)
> ...
>            clearTimeout(jsTimeout)
>            if (child) child.kill("SIGTERM")
> -          resolve()
> +          finish()
>          },
> ```
> 
> Also applies to: 303-326
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/server/routes/analysis.ts\` around lines 241 - 299, The jsTimeout timer is
> only cleared in the abort handler, causing a timer leak when the child process
> closes successfully, fails non-retry, or emits an error; add a single finish()
> helper that clears jsTimeout, calls persistState, and then resolves the outer
> promise, and replace all direct resolve()/persistState() calls in the
> child.on("close") and child.on("error") flows (and the retry branch that
> ultimately finishes) to call finish() instead; ensure finish() is used by
> runChild’s error/close handling and by the abort handler to avoid
> double-finalization.
> ```

> **coderabbitai** · 2026-05-14
> 
> *⚠️ Potential issue* | *🟠 Major* | *⚡ Quick win*
> 
> **Keep analysis error events on the `{ error, detail, hint }` contract.**
> 
> These branches emit `{ message }` / `{ message, stderr }`, which gives this endpoint a different error shape from the rest of the API and drops the hint field the UI expects for actionable failures. Please normalize every `event: "error"` payload through one helper that returns `{ error, detail, hint }`.
> 
> As per coding guidelines, "Error responses must use `{ error, detail, hint }` structure in all API endpoints".
> 
> Also applies to: 293-297, 308-310
> 
> 🤖 Prompt for AI Agents
> 
> ```
> Verify each finding against current code. Fix only still-valid issues, skip the
> rest with a brief reason, keep changes minimal, and validate.
> 
> In \`@src/server/routes/analysis.ts\` around lines 272 - 280, The error SSE payloads
> currently send \`{ message, stderr }\` and must be normalized to the \`{ error,
> detail, hint }\` contract; add a small helper (e.g., formatErrorEvent or
> normalizeErrorPayload) that returns { error, detail, hint } and use it wherever
> you call stream.writeSSE with event: "error" (search for stream.writeSSE(...)
> error branches in this module) — replace existing JSON.stringify payloads with
> JSON.stringify(formatErrorEvent("short message", "more detail or stderr slice",
> "suggested hint")) and apply the same change to the other two error branches
> noted so all error emissions are consistent.
> ```