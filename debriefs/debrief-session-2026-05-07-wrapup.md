# Session Debrief: TradingAgents — 2026-05-07 Wrap-up

**Session:** Zed / Pi (ses_1b7e1c)  
**Branch:** feat/price-freshness  
**Commits since 2026-05-06:** 73  
**Status:** All major epics delivered. Open items quantified.

---

## Summary

This session delivered three major systems from scratch and hardened three existing ones. The scope was broad: CLI framework, trade calculator, IG API integration, database backup, GitNexus visualisation, and CI/CD automation. All committed, all passing checks.

---

## What Was Delivered

### 1. Unified Trading CLI (`cli/trading/`)

**Status:** Core framework + plan command complete. S01–S04 in review.

| Component | File | What |
|-----------|------|------|
| CLI framework | `cli/trading/main.ts` | citty-based multi-command CLI with lazy loading |
| Plan command | `cli/trading/commands/plan.ts` | Generates trade plans for any ticker via `bun run trading plan AAPL` |
| Platform config | `cli/trading/lib/platforms.ts` | AJBell=SIPP, Aviva=pension, IG=ISA+spreadbet, NS&I=cash |
| Shared args | `cli/trading/lib/args.ts` | Reusable arg definitions (ticker, platform, mode, account, risk, entry) |
| Package scripts | `package.json` | `bun run trading <command>` canonical invocation |

**Just recipes:** `just trading <TICKER>`

---

### 2. Strategic Trade Calculator (`server/lib/trade-calculator.ts`)

**Status:** Complete with 19 unit tests + 3 integration tests. Core functionality done.

| Function | Algorithm | Verified |
|----------|-----------|----------|
| `calculateATR` | Wilder's smoothing, 14-period | Cross-checked against known values |
| `findSwingHighLow` | AB swing detection (min → max after min) | Synthetic + real data |
| `fibonacciExtension` | B + (B-A) × ratio | Pure math, trivial |
| `calculateTradePlan` | Full pipeline: entry → stop → targets → sizing | Invariants proven, edge cases covered |

**Tests:** `tests/trade-calculator.test.ts` (19) + `tests/trade-calculator-integration.test.ts` (3 with real AAPL data)

**Dashboard integration:** Route (`trade-plan.ts`) + view (`trade-plan.tsx`) + server calculator module.

**Open:** S04 settings integration (`td-36bf91`) — wire defaults to `server/lib/settings.ts`.

---

### 3. IG API Integration (Epic IG-API-001)

**Status:** S01–S05 complete. All 5 stories delivered.

| Story | Deliverable | Status |
|-------|-------------|--------|
| S01 | Demo account created (user) | ✅ Done |
| S02 | Connectivity config validated via live API | ✅ Done |
| S03 | Test trades placed and closed (FTSE profit £5.00) | ✅ Done |
| S04 | Calculator validation with actual IG parameters | ✅ Done |
| S05 | Order placement guide | ✅ Done |

**Documents:**
- `docs/ig-connectivity-config.md` — Auth, accounts, instruments, validated EPICs
- `docs/ig-trading-guide.md` — Full trade lifecycle with working curl examples
- `playbooks/ig-api-playbook.md` — Complete REST API reference

**Instrument config:** `cli/trading/lib/ig-instruments.ts` — FTSE (5% margin, 8pt min stop), AAPL (20% margin, 1pt min stop), EUR/USD, Gold.

**Tests:** `tests/ig-instruments.test.ts` (14 tests, all pass) — validates margin, stop distance, deal size enforcement.

---

### 4. Database Backup Process

**Status:** Complete.

| Component | What |
|-----------|------|
| `scripts/db-backup.ts` | Timestamped SQLite backup via VACUUM INTO |
| `just backup` / `just backup-test` | One-command backup for LIVE/TEST |
| `just backups-list` / `just backups-prune` | List and prune old backups |
| `just db-stats` / `just db-stats-test` | Row counts for all tables |
| `just db-active` | Show LIVE vs TEST mode |
| `just db-reset-test` | Destroy and recreate TEST database |

**Playbook:** `playbooks/database-lifecycle-playbook.md` — TEST first, LIVE last, never mix data.

---

### 5. GitNexus Visualisation

**Status:** Working alternative to broken `serve` command.

| Component | What |
|-----------|------|
| `scripts/gitnexus-to-dot.ts` | Export GitNexus subgraph to Graphviz DOT |
| `just gn-graph-symbol <SYM>` | Impact graph for any symbol |
| `just gn-graph-file <FILE>` | Module graph for any file |
| `just gn-diagrams` | Generate key project graphs |
| `just regen-diagrams` | Full pipeline: clean + generate + render |

**Pre-push hook:** Auto-regenerates diagrams when source files change. Installed and tested.

**Playbooks:** `playbooks/gitnexus-playbook.md` + `playbooks/gitnexus-usage-guide.md`

---

### 6. CI/CD Automation

**Status:** Complete.

| Component | What |
|-----------|------|
| `scripts/install-pre-push-hook.sh` | Installer for pre-push diagram regen |
| `just install-hooks` | One-command installation |
| `just push` | Explicit push with diagram regen |

**Playbook:** `playbooks/ci-cd-playbook.md` — full workflow documentation.

---

### 7. Documentation

New playbooks written this session:

