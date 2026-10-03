# Epic: Unified Trading CLI

**Date:** 2026-05-07
**Epic ID:** UNIFIED-CLI-001
**Status:** Done
**Priority:** P1
**Language:** TypeScript (Bun runtime)
**Location:** `cli/trading/`

---

## Objective

A single, unified command-line interface (`trading`) that wraps all TradingAgents operations: trade planning, portfolio management, price syncing, analysis, and database maintenance. Replaces 15+ standalone scripts with one discoverable entry point.

**Current pain:** Scripts are scattered (`scripts/*.ts`), have inconsistent argument parsing, no shared help system, and no platform-aware calculations.

---

## Platform Taxonomy

| Platform | Type | Tax Wrapper | Spread Bet | Available Instruments | Key Constraints |
|----------|------|-------------|------------|---------------------|-----------------|
| **AJBell** | SIPP | Pension (25% tax-free at 55+) | ❌ | Stocks, ETFs, funds, trusts | Access restricted until 55. Tax relief on contributions. Stamp duty 0.5%. |
| **Aviva** | Company pension | Workplace pension | ❌ | Funds (limited menu) | Employer-matched. May not allow direct equity. Check scheme rules. |
| **IG** | Personal | ISA available (£20k/year) | ✅ | Stocks, ETFs, spread betting | No pension wrapper. CGT outside ISA. Spread betting = tax-free (currently). |
| **NS&I** | Cash savings | None | ❌ | Premium bonds only | Not an investment platform. Use as cash reserve. Prize-based, no guaranteed return. |

**Critical rule:** Spread betting (`--mode spreadbet`) is **IG-only**. Any other platform must error.

---

## Architecture

```
cli/trading/
├── main.ts                       # Entry point: parse subcommand, dispatch
├── commands/
│   ├── plan.ts                   # Trade calculator (shares + spreadbet)
│   ├── portfolio.ts              # Holdings + P&L summary
│   ├── sync.ts                   # Price catch-up + gap fill
│   ├── analyze.ts                # Run tradingagents analysis
│   ├── seed.ts                   # Database seeding
│   ├── prices.ts                 # Single ticker current price
│   └── config.ts                 # Show/set default account/platform/risk
├── lib/
│   ├── platforms.ts              # Platform config + validation
│   ├── calculations.ts           # Shares vs spreadbet formulas
│   ├── formatters.ts             # Pretty tables (cli-table, columnify)
│   └── validators.ts             # Argument validation
└── package.json                  # "bin": "./main.ts"
```

---

## Commands

### `trading plan <ticker>` — Trade Calculator

Generate a bracket order plan, platform-aware.

```bash
# Shares on AJBell SIPP
$ trading plan AAPL --platform ajbell --account 50000 --risk 0.02
┌──────────────┬────────────────────────────┐
│ Ticker       │ AAPL                       │
│ Platform     │ AJBell (SIPP)              │
│ Entry        │ $280.80                    │
│ Stop         │ $267.40 (-4.8%)            │
│ Target 1     │ $344.60 (scale 50%)        │
│ Target 2     │ $354.40 (full exit)        │
│ Position     │ 74 shares                  │
│ Notional     │ £20,779.20                 │
│ Stamp Duty   │ £103.90 (0.5%)             │
│ Commission   │ £9.95                      │
│ Total Cost   │ £20,893.05                 │
│ Risk         │ £991.38 (1.98% of account) │
│ R/R          │ 5.49                       │
│ Tax Note     │ SIPP: no CGT, tax relief   │
│ Access Note  │ Locked until 55+           │
└──────────────┴────────────────────────────┘

# Spread bet on IG
$ trading plan AAPL --platform ig --mode spreadbet --account 50000 --risk 0.02
┌──────────────┬────────────────────────────┐
│ Ticker       │ AAPL                       │
│ Platform     │ IG (Spread Bet)            │
│ Entry        │ $280.80                    │
│ Stop         │ $267.40 (13.4 points)      │
│ Target 1     │ $344.60                    │
│ Target 2     │ $354.40                    │
│ Stake        │ £74.63 / point             │
│ Margin Req   │ £1,048 (5% of notional)    │
│ Risk         │ £1,000 (2.0% of account)   │
│ R/R          │ 5.49                       │
│ Tax Note     │ Currently CGT-free         │
│ Overnight    │ ~£0.51/day (financing)     │
└──────────────┴────────────────────────────┘
```

