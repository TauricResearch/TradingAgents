# Analyst upgrades: valuation, risk metrics and Gulf markets

Three additions that make the agents reason with numbers an analyst would compute, not only
summarise news and sentiment. This is a research tool; none of it is investment advice.

| Feature | What it adds | Switch |
|---|---|---|
| Valuation analyst | DCF and peer multiples, computed in code | `--analysts valuation` (opt-in); `valuation_enabled` |
| Quantitative risk metrics | A computed step before the risk debate | `risk_metrics_enabled` (on by default) |
| Gulf markets | Saudi, Dubai, Qatar, Kuwait, Bahrain tickers, benchmarks and currencies | none needed |

## Ground rules all three follow

- **The model never calculates.** Every figure comes from plain Python in `tradingagents/valuation/` and
  `tradingagents/risk_metrics/`. The model only reads the numbers.
- **Point in time.** A run dated *d* reads only what was public on *d*. US statements come from SEC EDGAR as
  filed, so a restated figure reads as first reported. Yahoo statements, profiles and peer multiples carry no
  filing date, so a past run is told they are withheld and no request is made. Prices are final closes only:
  a session still trading, and any day after *d*, is never used.
- **Missing data is reported, not filled.** A figure that cannot be computed says `UNAVAILABLE` and why. Nothing is
  estimated in its place.
- **Additive.** With a feature off, prompts, reports and the graph are exactly as before.

---

## 1. Valuation analyst

### How it runs

`valuation` is an analyst like market or news (`ANALYST_NODE_SPECS`, report key `valuation_report`). It runs in
parallel with the others and has two tools, `get_dcf_valuation` and `get_peer_multiples`. The Bull and Bear
researchers, the Research Manager and the Portfolio Manager receive its report, and it is saved as
`1_analysts/valuation.md` and in the HTML report.

```bash
tradingagents --ticker AAPL --date 2026-11-06 --analysts market,fundamentals,valuation --save
```

### Where the inputs come from

| Input | Source |
|---|---|
| Operating cash flow, capex (up to 5 fiscal years), interest, tax, debt, cash, equity, shares | SEC EDGAR facts as filed (US filers); else Yahoo, present-day runs only |
| Price | last final close on or before the run date |
| Beta | 2 years of weekly returns against the ticker's regional benchmark (`resolve_benchmark`) |
| Risk-free rate | FRED 10-year Treasury (`DGS10`, as published on the run date) if `FRED_API_KEY` is set, else `valuation_risk_free_rate` |

### DCF, step by step

A worked example for a company called Acme: price 50, 20M shares (market cap 1,000M), debt 400M, cash 150M,
interest expense 20M, tax 18M on 90M pretax income, free cash flow over four years 70, 78, 85, 100 (M),
risk-free 4.25%, beta 1.2, equity risk premium 5.5%, terminal growth 2.5%.

**1. Free cash flow.** FCF = operating cash flow − capital expenditure. The base is the latest fiscal year: 100M.
If it is not positive, the report says a growth DCF does not apply.

**2. Cost of equity (CAPM).** Ke = rf + β × ERP = 4.25% + 1.2 × 5.5% = **10.85%**.

**3. Cost of debt.** Pre-tax Kd = interest expense / total debt = 20 / 400 = 5%. Tax rate = tax / pretax income =
18 / 90 = 20% (clamped to 0–35%; the 21% default applies only if it cannot be computed). After tax:
5% × (1 − 0.20) = **4.00%**.

**4. WACC** with market equity and book debt: E = 1,000, D = 400, so weights 71.43% / 28.57%.
WACC = 0.7143 × 10.85% + 0.2857 × 4.00% = **8.89%**.

**5. Growth path.** Initial growth is the compound growth of the FCF history, clamped to −5%…+25%:
(100 / 70)^(1/3) − 1 = 12.62%. It fades linearly to terminal growth over 5 years:
g_t = g₁ + (g_T − g₁)(t − 1)/(N − 1), giving 12.62%, 10.09%, 7.56%, 5.03%, 2.50%.
If history cannot give a rate (fewer than two years, or not positive at both ends), the configured
`valuation_default_growth` is used and the report says so.

