# PR18: Financial Health Check

## Purpose

The research platform now derives a compact, deterministic financial-health assessment from the latest disclosed financial-quality snapshot. It is an evidence layer for personal research, not an investment recommendation and not an input that changes the existing trade-risk decision.

## Checks

| Check | Reference threshold | Result below/above threshold |
| --- | ---: | --- |
| Cash conversion | Operating cash flow / net income >= 0.8 | `watch` below |
| Leverage | Debt to assets <= 60% | `caution` above |
| Liquidity | Current ratio >= 1.0 | `watch` below |
| Return on equity | ROE >= 10% | `watch` below |

Missing, non-numeric, or non-finite values remain `unknown`; they are never inferred from unrelated values.

## Status Semantics

- `healthy`: all four checks are healthy.
- `watch`: available checks have no `caution`, but at least one check is below its reference threshold or unknown.
- `caution`: leverage is above its reference threshold.
- `unknown`: no check has an available disclosed metric.

The Markdown report renders this section after Financial Quality. The local cockpit exposes the same structured assessment in `/api/snapshot` and displays its individual checks.
