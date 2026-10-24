# Koral Equities - Full traceable trade rehearsal

STATUS: CONTROLLED SYNTHETIC REHEARSAL, NOT REAL MARKET OR FORWARD PERFORMANCE.

## Reproduce on Windows

After installing this source update, open a PowerShell terminal in the
existing Koral Equities folder and enter:

    .\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli rehearse --output ".\Koral_Trade_Rehearsal_001"

The output path must be NEW. Reusing an existing folder, or writing anywhere
under the user's real paper accounts, is refused. No real paper portfolio,
AI provider, brokerage, or live market data is accessed by the rehearsal.

## What it proves

The actual production policy and conditional portfolio engine execute a
five-session, fully SYNTHETIC market example for fictional ticker KXDEMO.

- Wed 21 October 2026: an explicitly MOCKED AI portfolio manager and
  trader agree on TWO completed closes above $102, and a firm $92 stop.
  Strict numeric/source matching validates the machine-readable instruction.
- Thu 22 October: first synthetic confirming close; no order.
- Fri 23 October: second synthetic confirming close; queue a conditional buy
  AFTER the close.
- Mon 26 October: fabricated but correctly time-labelled pre-open earnings
  confirmation; simulated opening fill with slippage, GBP FX and sizing limits.
- Tue 27 October: adverse synthetic gap at $88 below the $92 stop. The
  simulator exits at the worse available open, recording about GBP -82.28
  in realised P&L and leaving about GBP 9,917.72 in an ISOLATED mock account.

Files generated in the output folder:
- SUMMARY.md: a human-readable narrative.
- AUDIT_MANIFEST.json: file-level SHA-256 source fingerprints, order IDs,
  mock research, entry and exit details and synthetic-data warnings.
- portfolio.json: the real V3 hash-chain audit and paper engine state.
- reports/.../source.json: source report that matches the hashed typed plan.
- calendar/... and market_evidence/...: dates, source metadata and OHLC
  evidence used by the deterministic trade lifecycle.

This does NOT establish that a real LLM recommended a stock, that real market
data passed verification, or that a profitable edge exists. Never add the
synthetic loss or return to genuine forward-trading statistics.

## Defect fixed by this release

The production Autopilot previously called the AI audit logger with
both an explicit ticker parameter and an expanded receipt that itself
contained ticker. That could abort a valid research cycle with a duplicated
argument error. The receipt is now nested inside one audit event. Unit
regression requires the complete synthetic decision to be retained.

## Actual first forward-paper trade still requires

1. Independent source-gated upcoming/previous earnings dates observed at
   their correct real-world cutoff windows. The last observed AAPL/MSFT
   calendars were matched by two secondary sources, but NVDA was unverified.
2. Real NYSE complete prices, correct USD/GBP and corporate action handling,
   with no after-close or retroactive information entering an earlier fill.
3. Real AI Portfolio Manager and typed proposal with unambiguous, report-backed
   executable trigger, stop, expiry and size, accepted by the V3 risk engine.
4. Confirmation on later completed sessions, and only then a valid subsequent
   market-opening simulated fill (or NO TRADE if any evidence is missing).
5. An independent audit versus a simple rule-based control and a benchmark.

The existing V3.1 paper account remains DISABLED by default. This rehearsal
never enables it. The system does not connect to a brokerage or put real
funds at risk.
