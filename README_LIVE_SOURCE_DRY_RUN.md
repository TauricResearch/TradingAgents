# Koral Equities | Live-Source Dry Run 001

**Release classification: RESEARCH / OBSERVATION ONLY. No paper or brokerage orders.**
This is the missing bridge between the synthetic end-to-end trade rehearsal
and the first genuine, dated AI-generated investment decision.

## What it uses

- Previously saved *real* source observations made by the independent observer under
  %USERPROFILE%\.tradingagents\observations\koral_v3
- Validated, completed share OHLC for AAPL / MSFT / NVDA and SPY, plus GBP/USD
  conversion and a positive independent corporate-action-check field
- A separate, time-stamped Yahoo + Nasdaq earnings consensus snapshot, if present
- The existing TradingAgents AI investment committee and strict Koral TradeIntent
  policy, optionally, **only when the analysis is performed on the same New York
  session date after 17:40 New York time**

No AI model is called unless --ai is explicitly nonzero. Model usage may have
associated charges. When AI is used, the research report and exact source hash
are checked and archived under the newly requested output folder.

This program creates **zero simulated orders**. It does not import or call
the existing paper-account write functions, does not open any portfolio.json
and cannot activate the local Autopilot scheduler. A complete diagnostic
TradeIntent may be *examined*, but it is NEVER approved or submitted.

## First step: audit our Friday 23 October evidence on Saturday

Run from the existing Koral Equities project folder:

    .\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.live_dry_run --session 2026-10-23 --tickers AAPL MSFT NVDA --ai 0 --output ".\Koral_Live_Data_Audit_20261023"

Expected classification:

    RETROSPECTIVE_SOURCE_AUDIT_NOT_FORWARD_RESEARCH

This performs actual stored market-data validation **without an LLM call**.
It should report the **23 October 2026** MSFT earnings blackout and the
unverified NVDA event if the saved files still contain the previously observed
results. AAPL's Oct 23 secondary-source earnings snapshot was farther than
seven calendar days from the Nov 2 reported release, but that does NOT
authorise a purchase.

If a required observation is missing, stale, malformed or not yet complete,
the command refuses it instead of inventing values. The audit manifest
and copied source files are saved in a new directory. Never reuse the same
output directory or overwrite old evidence.

## Next full-session live-source AI dry run

**Monday 26 October 2026** is the next ordinary NYSE session following the
Friday observation. Due to the UK changing from BST to GMT on Sunday,
17:40 New York daylight time is **21:40 UK GMT** on Monday (one hour earlier
than Friday's UK observation time). The independent observer must capture
*Monday's actual market and earnings files* first, and the computer must
remain awake to do so.

After observing a valid completed market session, and still on 26 October in
New York local time, operators may explicitly choose up to three paid AI
analyses. For example:

    .\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.live_dry_run --session 2026-10-26 --tickers AAPL MSFT NVDA --ai 1 --output ".\Koral_AI_Dry_Run_20261026"

The program automatically skips companies with missing/unverified earnings
sources or a seven-day pre-earnings blackout. With the initial watchlist,
**zero eligible real AI calls is an entirely valid outcome**. Microsoft is
close to the 28 October earnings date, Apple to the 2 November earnings date,
and NVIDIA had an unresolved calendar in the first real observation.

Change or expand the future observer watchlist through a deliberate
operator update **before** the relevant session, never by altering an existing
captured file to fabricate historical coverage.

## Audit definitions

- SAME_SESSION_REAL_AI_DRY_RUN_NOT_FORWARD_TRADE:
  Research attempted on actual recorded same-session source inputs, no entry.
- SAME_SESSION_NO_ELIGIBLE_AI_BLOCKED_NO_TRADE:
  An AI run was requested but missing evidence/blackouts blocked every name.
- SAME_SESSION_MARKET_SOURCE_AUDIT_ONLY:
  Same-day captured input check only, with AI disabled.
- RETROSPECTIVE_SOURCE_AUDIT_NOT_FORWARD_RESEARCH:
  Read-only validation of a prior trading day's immutable observations.

Manifest: DRY_RUN_MANIFEST.json; source files copied unchanged into
original_sources/. Original SHA-256 values are recorded, as are any AI
decision/report hashes. This is a *source-integrity record*, not proof the
underlying Yahoo/Nasdaq data are exchange-certified or the model's
external financial/news sources were available at the exact market close.

**No simulated P&L, no trade approval, no broker connection, no claimed alpha.**
Do not count a valid plan in a dry run as a forward trade. The next milestone
is a genuinely future, policy-approved **paper** entry and eventual exit,
and its independent performance benchmark.

Known data limitations: secondary Yahoo/Nasdaq calendars, share splits and
dividends need full model support before live forward P&L can be trusted;
real AI provider configuration/login can fail or incur fees; sector and
fundamental data from current profiles are not fully point-in-time certified.

## Developer checks

    .\.venv\Scripts\python.exe -m pytest -q tests/test_autopilot_live_dry_run.py
    .\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.live_dry_run --help

Source code in tradingagents/paper/autopilot/live_dry_run.py. Existing V1,
V2, V3 staging and V3.1 Autopilot accounts remain separate and untouched.
