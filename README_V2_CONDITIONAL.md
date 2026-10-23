# Koral Equities — Conditional Execution Research V2.1

**Status: validated offline simulator candidate. NOT connected to the dashboard, an autonomous AI order flow, Trading 212, or any other broker. This is not an investment strategy with demonstrated profitability.**

This milestone addresses a serious finding in the first Koral Equities research cycle: the Portfolio Manager advised a **conditional** entry in NVDA (above $226.87 with follow-through), and a **conditional** META entry (above $716.08), but the initial engine had treated each simple `Overweight` label as an unconditional buy at the next open. That was an execution **mismatch**. The archived reports are research, not machine-valid trading instructions.

## Two accounts, completely isolated

- **V1 original:** `~/.tradingagents/paper/portfolio.json` — existing £10,000 GBP simulated account, research history, previous decisions and cancellation audit preserved. The *scanner now records new ratings only*, and cannot queue new orders from the five rating labels. Any previously queued orders should still be checked/cancelled manually, since the daily V1 book can process already-queued legacy orders.
- **V2 offline:** `~/.tradingagents/paper/v2/portfolio.json` — separate state for testing approved, structured conditional plans only. It does not read or write V1, and doesn't make HTTP, broker or AI calls.

## What a valid machine-executable plan requires

Every `TradeIntent` must explicitly declare and validate all of these: contract schema, unique ID, ticker, as-of decision date, expiry, Buy/Overweight rating, long-entry side, `CLOSES_ABOVE` trigger, 1–3 required consecutive **completed** closing prices, positive dollar trigger, an **explicit executable** stop-loss (not an ambiguous 'watch level'), fraction of a standard portfolio allocation (max 30% of equity), maximum holding sessions (1–126), maximum allowable opening gap (max 5%, default suggestion 3%), verified sector, and SHA-256 of the source report.

An operator must explicitly approve a plan; model-generated strings never automatically authorize orders. An existing V1 report **cannot** be converted by merely reading its Overweight rating. If the report doesn't specify an actual executable stop or unambiguous entry confirmation, the new plan should remain **REVIEW REQUIRED**, not be fabricated.

### Deterministic execution sequence

1. **Observe only completed daily prices.** A trigger never executes at its first intraday touch. A two-close plan needs two successive completed sessions above the trigger.
2. **Queue only after confirmation.** An accepted signal on day T must wait until a *later* trading session open before any fill is permitted.
3. **Pre-open veto:** reject orders that have expired, lack a valid pre-open earnings snapshot, would cross the earnings blackout, open back below the trigger, or open more than the plan's configured max gap above the confirmation close.
4. **Mandatory data:** no price bar for an active plan/position or a missing required market/FX quote means reject the session, preserving the existing ledger.
5. **Portfolio controls:** no leverage; max five holdings; 2% intended stop-risk budget per position; 6% total planned stop risk; max 30% in any name; 40% **same-sector cap when verified sector metadata is included**; max gross exposure 100%; a sticky 10% drawdown pause for new buys. Overnight gaps can exceed stop-risk budgets. The initial allocation cap may only **tighten** these rules.
6. **Time exits:** each V2 plan specifies a maximum number of holding sessions, rather than the unrelated V1 default of 20. The actual execution engine still processes stops and next-day exits, not the AI.
7. **Auditing:** every approved intent, veto, queued conditional order, fill, expiry or cancellation creates an event. Events remain separate from AI narrative and cannot be mistaken for original market quotes.

### Earnings calendars: timestamped and conservative

V2 requires **separately time-stamped** issuer event-calendar snapshots for the session **pre-open** and **after close**. Each must state both the most recent and next earnings date, verified source and timestamp. Missing, unverifiable, or stale data fail closed. A planned entry is blocked within seven calendar days before earnings and for two calendar days after the latest release. The latest snapshot must have been available within the prior four hours of the relevant New York market cutoff. This guards against accidentally applying post-close news to an earlier fill. These are prototype research rules, not proven return enhancers.

An input timestamp by itself is **not proof of historical point-in-time correctness**. We need real vendor-provided publication timestamps and corporate-action handling before historical or actual forward deployment.

## Commands (from the repository root, after `pip install -e .`)

```powershell
# Create an entirely new, isolated OFFLINE experimental account. Only once.
.\.venv\Scripts\koral-equities-v2-replay.exe init --start 2026-10-22

.\.venv\Scripts\koral-equities-v2-replay.exe status

# Approved review flow, once the plan JSON and exact original source text exist:
.\.venv\Scripts\koral-equities-v2-replay.exe approve-plan --plan path\to\intent.json --report path\to\exact_source_report.txt --approve

# Offline test replay, with bars / FX / benchmark / independent event snapshots:
.\.venv\Scripts\koral-equities-v2-replay.exe replay-day --fixture path\to\session.json
```

The CLI explicitly refuses to write to the V1 state file, refuses to overwrite an existing V2 file, verifies the exact report hash before allowing approval, and writes V2 state atomically. **It has no market feed, model integration or real execution capability.** Feed adapters and structured-output integration are separate deliverables. Do not use this CLI to infer actual P&L without authenticated historical or live data.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest -q tests/test_conditional_v2.py tests/test_v1_research_gate.py tests/test_paper_engine.py
```

The local developer test passed **34 tests** against these three test modules before this code was committed. Live Windows/Python installation and remote service integrations remain unverified until run on that machine.

## Still to build before autonomous forward trading

The AI must emit a proper typed trade contract in a single as-of research run; independently validate entry conditions against the original report and issuer filings; provide a credible data vendor for earnings calendars, prices and corporate actions; handle sector/correlation risk; execute all daily sessions and missed sessions in a hosted scheduler; retain immutable model versions and research source snapshots; produce comparable true total-return benchmarks and cost accounting. Failure at any stage must not trigger an imagined order.

The first V2 release is **safety infrastructure**, not evidence of stock-selection alpha or a production-ready portfolio.