| Playbook | Purpose |
|----------|---------|
| `playbooks/trade-calculator-testing-playbook.md` | Unit + integration test patterns for calculators |
| `playbooks/database-lifecycle-playbook.md` | TEST vs LIVE separation, backup procedures |
| `playbooks/ig-api-playbook.md` | IG REST API reference (auth, endpoints, errors) |
| `playbooks/gitnexus-playbook.md` | GitNexus evaluation — what works, what doesn't |
| `playbooks/gitnexus-usage-guide.md` | Concrete use cases with real examples |
| `playbooks/ci-cd-playbook.md` | Automated diagram synchronisation |

**Other docs:**
- `docs/ig-connectivity-config.md` — Validated IG API connectivity
- `docs/ig-trading-guide.md` — Order placement with examples
- `docs/diagrams/README.md` — How to link and regenerate diagrams

---

### 8. Test Infrastructure

| Test Suite | Tests | Coverage |
|------------|-------|----------|
| `tests/trade-calculator.test.ts` | 19 | ATR, swing, Fibonacci, sizing, edge cases |
| `tests/trade-calculator-integration.test.ts` | 3 | Real AAPL data, monotonicity, risk scaling |
| `tests/ig-instruments.test.ts` | 14 | IG instrument config, validation rules |

**Just recipes:** `just test-trade-calc`, `just test-trade-calc-integration`

---

## What's Open

### Epic: Unified Trading CLI (`td-d19b7c`)

| Story | Status | What |
|-------|--------|------|
| S05 | `in_progress` | Wrap existing scripts as subcommands (portfolio, sync, analyze, seed, prices) |
| S06 | `in_progress` | Config management (`trading config set account 75000`) |

### Epic: Trade Calculator (`td-f938f4`)

| Story | Status | What |
|-------|--------|------|
| S04 | `open` | Settings integration — wire defaults to `server/lib/settings.ts` |

### IG API Follow-ups

| Item | What |
|------|------|
| US stock spread bets | Demo account lacks AAPL spread bet EPICs — need to discover or use indices |
| Share dealing validation | AAPL rejected on demo (null bid/offer) — test with UK shares (Lloyds, BP) |
| Live account migration | When ready, swap `demo-api.ig.com` for `api.ig.com` |

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **citty over custom parsing** | Playbook mandates declarative CLI framework; auto-help, validation, lazy loading |
| **AJBell = SIPP, not ISA** | User corrected taxonomy: personal pension, locked until 55 |
| **Spread bet is IG-only** | Hard error on `--platform ajbell --mode spreadbet` prevents bad orders |
| **Margin estimates marked** | `marginIsEstimate: true` on IG platform config; warnings in output |
| **Graphviz over graphology** | DOT is standard, already installed, zero maintenance vs. porting KuzuDB to SQLite |
| **Pre-push over pre-commit** | Diagrams are slow (~10s); commit-time is too frequent, push-time is right |
| **V2 auth over V3 OAuth** | Simpler, tokens auto-extend, no refresh logic needed |
| **Close = POST (not DELETE)** | IG API requires `POST /positions/otc` with `forceOpen: false` for close |

---

## Metrics

| Metric | Value |
|--------|-------|
| Commits | 73 |
| New files | ~25 |
| Playbooks written | 6 |
| Tests written | 36 (19 + 3 + 14) |
| Just recipes added | ~15 |
| IG test trades executed | 2 (FTSE open/close, AAPL rejected) |
| Lines of documentation | ~3,500 |
| Check failures fixed | ~8 (biome, tsc, db-usage gate) |

---

## Lessons Learned

1. **The 3-script rule is reliable.** Both `llm.ts` and `args.ts` extractions paid off immediately. Third time is the threshold.
2. **Platform taxonomy is load-bearing.** The AJBell=SIPP correction saved bad tax advice. Verify with the user before coding.
3. **Tests verify understanding, not just code.** Three initial test failures were wrong expectations, not code bugs.
4. **Integration tests catch what unit tests miss.** Real AAPL data revealed a rounding precision issue.
5. **`.gitignore lib/` is a recurring landmine.** Hit twice: `scripts/lib/` and `cli/trading/lib/`. Always verify git status after creating `lib/` directories.
6. **Revert is faster than forward-fix.** When a change breaks checks and the fix isn't obvious, revert first, diagnose second.
7. **Pre-push hooks read pushed commits, not working tree.** Using `git diff --name-only HEAD` fails after commit; must read refs from stdin.
8. **CSP kills localhost connections.** gitnexus.vercel.app's `default-src 'none'` makes `serve` architecturally impossible, not merely unreliable.

---

## Next Phase: Test Trading

The user will provide starting numbers (account balance, risk parameters, ticker list). Then:

1. **Generate trade plans** via `bun run trading plan <TICKER>` for each ticker
2. **Validate against IG API** using `validateIGPlan()` warnings
3. **Place test trades** on the demo account using the validated plans
4. **Track results** in the TEST database
5. **Compare predicted vs. actual** margin, stop distances, fills

**Required from user:**
- Account balance for each IG sub-account (CFD, Spread Bet)
- Risk per trade (default 2%)
- Tickers to trade (AAPL, TSLA, FTSE, etc.)
- Preferred mode (spread bet vs. share dealing)

**Ready when you are.**
