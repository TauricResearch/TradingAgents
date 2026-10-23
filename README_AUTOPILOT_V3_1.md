# Koral Equities — V3.1 Autonomous PAPER Candidate

**Status: experimental local paper-trading integration. No real broker connection. No proven investment edge. The vendor/provider end-to-end workflow is not verified on the user's PC.**

This build is a separate pilot to protect the **already initialised V3 staging portfolio**. The existing `~/.tradingagents/paper/v3/portfolio.json`, the original V1 portfolio, the V2 offline portfolio, all saved reports and `.env` are unchanged.

## Architecture and account separation

| Sleeve | State path | What it does |
| --- | --- | --- |
| Original V1 paper | `~/.tradingagents/paper/portfolio.json` | Archived research and baseline simulated account |
| V2 conditional replay | `~/.tradingagents/paper/v2/portfolio.json` | Manually approved offline conditional engine |
| V3 Paper Lab | `~/.tradingagents/paper/v3/portfolio.json` | Existing user's successfully initialised staging account |
| **V3.1 Autopilot candidate** | `~/.tradingagents/paper/v3_autopilot/portfolio.json` | **Separate** paper-only, source-gated scheduled candidate |

V3.1 does not automatically inherit or convert V3's cash, orders or positions. This is intentional and ensures we never overwrite a funded ledger or reproduce a backtested fill as a real forward trade. Initial simulated capital is £10,000.

## The local paper workflow

1. When the user's computer is awake and the `serve` command remains running, a local New York/DST-aware scheduler polls once per configured interval. **Nothing runs in the cloud when the PC is asleep.**
2. During 08:45–09:25 NY it captures immutable **pre-open** earnings observations from independent Yahoo/Nasdaq secondary calendars. Each issuer must have both a previous and an upcoming earnings date, and both providers must agree on the next event. Missing, stale or inconsistent data cause **NO NEW BUY**. This is not issuer-primary verification.
3. During 17:00–17:25 NY it captures another after-market-close (named `preclose` for historical compatibility) earnings observation. Existing snapshots cannot be rewritten.
4. From 17:40 NY it checks completed daily stock OHLC, SPY price-only benchmark and GBP conversion. It detects unmapped stock splits/dividends and refuses to model positions through unsupported corporate actions. Captured market prices are independently archived and SHA-linked to the event audit; a later modified quote invalidates the ledger.
5. The existing V2 deterministic risk engine marks holdings, standing stops and time exits. Missed sessions may be modelled as historical **standing risk**, but a late-launched service **never retroactively opens new positions**.
6. When paper automation has been explicitly enabled, the AI investment committee can research a **predeclared** US stock swing watchlist using its completed-session date. A second strictly structured model examines the original report for an exact closing-price trigger, numeric stop the portfolio manager explicitly describes as *executable*, small allocation, confirmation and holding instructions. No free-text fallback, no ambiguous stop, and no rating-only market order.
7. Only a validated conditional `TradeIntent` becomes `WATCHING`. One new research intent per session; no buy until confirmed on completed future days and vetted again at the next session's open. The AI never controls the broker: there is no broker API in these modules.
8. The programme records model decision receipts and a hash-chained audit. Losses, fills, FX, costs and exits are **simulated** with daily OHLC, not executable exchange quotes.

### Risk limits inherited from the existing engine

- Initial £10k simulated GBP; **2% intended stop risk per position**, **6% combined intended stop risk**.
- Up to five holdings; maximum 10% initial allocation per autonomously accepted plan; 30% name upper bound in the underlying engine; 40% sector ceiling when verified; maximum 100% gross long exposure.
- 10% equity-drawdown lockout for new entries, no leverage, and gap/slippage risk **can exceed** planned stop losses.
- Two or three completed close confirmations as actually documented by the portfolio manager, never inferred from the rating.
- At most three candidate research analyses daily, separately limited by CLI config. Model calls can incur costs and do not guarantee any approved plans.

## Commands — PowerShell from Koral Equities project directory