**6. Forecast and discounting.** FCF_t = FCF_{t−1} × (1 + g_t), discounted at year end: PV_t = FCF_t / (1 + WACC)^t.

| Year | Growth | FCF | PV at 8.89% |
|---|---|---|---|
| 1 | 12.62% | 112.62 | 103.43 |
| 2 | 10.09% | 123.99 | 104.57 |
| 3 | 7.56% | 133.37 | 103.29 |
| 4 | 5.03% | 140.08 | 99.63 |
| 5 | 2.50% | 143.58 | 93.78 |
| | | Sum of PV | **504.69** |

**7. Terminal value (Gordon growth).** TV = FCF₅ × (1 + g_T) / (WACC − g_T) = 143.58 × 1.025 / (0.0889 − 0.025)
= 2,302.12, and its present value is 2,302.12 / 1.0889⁵ = **1,503.59** (74.9% of enterprise value; the report adds
a warning when the terminal value is more than 75%).

**8. From enterprise value to a price.** EV = 504.69 + 1,503.59 = **2,008.28**. Equity = EV − debt + cash =
2,008.28 − 400 + 150 = **1,758.28**. Per share = 1,758.28 / 20 = **87.91**, which is **+75.8%** against the price of 50.

**9. Sensitivity.** The report recomputes the value per share with WACC ±1% and ±2% and terminal growth ±0.5%
and ±1%, holding the explicit growth path fixed. A cell where WACC does not exceed terminal growth by at least
0.5% is `n/a`.

| WACC \ g | 1.5% | 2.0% | 2.5% | 3.0% | 3.5% |
|---|---|---|---|---|---|
| 6.89% | 110.98 | 121.40 | 134.20 | 150.27 | 171.09 |
| 7.89% | 91.39 | 98.43 | 106.76 | 116.80 | 129.12 |
| **8.89%** | 77.11 | 82.12 | **87.91** | 94.69 | 102.72 |
| 9.89% | 66.24 | 69.95 | 74.17 | 79.00 | 84.59 |
| 10.89% | 57.68 | 60.53 | 63.71 | 67.29 | 71.36 |

Read the grid before the point estimate: here a one-point move in WACC moves the value by 20% or more.

**Beta**, as the report computes it: weekly returns of the stock and benchmark, beta = cov(stock, benchmark) /
var(benchmark). With six weeks of returns, stock 3, −2, 4, −1, 2, −3 (%) and benchmark 2, −1, 3, −1, 1, −2 (%):
deviations from the means (0.5% and 0.3%) multiply to a sum of 28.0 (%²) and the benchmark's squared deviations
sum to 19.34, so β = 28.0 / 19.34 = **1.45**. The real calculation needs at least 52 weeks.

### Banks and insurers

A free-cash-flow DCF does not fit a bank or insurer: its debt and cash flows are operating items. The report says
so and gives P/B, P/E and ROE instead, plus a justified P/B from the Gordon model on book value:

justified P/B = (ROE − g) / (Ke − g). With ROE 12%, Ke 10%, g 3%: (0.12 − 0.03) / (0.10 − 0.03) = **1.29×**, so with
book value per share of 20 the implied price is **25.71**.

A filer is treated as financial when its SEC facts include bank or insurance line items (deposits, premiums earned,
policy benefits); from Yahoo, when the sector is Financial Services and the industry is a bank, insurer, mortgage
finance or credit-services business.

### Peer multiples

Peers come from `valuation_peer_map` if the ticker is listed, otherwise from the largest companies in the same
Yahoo industry. For P/E, EV/EBITDA, P/S and P/B the report takes the median of the peers' **positive** multiples
and the price it implies:

| Multiple | Implied price |
|---|---|
| P/E | median × EPS |
| P/B | median × book value per share |
| P/S | median × revenue / shares |
| EV/EBITDA | (median × EBITDA − debt + cash) / shares |

Example: EPS 5, book value 20, revenue 1,000, 100 shares, EBITDA 200, debt 300, cash 100; peer medians
P/E 20, P/B 2.0, P/S 2, EV/EBITDA 10. Implied: 20 × 5 = **100**, 2 × 20 = **40**, 2 × 1,000 / 100 = **20**,
(10 × 200 − 300 + 100) / 100 = **18**. The report averages the available implied prices and shows the range.

