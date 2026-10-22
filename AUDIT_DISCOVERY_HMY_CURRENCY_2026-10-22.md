# HMY ADR currency mislabelling in Discovery V2 - 22 October 2026

**Result:** One real defect found. A USD-traded ADR (HMY) displayed levered free cash flow of 9.85 billion **ZAR** as 9.85 billion **USD**. This contaminated the cross-currency screening ratio and potentially the candidate ranking.

## Primary evidence
- Harmony Gold's official FY2026 results are denominated in South African rand; FY2026 revenue was R99.238bn (approximately US$5.876bn), and issuer-defined adjusted free cash flow was R17.148bn (US$1.015bn). These are different from the vendor levered FCF definition.
- Source-labelled 2026 HMY levered free cash flow was R9.850bn, in millions ZAR (not US dollars). See https://stockanalysis.com/stocks/hmy/financials/cash-flow-statement/
- Official issuer results: https://www.harmony.co.za/media/announcements/2026/fy26-results-final-dividend-declaration-20260827/

## Root cause
The scanner used Yahoo marketCap for the USD-traded NYSE ADR alongside totalRevenue, freeCashflow, totalCash and totalDebt in the issuer's ZAR reporting currency without checking Yahoo currency / financialCurrency. It then gave ratios and labels the suffix _usd.

## Corrective commit
930c7bfa2180f5b6cae25dc274ef0075166a8098 on feature/gbp-paper-equities-v1

- The new financial_currency_guard requires explicit ISO currency labels for both the quote and financial statements, and presently requires USD/USD before any balance sheet or income/cashflow figure may be called USD or scored.
- USD/ZAR, USD/CAD, missing financial currency or other noncomparable situations are excluded, not 'converted' using an imaginary exchange rate.
- The console logs CURRENCY SAFETY and the scan metadata counts rejected profiles.
- Unit tests cover USD/ZAR and other mismatches, missing metadata, and a correctly matching USD financial company.

## Scope and limitations
- Existing archived screenshots, reports and cached discovery shortlists are **unchanged** and retain the known defect. Research produced before this fix must not be construed as valid USD valuations.
- A future release should independently source statement-period-appropriate FX conversions, ADR ratios and issuer filings before restoring foreign-currency ADRs to the ranking.
- The change is **research only** and cannot mutate V1 or V2 trading accounts or place orders.
- SEC NOT_CONFIGURED continues to mean the optional filing source collector has not been configured; no official primary files may have been retrieved.

## Installation
Source-only Python updater: Koral_Discovery_FX_Safety_Updater.py; allowlist contains only tradingagents/paper/discovery.py, tests/test_discovery.py, README_DISCOVERY.md. Backups and SHA-256 ledger protection retained. Do not run while a discovery subprocess or dashboard is active.