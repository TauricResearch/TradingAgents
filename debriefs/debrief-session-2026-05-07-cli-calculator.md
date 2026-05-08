# Debrief: 2026-05-07 — Unified CLI + Trade Calculator + citty Migration

**Branch:** `feat/price-freshness`  
**Scope:** Unified CLI (`trading`), platform-aware trade calculator, citty migration, test suite  
**Commits:** 5  

---

## What We Did

### 1. Gap Analysis (debriefs/cli-gap-analysis.md)

Compared `cli/trading/` implementation against `playbooks/cli-design-playbook.md`. Found 11 gaps:
- 7 structural (no citty, no meta blocks, manual arg parsing, no shared args, no lazy loading)
- 4 cosmetic (no emojis, missing context in errors, no tests, no bin entry)

**Decision:** Migrate to citty. Not because the custom parser was broken — it worked — but because citty provides auto-generated help, type-safe args, and compliance with the project's own standards.

### 2. citty Migration (0ae8892, d615e0d, 3fc2d22)

- Installed `citty@0.2.2`
- Restructured `main.ts` with `defineCommand` + `runMain` + lazy subcommand loading
- Restructured `plan.ts` with declarative `args` (type, alias, default, description)
- Extracted shared arg definitions into `cli/trading/lib/args.ts`
- Added `just trading <TICKER>` recipe
- Added `package.json` script: `"trading": "bun cli/trading/main.ts"`

**Verification:**
```bash
bun run trading plan --help       # auto-generated, shows all flags
bun run trading plan AAPL         # shares plan, IG default
bun run trading plan AAPL -p ig -m spreadbet  # spread bet plan
bun run trading plan AAPL -p ajbell -m spreadbet  # ❌ Error: AJBell does not support spreadbet
```

### 3. Platform Taxonomy Correction

User corrected our initial understanding:
- **AJBell** = SIPP (personal pension, locked until 55)
- **Aviva** = Company pension (employer-matched, limited fund menu)
- **IG** = Personal + ISA + spread betting (CGT outside ISA)
- **NS&I** = Cash savings (premium bonds only)

**Impact:** The `validateMode()` function in `cli/trading/lib/platforms.ts` now enforces:
- `spreadbet` mode only on IG
- `shares` mode errors on NS&I
- `funds` mode is the only option for Aviva

### 4. Trade Calculator Tests (0bf82be, 12418f5)

**Unit tests (19 tests):**
- ATR calculation: cross-referenced with Investopedia example
- Swing detection: clear AB move, edge cases, single bar
- Fibonacci extensions: 138.2%, 161.8%, reverse AB
- Position sizing: never exceeds risk limit (integer shares round down)
- Concentration flag: triggers at >5% of portfolio
- Edge cases: empty history, insufficient history, zero risk

**Integration tests (3 tests):**
- Real AAPL price data from `prices` table
- Manual cross-check: entry=last close, stop=entry-2*ATR, targets ordered
- Monotonic position sizing with account balance
- Risk scaling with `riskPerTrade` percentage

**Critical finding:** The first test run had **3 failures** — not because the code was wrong, but because the test expectations were wrong:

| Test | Wrong Expectation | Correct Value | Lesson |
|------|-------------------|---------------|--------|
| ATR flat series | 9.2857 | 10.00 | TR uses `\|high - prev_close\|`, not `high-low` |
| Swing detection | Global max (103) | Highest after low (101) | Swing high is AFTER swing low, not global max |
| Position sizing | Exactly £1,000 | £984 | Integer shares round down, actual risk ≤ target |

This is the single most important lesson: **tests verify your understanding as much as your code.**

### 5. Rounding Precision Issue

Integration test revealed that `plan.entry` and `plan.stopLoss` are rounded to 2 decimals in the output, but `riskAmount` is computed from raw (unrounded) values. This creates a ~£0.22 discrepancy when recomputing from rounded values.

**Verdict:** Acceptable for display purposes. The risk amount is computed correctly from raw values; rounding is applied only for presentation. Documented in test comments.

---

## Lessons Learned

### 1. Tests verify understanding, not just code

The three initial test failures were all in my head, not in the calculator. I misunderstood how TR is computed (uses prior close, not just high-low), how swing detection works (highest after lowest, not global max), and how integer rounding affects risk (always ≤ target, never above).

**Rule:** When a test fails, check your expectation before checking the code.

### 2. Integration tests catch what unit tests miss

Unit tests with synthetic data (flat bars, perfect AB moves) validate the formula. Integration tests with real AAPL data validate that the formula behaves sensibly with actual market volatility, gaps, and rounding.

**Rule:** Always add at least one integration test that uses real data.

### 3. The 3-script rule is a reliable heuristic

We had 3 scripts with duplicated OpenRouter logic → extracted `scripts/lib/llm.ts`. We had 3+ CLI commands needing shared args → extracted `cli/trading/lib/args.ts`. Both extractions paid off immediately.

**Rule:** At 2 scripts, extraction is debatable. At 3, it's mandatory.

### 4. Platform taxonomy is load-bearing

Getting AJBell wrong as "ISA" instead of "SIPP" would have produced tax advice that could cost the user thousands. The platform config is not metadata — it's the foundation of the calculator's correctness.

**Rule:** Verify platform types with the user before writing a single line of calculator code.

### 5. citty migration is low-friction once you commit

The migration took ~2 hours total: install, restructure, extract args, add just recipe. The benefits (auto-help, type-safe args, lazy loading) are immediate and compound.

**Rule:** Don't build custom arg parsing. Use the framework the playbook specifies.

### 6. .gitignore `lib/` is a recurring landmine

Python's standard `.gitignore` includes `lib/`. We hit this twice: `scripts/lib/` and `cli/trading/lib/`. Each time the file was created, worked locally, but was invisible to git.

**Rule:** Any time you create a `*/lib/` directory, immediately add a `!` exception to `.gitignore`.

---

## Files Created This Session

- `cli/trading/main.ts` — citty entry point
- `cli/trading/commands/plan.ts` — trade plan command
- `cli/trading/commands/help.ts` — help subcommand
- `cli/trading/lib/platforms.ts` — platform config + validation
- `cli/trading/lib/args.ts` — shared citty arg definitions
- `tests/trade-calculator.test.ts` — 19 unit tests
- `tests/trade-calculator-integration.test.ts` — 3 integration tests
- `debriefs/cli-gap-analysis.md` — gap analysis vs. playbook

---

## Verification

| Check | Status |
|-------|--------|
| `just check` | ✅ biome + tsc + db-gate pass |
| `bun test tests/trade-calculator.test.ts` | ✅ 19 pass, 0 fail |
| `bun test tests/trade-calculator-integration.test.ts` | ✅ 3 pass, 0 fail |
| `bun run trading plan --help` | ✅ Auto-generated help |
| `bun run trading plan AAPL` | ✅ Shares plan |
| `bun run trading plan AAPL -p ig -m spreadbet` | ✅ Spread bet plan |
| `bun run trading plan AAPL -p ajbell -m spreadbet` | ✅ Error with context |
| `just trading TKA.DE` | ✅ Quick recipe works |

---

## What's Next

1. **IG API Integration** — set up demo account, validate calculator against actual IG order parameters
2. **S05/S06** — wrap remaining scripts (portfolio, sync, analyze) and add config management
3. **Settings Integration** (`td-36bf91`) — wire calculator defaults to `server/lib/settings.ts`
4. **Playbook** — document the calculator testing pattern for future agents
