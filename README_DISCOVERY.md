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
