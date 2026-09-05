# PR20: Research Readiness Checklist

## Purpose

PR20 adds a deterministic evidence-readiness checklist to the local cockpit and Markdown report. It tells the researcher which evidence and review layers are present, lagging, missing, or not started. It is not a recommendation engine and does not change a trade signal or risk decision.

## Required Evidence

The overall readiness state evaluates five required evidence layers:

- market data with point-in-time cache health;
- fundamental snapshots with point-in-time cache health;
- historical valuation context with at least 20 valid daily observations;
- disclosed financial-health metrics; and
- a structured investment thesis.

Corporate events, manual decision, risk review, and backtest remain visible optional workflow layers. Once a manual decision exists, a missing risk review or backtest is marked for attention.

## Status

- `ready`: all required evidence layers are available and aligned.
- `attention`: required evidence is present but at least one cached source is lagging.
- `incomplete`: one or more required evidence layers are missing.

Financial health records availability rather than desirability: a `watch` or `caution` assessment is still usable disclosed evidence and is shown verbatim in the item detail.