Warnings the report raises: fewer than 3 peers; the company's market cap more than 10× (or less than a tenth of)
the peer median, compared only among peers in the same currency; a reporting currency that differs from the
quote currency (EV/EBITDA and P/S are then skipped: no FX is applied).

**Yahoo's industry peers can be poor.** For Apple they are small consumer-electronics companies. Name the
peers you trust:

```python
config["valuation_peer_map"] = {"AAPL": ["MSFT", "GOOGL", "AMZN"], "2222.SR": ["XOM", "SHEL.L", "TTE.PA"]}
```

### When it says UNAVAILABLE

No share count, debt or cash from the source; free cash flow not positive; reporting currency different from the
trading currency; prices missing or stale; a past run date for a non-US company or for peer multiples; no peers.
The reason is in the report, and the analyst is told to say so and not to estimate.

### Config keys

| Key | Default | Meaning |
|---|---|---|
| `valuation_enabled` | `True` | `False` refuses a run that selects the analyst |
| `valuation_risk_free_rate` | `0.04` | used when FRED is not read |
| `valuation_use_fred_risk_free` | `True` | read the 10-year from FRED when a key is set |
| `valuation_equity_risk_premium` | `0.055` | ERP in CAPM |
| `valuation_terminal_growth` | `0.025` | Gordon growth |
| `valuation_forecast_years` | `5` | explicit forecast length |
| `valuation_beta_years` | `2` | weekly-return history for beta |
| `valuation_tax_rate_default` | `0.21` | only if the effective rate cannot be computed |
| `valuation_growth_floor` / `valuation_growth_cap` | `-0.05` / `0.25` | clamp on initial growth |
| `valuation_default_growth` | `0.05` | when history gives no usable growth |
| `valuation_peer_map` | `{}` | `ticker -> [peers]` |
| `valuation_max_peers` | `8` | peers read for the industry fallback |
| `data_vendors["valuation_data"]` | `"sec_edgar,yfinance"` | where the raw inputs come from |

Environment overrides: `TRADINGAGENTS_VALUATION_ENABLED`, `…_RISK_FREE_RATE`, `…_EQUITY_RISK_PREMIUM`,
`…_TERMINAL_GROWTH`.

---

## 2. Quantitative risk metrics

### How it runs

A graph step named **Quant Risk** runs beside the analysts and writes `quant_risk_metrics` into state. It makes no
model call. The Trader, the three risk debators and the Portfolio Manager receive the block and are told to anchor
sizing and stops to it. It is saved as `4_risk/quant_risk.md` and appears in the HTML report. Turn it off with
`risk_metrics_enabled = False`.

The window is the year ending on the run date, from final daily bars. Stocks annualise over 252 sessions, crypto
over 365. Returns are simple daily returns r_t = close_t / close_{t−1} − 1. Losses are shown as positive fractions.

### The metrics, with one worked example

Twenty daily returns (%): 1.2, −0.8, 0.4, 1.5, −2.1, 0.7, −0.3, 0.9, −1.4, 0.2, 1.1, −0.6, 0.5, −1.9, 1.3, 0.1,
−1.0, 0.8, −0.4, 0.6. Their mean is 0.04% and their sample standard deviation σ is 1.065%.