**Platform validation:**
- `--platform ajbell --mode spreadbet` → Error: "AJBell does not offer spread betting. Available: shares, funds, trusts. Use --mode shares."
- `--platform nsandi --mode shares` → Error: "NS&I offers Premium Bonds only. Use `trading reserve` for cash allocation."
- `--platform aviva --ticker AAPL` → Warning: "Aviva company pension may not allow direct equity. Verify your scheme's fund menu."

---

### `trading portfolio` — Portfolio Summary

```bash
$ trading portfolio
┌──────────┬──────────┬─────────┬──────────┬──────────┬────────┐
│ Platform │ Ticker   │ Shares  │ Entry    │ Current  │ P&L    │
├──────────┼──────────┼─────────┼──────────┼──────────┼────────┤
│ AJBell   │ AAPL     │ 74      │ $280.80  │ $312.40  │ +11.3% │
│ IG       │ TSLA     │ £50/pt  │ $245.00  │ $267.50  │ +9.2%  │
│ Aviva    │ VWRL     │ 200     │ £85.20   │ £91.40   │ +7.3%  │
└──────────┴──────────┴─────────┴──────────┴──────────┴────────┘
Total deployed: £45,230 | Cash reserve: £4,770 (9.5%)
```

---

### `trading sync` — Price Catch-Up

```bash
$ trading sync              # Catch up all open positions
$ trading sync --all        # Full gap fill + catch-up
$ trading sync --ticker AAPL # Single ticker
```

---

### `trading analyze <ticker>` — Run Analysis

```bash
$ trading analyze IONQ --debates 2
$ trading analyze TKA.DE --date 2026-05-01
```

Spawns `tradingagents analyze` with correct env/config.

---

### `trading seed` — Database Seeding

```bash
$ trading seed              # Full seed (positions, signals, analyses, watchlist)
$ trading seed --positions  # Partial
$ trading seed --prices     # Backfill prices
$ trading seed --test       # Test DB
```

---

### `trading prices <ticker>` — Current Price

```bash
$ trading prices AAPL
AAPL: $312.40 (+1.2%, 1d)
```

---

### `trading config` — Settings

```bash
$ trading config show       # Show defaults
$ trading config set account 75000
$ trading config set platform ig
$ trading config set risk 0.015
```

Stores in `~/.tradingagents/config.json`.

---

## Spread Betting Formula

When `--mode spreadbet` is used (IG only):

| Calculation | Formula |
|-------------|---------|
| Risk Amount | `Account × Risk%` |
| Stop Distance (points) | `Entry - Stop` |
| Stake (£/point) | `Risk Amount / Stop Distance` |
| Notional Exposure | `Stake × Entry` |
| Margin Required | `Notional × Margin Factor` (IG default: 5%) |
| Overnight Financing | `Notional × Overnight Rate / 365` (~2.5% annually) |
| P&L at Target | `Stake × (Target - Entry)` |

**Example (AAPL on IG):**
- Account: £50,000, Risk: 2% = £1,000
- Entry: $280.80, Stop: $267.40 → 13.4 points
- Stake: £1,000 / 13.4 = **£74.63/point**
- Notional: £74.63 × $280.80 = **£20,956**
- Margin (5%): £20,956 × 0.05 = **£1,048**
- If target hits ($354.40): P&L = £74.63 × 73.6 = **£5,493**

Compare to shares: £20,779 notional requires full cash. Spread bet: same exposure for £1,048 margin.

---

## Stories

### UNIFIED-CLI-001-S01: CLI Framework + Command Dispatch

**What:** Scaffold `cli/trading/` with subcommand dispatch, argument parsing, help generation.

**Acceptance:**
- `trading --help` shows all commands
- `trading plan --help` shows plan-specific flags
- `trading <command> --help` works for all commands
- Exit code 0 on success, 1 on error, 2 on invalid arguments
- Tab completion script generated (`trading completion bash|zsh|fish`)

