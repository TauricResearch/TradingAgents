# India Data Sources

## Source Hierarchy

1. User-supplied local files.
2. Official NSE/BSE/company filings where feasible.
3. yfinance for public market data.
4. Alpha Vantage when configured.
5. Explicit unavailable responses.

## Local Files

Place files under:

```text
data/india/filings/<SYMBOL>/annual_report/*.pdf
data/india/filings/<SYMBOL>/concall/*.txt
data/india/filings/<SYMBOL>/investor_presentations/*.pdf
data/india/filings/<SYMBOL>/results/*.csv
data/india/filings/<SYMBOL>/notes/*.md
```

PDF OCR is intentionally not enabled by default. Convert important pages to text or markdown.

## NSE/BSE

NSE/BSE modules are defensive placeholders until verified public endpoints are added. If access is blocked or terms are unclear, return `UNAVAILABLE` and use local files.

## Data Quality

Every material block should state source, as-of timestamp, coverage, staleness, confidence, and warnings.