| Metric | Formula | Example |
|---|---|---|
| Annualised volatility | σ × √252 | 1.065% × 15.875 = **16.9%** |
| Beta | cov(stock, benchmark) / var(benchmark), same-day returns | as in the valuation example |
| Max drawdown | deepest fall from a running peak | closes 100, 104, 99, 103, 95, 101, 108, 102: peak 104, trough 95, (104 − 95) / 104 = **8.65%** |
| 1-day VaR 95%, historical | −(5% quantile of returns) | worst returns −2.1, −1.9, …; the quantile sits at position 0.05 × 19 = 0.95, so −2.1 + 0.95 × 0.2 = −1.91%; VaR = **1.91%** |
| 1-day VaR 95%, parametric | 1.645 σ − mean | 1.645 × 1.065 − 0.04 = **1.71%** |
| CVaR 95%, historical | −(mean of returns at or below that quantile) | only −2.1% qualifies: **2.10%** |
| CVaR 95%, parametric | σ × φ(z) / 5% − mean, φ(1.645) = 0.1031 | 1.065 × 0.1031 / 0.05 − 0.04 = **2.16%** |
| Sharpe | √252 × mean(excess) / std(excess); excess = r − rf/252 | rf 4%: 0.0241% / 1.065% × 15.875 = **0.36** |
| Sortino | √252 × mean(excess) / downside deviation | downside deviation = √(mean(min(excess, 0)²)) = 0.791%: 0.0241 / 0.791 × 15.875 = **0.48** |
| ATR(14) | Wilder: first ATR = mean of the first 14 true ranges, then ATR_t = (ATR_{t−1} × 13 + TR_t) / 14 | see below |
| ATR stop | close ∓ k × ATR (k = 2) | long stop below the close, short stop above |
| Position size | risk per position / stop distance | see below |

**True range and ATR.** TR = max(high − low, |high − previous close|, |low − previous close|). With highs
11, 12, 13, 12, 14, lows 9, 10, 11, 10, 12 and closes 10, 11, 12, 11, 13 the true ranges are 2, 2, 2, 3. A 3-day
ATR starts at (2 + 2 + 2) / 3 = 2 and the next value is (2 × 2 + 3) / 3 = **2.33**.

**Position size.** Price 100, ATR 2, k = 2: the stop is 2 × 2 / 100 = **4%** away. Risking 1% of the book
(`risk_metrics_risk_per_position`) gives size = 1% / 4% = **25% of the book**. If a cap
(`risk_metrics_max_position_pct`, default 1.0 = no leverage) binds, the report shows the capped size and the
smaller book loss at the stop. It also shows the 1-day historical VaR of that position as a share of the book.

**Risk-free rate.** FRED `DTB3` (3-month Treasury bill) as published on the run date if `FRED_API_KEY` is set, else
`risk_metrics_risk_free_rate`. The report says which.

**Caveat on beta.** Beta here uses same-day returns. Against a benchmark on a different calendar (a Gulf stock
against a US-listed ETF) it is understated, and the report says so; the valuation analyst's weekly beta is less
affected. For a market with no regional benchmark the report says that beta is against SPY and is not a
local-market beta.

### Config keys

| Key | Default | Meaning |
|---|---|---|
| `risk_metrics_enabled` | `True` | the whole step |
| `risk_metrics_window_days` | `365` | window ending on the run date |
| `risk_metrics_var_confidence` | `0.95` | VaR and CVaR confidence |
| `risk_metrics_atr_window` | `14` | ATR length |
| `risk_metrics_atr_multiple` | `2.0` | stop distance in ATRs |
| `risk_metrics_risk_per_position` | `0.01` | share of the book lost if the stop is hit |
| `risk_metrics_max_position_pct` | `1.0` | cap on position size (share of the book) |
| `risk_metrics_risk_free_series` | `"DTB3"` | FRED series for Sharpe and Sortino |
| `risk_metrics_use_fred_risk_free` | `True` | read it from FRED when a key is set |
| `risk_metrics_risk_free_rate` | `0.04` | fallback |

Environment overrides: `TRADINGAGENTS_RISK_METRICS_ENABLED`, `…_RISK_PER_POSITION`, `…_ATR_MULTIPLE`.

---

## 3. Gulf markets

### What was checked against Yahoo (via yfinance)

| Market | Suffix | Stocks checked | Index | Result |
|---|---|---|---|---|
| Saudi Tadawul | `.SR` | 2222.SR, 1120.SR: a year of daily prices | `^TASI.SR` | stocks confirmed; index returns **one row only** |
| Dubai (DFM) | `.AE` | EMAAR.AE, DIB.AE, DEWA.AE, EMIRATESNBD.AE | `DFMGI.AE` | stocks confirmed; index returns **one row only** |
| Qatar | `.QA` | QNBK.QA, IQCD.QA | `^GNRI.QA` | stocks confirmed; index returns **one row only** |
| Kuwait | `.KW` | NBK.KW, KFH.KW, ZAIN.KW | `^BKA.KW`, `^BKP.KW`, `^BKM.KW` | stocks confirmed; indices return **one row only** |
| Bahrain | `.BH` | BBK.BH, ALBH.BH: prices only, no profile data | none found | stocks partly confirmed; **no index** |
| Abu Dhabi (ADX) | none found | ALDAR, FAB, ADNOCDIST, IHC under `.AE`, `.AD`, `.ADX`, `.AB`: no data | none found | **not confirmed** |

