# Koral Equities | Anytime Discovery

## Use the premium dashboard

1. Install the updated branch and run `pip install -e .` inside your existing Python environment.
2. Open `koral-equities` and click **Discovery** in the top navigation.
3. Choose the number of listed symbols to screen and how many AI due-diligence reports to commission (start with 350 and 0–2 reports).
4. Press **Discover stocks**. The dashboard keeps the progress log available until dismissed and shows a ranked shortlist with scenario analysis once data arrives.
5. Open each AI report and five-year memo to review evidence, valuation assumptions and disconfirming risks.

## Independent command line

```powershell
.\\.venv\\Scripts\\koral-equities-discover.exe --max-symbols 350 --ai 2
```

Start with `--ai 0` if you want to screen cheaply before spending model usage:

```powershell
.\\.venv\\Scripts\\koral-equities-discover.exe --max-symbols 350 --ai 0
```

The default source is the current Nasdaq Trader Nasdaq- and other-listed symbol directories. If both sources are offline, the scan fails rather than inventing tickers. Yahoo Finance supplies price histories and current public profile fields; missing/inconsistent data are excluded. A fixed-seed sample is **not** the entire market and the procedure is neither a point-in-time historical backtest nor survivorship-bias-free. Profiles and news can have different timestamps from the final complete daily candle.

**Research heuristics, not edge claims:** current filters favour $200m–$30bn capitalisation, at least $20m reported revenue, 12% vendor-reported revenue growth, liquid share turnover, momentum and positive business quality proxies. Scores are screening priorities, not calibrated likelihoods of 10× returns. Bear/base/bull five-year revenue-growth, sales-multiple and dilution assumptions illustrate mathematical possibilities; they require independent scrutiny and can produce losses or implausible outcomes.

**Safety boundaries:** no access to `portfolio.json`, the V2 offline ledger, Trading 212, or any brokerage API. The AI can only generate research; it cannot queue an order. Earnings/SEC filings, dilution, financial series and sector classifications need independent source verification before capital decisions. Discovery runs are user initiated, not continuously scheduled.

## Critical timestamp correction — 22 October 2026

An initial ERO research report generated at **15:43 UK / 10:43 New York** mistakenly called an **intraday** October 22 price the October 22 daily **close**. The discovery price shortlist already excluded unfinished bars; the AI research call independently supplied the *calendar date of the research run* instead of the candidate's completed price date. This caused the market analyst to describe partial-session candles as completed daily data.

**Fix:** the AI analyst now receives `price_asof` from the candidate's most recent completed screening candle, after validation against the scan's exclusive market-data cutoff. The run log and AI report index explicitly record that completed `price_analysis_date` separately from `research_at_utc`. During a US trading day, this may deliberately result in a report dated the **prior market session** even though the research runs right now. This is expected and avoids mislabelling partial bars.

**Remaining limitation:** the externally supplied company profiles and any live news may be updated at times that differ from the screened market close. This is an on-demand research product, NOT a backtest or a fully point-in-time-audited investment dataset. Re-running research is required to obtain a corrected report. Historical AI reports and the existing V1/V2 paper ledgers are not modified.

## V2 valuation policy — evidence first, no imaginary 10x targets

Universal 22%/40% CAGR and 3×/6× terminal-sales valuation scenarios have been **removed from new scans**. V2 classifies companies into industry-specific underwriting methods: mine NAV, reserve NAV, cycle-normalised refining cash flow, software cohort cash flow, bank capital/ROTE, insurance reserve adequacy, healthcare product-risk cash flow, consumer unit economics or industrial through-cycle returns. It calculates the *math* of tenfold shareholder appreciation (58.49% annualised for five years) but **no forecast return multiple, price target or success probability**. An unverified company remains **INSUFFICIENT_EVIDENCE** with an explicit diligence checklist.

The discovery pipeline now selects a combination of momentum leaders and a seeded sample of other liquid companies for fundamental research, reducing the old momentum-only bias. Shortlists are sector-diversified when enough candidates qualify. These selection choices are untested research heuristics, not proven alpha.

### Optional direct SEC source metadata and tagged XBRL facts

The SEC collector uses official `company_tickers.json`, `submissions` and `companyfacts` endpoints. To responsibly identify a research tool in SEC requests, set `KORAL_SEC_USER_AGENT=KoralEquities Research contact@example.com` **with your actual email replacing the example** in your private `.env` and restart the dashboard. This is an optional operator choice; no configuration means the scan still runs and explicitly records `SEC NOT_CONFIGURED`. Keep all contact details and provider keys out of GitHub.

Filing links and tagged XBRL facts include accession, form, filing date, concept, unit and reporting period where available. They do **not** prove that the Yahoo financial snapshot reconciles to a filed statement, establish a defensible industry forecast, or make a historical backtest point-in-time safe. Foreign filers can have incomplete US-GAAP tagging. Nothing in this module writes to either V1 or V2 portfolio accounts.