**Estimate:** 1d

---

### UNIFIED-CLI-001-S02: Platform Config + Validation

**What:** `lib/platforms.ts` with corrected platform taxonomy.

**Platforms:**
- AJBell: SIPP (shares, funds, trusts; no spreadbet)
- Aviva: Company pension (funds; check direct equity)
- IG: Personal + ISA (shares, ETFs, spread betting)
- NS&I: Cash savings (premium bonds only)

**Acceptance:**
- `--platform <name>` validated against known platforms
- `--mode spreadbet` only allowed with `--platform ig`
- Platform-specific warnings shown (e.g., "SIPP: locked until 55+")
- Tax notes appended to output (CGT, stamp duty, tax relief)

**Estimate:** 0.5d

---

### UNIFIED-CLI-001-S03: Shares Calculator

**What:** Port `server/lib/trade-calculator.ts` into CLI with pretty output.

**Features:**
- All existing calculations (ATR, Fib, sizing)
- Platform-specific costs (stamp duty, commission)
- Tax wrapper notes (ISA, SIPP, CGT)
- Pretty table output (not JSON)

**Estimate:** 0.5d

---

### UNIFIED-CLI-001-S04: Spread Betting Calculator

**What:** Extend calculator for IG spread betting.

**New calculations:**
- Stake (£/point) from risk amount and stop distance
- Margin required (5% of notional)
- Overnight financing estimate
- Point value of targets

**Acceptance:**
- `trading plan AAPL --platform ig --mode spreadbet` produces valid spread bet plan
- `trading plan AAPL --platform ajbell --mode spreadbet` errors correctly
- Output shows stake, margin, financing, tax status

**Estimate:** 1d

---

### UNIFIED-CLI-001-S05: Existing Script Wrappers

**What:** Wrap current standalone scripts as CLI subcommands.

| Script | CLI Command |
|--------|-------------|
| `scripts/trade-calculator.ts` | `trading plan` |
| `scripts/portfolio-intel.ts` | `trading portfolio` |
| `scripts/sync-prices.ts` | `trading sync` |
| `scripts/seed_database.ts` | `trading seed` |
| `scripts/get_price.ts` | `trading prices` |
| `tradingagents analyze` | `trading analyze` |

**Acceptance:**
- Each old script has a CLI equivalent
- CLI version uses same underlying code (not duplicated)
- Old scripts remain functional (backward compat)

**Estimate:** 1d

---

### UNIFIED-CLI-001-S06: Config Management

**What:** `trading config` command for persistent defaults.

**Storage:** `~/.tradingagents/config.json`

**Fields:**
- `defaultAccountBalance`
- `defaultPlatform`
- `defaultRiskPerTrade`
- `defaultMode` (shares vs spreadbet)

**Estimate:** 0.5d

---

## Exit Criteria

- S01: `trading --help` shows all commands with descriptions
- S02: All 4 platforms validated; spreadbet restricted to IG
- S03: Shares calculator matches existing `server/lib/trade-calculator.ts` output
- S04: Spread bet calculator produces stake/margin/financing for IG
- S05: All 6 old scripts have CLI equivalents
- S06: Config persists across sessions

---

## Dependencies

- `server/lib/trade-calculator.ts` — pure functions (reuse, don't duplicate)
- `server/lib/db.ts` — `DatabaseFactory` for portfolio queries
- `scripts/get_price.ts` — current price fetching
- `tradingagents` package — analysis spawning

---

## Risks

- **Scope creep:** The CLI could become a full application. Keep it thin — delegate to existing code.
- **Breaking old scripts:** Ensure standalone scripts still work. The CLI is a facade.
- **Platform rules change:** Stamp duty, ISA limits, spread betting tax status. Keep platform config external (JSON) for easy updates.

---

## Stretch

- `trading watch <ticker>` — live price ticker in terminal
- `trading alert <ticker> --above 350` — notify when target hit
- `trading report --weekly` — P&L summary email/Slack
- `trading backtest --strategy momentum --ticker AAPL` — strategy testing