Yahoo serves each Gulf index symbol's latest quote but no history, whatever period is asked. Mapped as benchmarks
they would give no alpha or beta and, worse, a decision would stay pending for good because its benchmark has no
prices. So the benchmark map uses the USD-listed iShares MSCI country ETFs, which have a full daily history
(checked: about 255 daily bars over a year each):

| Suffix | Benchmark |
|---|---|
| `.SR` | `KSA` (iShares MSCI Saudi Arabia) |
| `.AE` | `UAE` (iShares MSCI UAE) |
| `.QA` | `QAT` (iShares MSCI Qatar) |
| `.KW` | `KWT` (iShares MSCI Kuwait) |

These are stand-ins, not the local indices. Their returns are in US dollars, which is close to local returns for
the riyal, dirham and Qatari riyal (fixed pegs) and looser for the dinar (a managed basket peg). They trade on
different days and hours from the Gulf markets, so daily betas are understated. Bahrain and Abu Dhabi have no
entry and fall to SPY, with a warning in the risk and valuation reports. To use something else:

```python
config["benchmark_ticker"] = "KSA"                      # one benchmark for every ticker
config["benchmark_map"][".BH"] = "KSA"                  # or per suffix
```

### Symbols and currencies

- Symbol handling needs no change: `2222.SR`, `EMAAR.AE`, `QNBK.QA`, `NBK.KW`, `BBK.BH` pass through
  `normalize_symbol` unchanged, in either case.
- Yahoo gives SAR, AED and QAR as the quote and reporting currency, so those read correctly.
- **Kuwait** is quoted in fils (`KWF`, a thousandth of a dinar) while market cap, EPS and book value are in
  dinars. Fundamentals now label price levels `KWF` and the rest `KWD`, and the valuation converts a price from fils to
  dinars (÷ 1,000) before comparing it with per-share figures.
- **Bahrain** profiles carry no quote currency; `BHD` is used for the suffix. For a suffix not listed, no currency
  is guessed.
- `tradingagents/dataflows/currencies.py` holds the minor-unit table (pence, cents, agorot, fils) and the suffix
  currencies.

### Live checks

```bash
pytest tests/test_gulf_markets.py -m integration -o addopts=""
```

---

## Running it

```bash
# US stock with valuation
tradingagents --ticker AAPL --date 2026-11-06 --analysts market,fundamentals,valuation --save

# Saudi Aramco (an unattended run also needs the TRADINGAGENTS_* variables named in the README)
tradingagents --ticker 2222.SR --date 2026-11-06 --analysts market,fundamentals,valuation --save
```

Valuation inputs for a non-US company come from Yahoo and only for a run dated today, so for 2222.SR use today's date.
The risk-metrics block is included automatically; `TRADINGAGENTS_RISK_METRICS_ENABLED=false` removes it.

## Tests

```bash
pytest -m "not integration"          # unit tests, no network
pytest tests/test_gulf_markets.py -m integration -o addopts=""   # live Yahoo checks
```

New test files: `test_valuation_math.py` (hand-worked numbers), `test_valuation_lookahead.py` (point-in-time),
`test_valuation_service.py` (reports and graph wiring), `test_quant_risk.py` and `test_gulf_markets.py`.

## Limits worth knowing

- DCF output is only as good as a few inputs. Read the sensitivity table; terminal value is often 70%+ of the total.
- Debt is taken at book value and the weights use market equity. Cash excludes short-term investments when a
  filer tags them separately.
- Free cash flow ignores stock-based compensation and acquisitions; for a company where those matter the value is high.
- Yahoo's industry peers are a convenience, not a curated set (see above).
- Only US filers have point-in-time valuation inputs; Yahoo-sourced inputs are for runs dated today.
