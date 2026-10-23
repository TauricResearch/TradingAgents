# Koral Equities — Discovery 001 ERO research audit

**Discovery run:** 22 October 2026 14:39 UTC
**AI stock report:** 22 October 2026 15:43 London time / 10:43 New York time
**Compounder memo:** 22 October 2026 14:44 UTC
**Status:** Historical research evidence, not a trade or validated tenfold return prospect.

## Critical source-date defect (corrected in code, historical report unchanged)

At 10:43 Eastern on 22 October, the US market was open. The 19-page analyst report nonetheless described `$30.36`, the partial-session volume and technical readings as the **22 October closing price**. This is not a valid completed-session daily price.

**Root cause:** `scan_market()` correctly excluded the unfinished Oct 22 daily bar for its quant price shortlist, but its separate `TradingAgentsGraph.propagate()` call used `now ... NY date` as the analyst date. That permitted a partial current-day candle to be labelled the completed day.

**Patch:** `analyst_asof_date(candidate, end_exclusive)` validates and supplies the candidate's `price_asof` last *completed* bar to the AI graph, and separately records `price_analysis_date` versus `research_at_utc`. Before the 22 October close the research market-analysis date should therefore be **21 October**. Focused regression tests added. We make **no retroactive edits** to the saved ERO research report or its five-year commentary. This code patch does not touch the simulated ledger.

**Residual:** Current Yahoo fundamental profiles, macro/news/vendor estimates can have different publication cutoffs. This is NOT a fully point-in-time historical feed.

## Contrasting AI judgments

- **Investment committee:** Overweight, small initial tranche near its observed $30.36 price, a $27.50 *risk-review* level, and a `several quarters` horizon; its chart analysis is compromised by the unfinished candle. **Do not execute or re-interpret as a structured V2 order.**
- **Independent compounder memo:** WATCH on the five-year tenfold possibility; explicitly rejects treating the short-term rating as the five-year thesis. Its hypothetical bull `9.2×` assumes 40% annual revenue growth for five years, 6× terminal sales and 3% annual dilution—not validated forecasts.
- **Research conclusion:** The *idea* of ERO as a cash-generating producer merits independent diligence; the evidence for tenfold per-share return is insufficient.

## Primary-source verification found information unavailable to the AI agents

Ero's **5 August 2026 Q2 press release** and SEC-filed MD&A contain:
- Q2 consolidated copper production **17,315 tonnes** at consolidated C1 cash cost **$2.42/lb**.
- Two copper mines: **Caraíba 8,351 tonnes, $2.76/lb**; **Tucumã 8,964 tonnes, $2.10/lb**.
- Cash flow from operations **$137.9 million**, and cash at June 30 of **$101.7 million**.
- Issuer-defined **net debt $452.7 million**, and available liquidity **$181.7 million**.
- 2026 production guidance **67,500–77,500 tonnes** copper in concentrate; consolidated C1 cost guidance **$2.15–$2.35/lb**.
- Third-quarter operating/financial results scheduled **2 November 2026 after NY close**, with call **3 November**.

These items are public **primary** evidence missing from the model's source bundle. The financial-vendor's `total debt $573.4m` is **not directly equivalent** to the issuer's loans-and-borrowings figure of approximately `$554.4m`, which underlies the issuer's `$452.7m` net-debt calculation after subtracting `$101.7m` cash. Definitions must be reconciled instead of calling one wrong.

Official sources:
- Q2 earnings release https://www.sec.gov/Archives/edgar/data/1853860/000162828026053508/erocopper-pressreleasex202.htm
- Q2 management discussion https://www.sec.gov/Archives/edgar/data/1853860/000162828026053508/erocopper-mdax2026q2.htm
- Q3 earnings schedule https://www.ero.com/investors/events-calendar/

## Next controls

1. Separate last completed market bar from the **current research timestamp** in every AI report and data API.
2. Before a five-year company memo, retrieve SEC/issuer filings with dated primary-source citations, including production, reserve tonnage, mine life, unit costs, capex budgets, financing commitments, calendar events and dilution.
3. Use a sector-appropriate commodity **mine NAV / normalised EV-EBITDA / FCF with cycle sensitivity**; do not infer an investable 10× probability from universal terminal price-to-sales assumptions.
4. Keep **Overweight** (short/intermediate portfolio allocation) separate from **WATCH** (five-year compounder potential). Never send plain ratings to a broker or the V2 conditional order engine.
5. Track as-of source versions and separate what the model knew at 10:43 from what could be learned later.

**No live or paper orders approved.**
