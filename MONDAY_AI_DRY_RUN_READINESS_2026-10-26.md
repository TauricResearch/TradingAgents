# Koral Equities | Monday 26 October 2026 — AI dry-run readiness

**Status:** RESEARCH-ONLY forward-data acceptance plan. No real or paper
orders approved. This checklist uses publicly announced earnings dates only
to choose a *better set of test subjects*; the actual engine MUST also receive
completed NY daily bars and fresh two-secondary-provider earnings evidence.

## Why this matters

The initial \`AAPL MSFT NVDA\` observer watchlist is unlikely to produce a
genuine LLM research call: Apple has a 2 November earnings release (exactly
7 days away from Monday, inside our seven-day veto), Microsoft has a
28 October release (two days away), and NVDA's prior observation recorded
\`UNVERIFIED_EARNINGS_SOURCE\`. The dry run must NOT force an entry or
report a missed opportunity if these are blocked.

**Proposed alternate research-test watchlist: COST JPM WMT.** They are not
stock recommendations or automatically approved trades. Their *officially
announced* future earnings dates are outside the seven-day blackout:

- **COST:** company Investor Relations states fiscal Q1 2027 earnings on
  10 December 2026; most recent quarterly results on 24 September 2026.
  https://investor.costco.com/events-and-presentations/
- **JPM:** company Investor Relations states Q4 2026 earnings on
  14 January 2027; Q3 2026 earnings on 13 October 2026.
  https://www.jpmorganchase.com/ir/events
- **WMT:** company event calendar states FY2027 Q3 earnings on
  19 November 2026; prior Q2 results on 20 August 2026.
  https://corporate.walmart.com/news/events

**Crucial:** Official event dates alone are not permission to trade.
The automated gate still requires same-session, timestamped Yahoo AND Nasdaq
agreement and both the previous/next earnings date. If any vendor source
returns nothing, the candidate must be blocked. These are research subjects
selected for a better chance of testing the system, not investment theses.

## Timezones / operational feasibility

On 25 October British Summer Time ends; US Eastern DST does not end until
1 November. On **Monday 26 October**, all observation times below are **UK GMT**:

| Phase | New York EDT | London GMT |
| --- | --- | --- |
| Preopen earnings | 08:45–09:25 | 12:45–13:25 |
| Evening earnings ("preclose") | 17:00–17:25 | 21:00–21:25 |
| Completed daily market capture | from 17:40 | from 21:40 |

The PC must remain awake and the **observation-only service** must be running
during each collection window. Saturday/Sunday are not genuine US sessions.

## If choosing the alternate watchlist

**Before Monday's first observation window**, stop the existing observer
with Ctrl+C and start exactly one observer with the alternate tickers:

\`\`\`powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli observe --tickers COST JPM WMT --poll-seconds 60
\`\`\`

Do not run two observers against the same directory simultaneously.
Previously saved AAPL/MSFT/NVDA **23 October** observations remain immutable.
Monday is a new session and may use a different, deliberately selected set of
three subjects. The local observer does not submit paper or brokerage orders.

## Monday verification (no extra installer)

After 21:40 GMT and only once the observer has captured a dated file:

\`\`\`powershell
$root = "$env:USERPROFILE\.tradingagents\observations\koral_v3"
$day = "2026-10-26"
@(
    "$root\calendar\$day\preopen.json",
    "$root\calendar\$day\preclose.json",
    "$root\market\$day.json"
) | ForEach-Object { "$_ : $(Test-Path $_)" }
if (Test-Path "$root\errors.jsonl") {
    Get-Content "$root\errors.jsonl" -Tail 10
}
\`\`\`

If all relevant files exist, run the **read-only, zero-AI preflight first**
using the CURRENT development version, never a stale local copy:

```powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.preflight_dry_run --session 2026-10-26 --tickers COST JPM WMT
```

The preflight reads only the captured source files, verifies the exact
watchlist and cutoff, reports source hashes, eligible tickers and whether
the current NY time permits one model call. It creates NO output directory,
does not read accounts and makes no AI/vendor requests. If it reports
`READ_ONLY_PREFLIGHT_NO_ELIGIBLE_AI`, the correct decision is to record
a blocked research day; don't manufacture a trade.

Only when its `can_request_one_real_ai_now` field is true may the same-session
**read-only** AI test be tried, explicitly permitting up to ONE real LLM
call (with provider charges):

\`\`\`powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.live_dry_run --session 2026-10-26 --tickers COST JPM WMT --ai 1 --output ".\Koral_AI_Dry_Run_20261026_COST_JPM_WMT"
\`\`\`

The output directory must not exist. Keep the requested tickers **identical**
to the observer capture's universe and never rewrite old calendar or price
evidence to force an apparent eligibility pass.

Independently verify the output folder:

\`\`\`powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.verify_dry_run --folder ".\Koral_AI_Dry_Run_20261026_COST_JPM_WMT"
\`\`\`

## Acceptance / rejection

- PASS: source files for the same completed NY session, valid GBP rates and
  OHLC, exact source hashes, fresh preclose earnings metadata, correct blacklist,
  and research report integrity. A real model call is optional; blockers are
  valid and must be recorded.
- FAIL: missing/corrupt market observation, retroactive earnings timestamp,
  conflicting or missing calendar, wrong watchlist, unsupported corporate
  action, altered report hash, duplicate state, or any automatic order.
- **No trade or simulated fill can result from this diagnostic process**.
  Its \`approved=false\`, \`submitted=false\` diagnostics cannot be promoted
  into V3.1's existing account without subsequent dedicated risk gates.
- Running code tests or reading a company's calendar over the weekend does
  NOT count as a true same-session market decision.

**Separate remaining engineering work:** repository-wide strict Ruff lint
remains red; it is independent of the focused trading regression suite.