Always inspect code and tests first. **Do not run `init` if a V3.1 autopilot account already exists.**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_autopilot_state.py tests/test_autopilot_decision.py tests/test_autopilot_feeds.py tests/test_autopilot_runner.py tests/test_autopilot_performance.py
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli --help
```

Create a **new separate V3.1 pilot** on an appropriate completed US session. October 22 is a development example, **not** a current-date default:

```powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli init --start 2026-10-22 --tickers AAPL MSFT NVDA
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli status
```

Pilot auto-trading is **disabled by default**. After understanding the paper-only risks and verifying the model provider and input feeds, the user must explicitly run:

```powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli enable-paper
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli serve --poll-seconds 60
```

The `serve` terminal must remain active; press `Ctrl+C` to stop. Pause or disable immediately if outputs are unexpected:

```powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli pause
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli disable-paper
.\.venv\Scripts\python.exe -m tradingagents.paper.autopilot.cli report
```

Do not activate this pilot for real capital. It is an **unproven experimental PAPER service**.


## Independent observation-only pilot (new, safe first step)

**We should test real data before enabling automatic paper execution.** The
`observe` command is a completely separate local process. It does **not**
read or write any of the V1/V2/V3/V3.1 portfolio files, call an LLM, create
a `TradeIntent`, queue simulated orders or connect to a broker.

Use your existing `.venv` and project directory; **do not run `init` again**.

Inspect whether the present time is within a valid New York observation window:

```powershell
.\\.venv\\Scripts\\python.exe -m tradingagents.paper.autopilot.cli observe --once
```

Run source observation continuously while the PC is awake:

```powershell
.\\.venv\\Scripts\\python.exe -m tradingagents.paper.autopilot.cli observe --tickers AAPL MSFT NVDA --poll-seconds 60
```

The observation process runs independently of `enable-paper`; Autopilot V3.1
remains **disabled**, and observation does not enable it. Use **Ctrl+C** to stop.

The separate observation folder is
`%USERPROFILE%\\.tradingagents\\observations\\koral_v3`. It contains:

- `calendar/YYYY-MM-DD/preopen.json`: Yahoo + Nasdaq upcoming/previous
  earnings observations captured 08:45–09:25 New York time
- `calendar/YYYY-MM-DD/preclose.json`: evening earnings observations from
  17:00–17:25 New York time (the existing V3 historical phase name)
- `market/YYYY-MM-DD.json`: validated post-close OHLC for the exact requested
  tickers and SPY, GBP conversion and split/dividend veto, starting 17:40 NY
- `heartbeat.json`: last observer pulse; `errors.jsonl`: collection errors

Saved daily evidence is not overwritten after its first successful capture.
An existing snapshot for a *different watchlist* is rejected. Source failure,
missing prices, implausible FX, split/dividend events and incomplete candles
block capture. There is no retroactive evidence fabrication: if the PC was
off during the morning collection, that observation stays missing.

**Limitations:** This does not prove that Yahoo or Nasdaq data are
exchange-certified, nor that every US exchange holiday or half-day is
covered. The observer requires a running PC, a working network and vendor
service. Its snapshots cannot authorise trades and are not treated as
validated past execution fills.

## Required acceptance gates before calling it ready

- Live provider smoke test on Windows through all three cutoff phases **without creating spurious fills**, including US exchange holidays, DST transitions, calendar-source outages and Yahoo bad candles.
- End-to-end tests with controlled mock AI portfolio manager/trader proposals, split/dividend detections, missing FX, quote revision, storage crashes, repeat starts and PC sleep/backfills.
- A fully source-backed earnings and corporate action calendar. Yahoo + Nasdaq are secondary data services, not guaranteed primary issuer filings. The current implementation conservatively fails closed on unavailable data and may therefore place **zero** trades.
- A persistent cloud/service deployment with operator-alerting if 24/7 execution is desired. The local process only runs while the PC is awake; no claim of background work in this chat.
- Benchmark against simple momentum/quality, SPY **total return** rather than solely price-only, and at least six months and 100 completed forward trades to start evaluating confidence. Even this sample cannot guarantee future profits.
- **Do not merge Discovery's speculative 3–10 year 10× watchlist into this 2–60-session Swing Alpha execution sleeve**. Long-horizon holdings need independent mandates and exit rules.

Original TradingAgents framework authors and Apache 2.0 license continue to be acknowledged in `UPSTREAM_ATTRIBUTION.md` and `LICENSE`.
