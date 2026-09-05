# PR21: Company Profile

## Purpose

PR21 adds a compact issuer profile to A-share research: company name, area, industry, market segment, exchange, and listing date. The cockpit and Markdown report render it separately from valuation and financial metrics.

## Source and Availability

For A shares, the Tushare adapter calls `stock_basic` with the canonical Tushare code and stores returned fields on the latest `daily_snapshot`. The profile call is optional: an unavailable endpoint or permission error leaves the profile empty and does not fail the research job or replace any core market/fundamental evidence.

Hong Kong and Yahoo Finance runs preserve an explicit unavailable profile until a source with matching issuer-identity fields is added.

## Semantics

The profile contains only vendor-supplied identity fields. It does not infer peers, sectors, industry classifications, or business descriptions from ticker text.
