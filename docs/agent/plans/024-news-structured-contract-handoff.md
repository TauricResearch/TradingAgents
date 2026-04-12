# 024 News Structured Contract Handoff

## Context

Latest audited run:

- Run ID: `01KP0QBCXE9J6Z3GB13N14AW3Q`
- Date: `2026-04-10`
- Type: `auto`
- Status: `completed`
- Tickers: `MRVL`, `LWLG`

The current news analyst and fact-checker flow produces usable structured claim JSON, but the resulting `news_report_structured` payload does not yet follow the same canonical status contract used by market/fundamentals/trader outputs.

This weakens downstream propagation because checks see `news_report_structured.status == null` even when claims were successfully validated.

## Current Output Examples

MRVL artifact:

- `reports/daily/2026-04-10/01KP0QBCXE9J6Z3GB13N14AW3Q/MRVL/report/20260412T114210883Z_complete_report.json`

Current `news_report_structured` shape:

```json
{
  "ticker": "MRVL",
  "report_title": "MRVL News Analysis",
  "claims": [
    {
      "claim": "Marvell Technology shares received an upgrade from Barclays analysts, who believe the company's focus on selling optical components for AI data centers will drive further growth.",
      "source": "Barron's",
      "published_at": "2026-04-09",
      "evidence_id": "art_7715d24cfa223b67",
      "scan_date": null
    }
  ],
  "summary_table": [
    {
      "date": "2026-04-09",
      "event": "Barclays Upgrade",
      "metric": "Rating Change",
      "value": "Overweight",
      "source": "Barron's",
      "evidence_id": "art_7715d24cfa223b67"
    }
  ]
}
```

LWLG artifact:

- `reports/daily/2026-04-10/01KP0QBCXE9J6Z3GB13N14AW3Q/LWLG/report/20260412T114133385Z_complete_report.json`

Current `news_report_structured` shape:

```json
{
  "ticker": "LWLG",
  "report_title": "LWLG News Analysis",
  "claims": [
    {
      "claim": "Lightwave Logic (LWLG) director Craig Ciesla sold 11,000 shares of the company's stock for $74,910.00 to cover tax withholding obligations on vested equity.",
      "source": "MarketBeat",
      "published_at": "2026-04-08",
      "evidence_id": "art_ed6be0667008ea15",
      "scan_date": null
    }
  ],
  "summary_table": [
    {
      "date": "2026-04-08",
      "event": "Director Sale",
      "metric": "Shares Sold",
      "value": "11,000",
      "source": "MarketBeat",
      "evidence_id": "art_ed6be0667008ea15"
    }
  ]
}
```

## Problem Statement

Earlier attempts at strict structured news output failed because the model was asked to produce perfect provenance JSON directly. Small schema/source/date issues caused validation rejection.

The better pattern is already present:

1. Let the LLM produce best-effort structured claims.
2. Validate and sanitize against run-scoped evidence IDs.
3. Deterministically normalize the sanitized payload into a canonical contract.

The missing piece is step 3.

## Target Contract

Add a canonical `news_report_v1` payload:

```json
{
  "ticker": "MRVL",
  "as_of_date": "2026-04-10",
  "status": "completed",
  "contract_version": "news_report_v1",
  "abort_reason": "",
  "report_title": "MRVL News Analysis",
  "claims": [
    {
      "claim": "...",
      "source": "Barron's",
      "published_at": "2026-04-09",
      "evidence_id": "art_7715d24cfa223b67",
      "sentiment": "unknown",
      "materiality": "unknown",
      "risk_direction": "unknown"
    }
  ],
  "summary_table": [
    {
      "date": "2026-04-09",
      "event": "Barclays Upgrade",
      "metric": "Rating Change",
      "value": "Overweight",
      "source": "Barron's",
      "evidence_id": "art_7715d24cfa223b67"
    }
  ],
  "key_metrics": {
    "claim_count": 5,
    "summary_rows": 5,
    "evidence_ids": 5,
    "removed_claims": 0
  }
}
```

Status guidance:

- `completed`: at least one verified claim remains.
- `completed_sparse`: one verified claim remains if the caller wants to distinguish sparse evidence.
- `empty`: zero verified claims remain.
- `timeout_fallback`: timeout path generated fallback payload.
- `invalid_structured_payload`: fact-checker rejected malformed payload.
- `missing_structured_payload`: analyst produced no structured payload.
- `aborted`: critical abort.

Recommendation: use `completed` for 1+ verified claims initially. Add `below_min_claims: true` in `key_metrics` instead of treating sparse output as failure.

## Files To Inspect

Primary files:

- `tradingagents/agents/analysts/news_analyst.py`
- `tradingagents/agents/managers/news_fact_checker.py`
- `tradingagents/agents/utils/output_validation.py`
- `tradingagents/agents/utils/summary_context.py`
- `agent_os/backend/services/langgraph_engine.py`

Useful existing patterns:

- `build_market_report_structured(...)` in `output_validation.py`
- `build_fundamentals_report_structured(...)` in `output_validation.py`
- `build_trader_plan_structured(...)` in `output_validation.py`
- `_news_structured_placeholder(...)` in `news_fact_checker.py`
- `sanitize_structured_news_payload(...)` in `output_validation.py`
- `render_structured_news_payload(...)` in `output_validation.py`

## Implementation Plan

1. Add `build_news_report_structured(...)` or `normalize_news_report_structured(...)` in `output_validation.py`.

   Inputs should include:

   - `ticker`
   - `as_of_date`
   - `payload`
   - `status`
   - `abort_reason`
   - `removed_claims`

   Responsibilities:

   - add `status`
   - add `contract_version: news_report_v1`
   - add `as_of_date`
   - add `abort_reason`
   - compute `key_metrics`
   - remove `scan_date: null` from article claims
   - keep `scan_date` only for scanner claims
   - default optional interpretation fields to `unknown`

2. Update `news_analyst.py` timeout paths to return canonical `news_report_structured`.

3. Update `news_fact_checker.py`.

   Required behavior:

   - missing payload returns canonical contract with `status: missing_structured_payload`
   - invalid payload returns canonical contract with `status: invalid_structured_payload`
   - zero kept claims returns canonical contract with `status: empty`
   - one or more kept claims returns canonical contract with `status: completed`

4. Update rendering if needed.

   Keep markdown evidence citation output, but consider adding `Evidence ID` to summary table rows. Current markdown table drops it, even though the structured table has it.

5. Update propagation checks.

   After this fix, downstream logic should be able to read:

   - `news_report_structured.status`
   - `news_report_structured.key_metrics.claim_count`

   Avoid testing `news_report_structured` only by truthiness.

## Tests To Add

Add focused unit tests, likely in `tests/unit/test_output_validation.py` and/or a dedicated news fact-checker test module.

Suggested tests:

1. `test_normalize_news_structured_adds_status_version_and_metrics`
2. `test_normalize_news_structured_removes_null_scan_date_for_articles`
3. `test_news_fact_checker_returns_completed_contract_after_sanitization`
4. `test_news_fact_checker_returns_empty_contract_when_all_claims_removed`
5. `test_news_fact_checker_missing_payload_contract_has_status`
6. `test_news_timeout_payload_has_news_report_v1_contract`

Regression assertion for latest observed problem:

```python
assert payload["status"] in {"completed", "completed_sparse"}
assert payload["contract_version"] == "news_report_v1"
assert payload["key_metrics"]["claim_count"] >= 1
```

## Non-Goals

Do not make the analyst LLM output stricter as the main fix.

Do not require three claims to consider the node usable. Sparse but verified news is better than failed news.

Do not add hard failure for missing optional interpretation fields like `sentiment`, `materiality`, or `risk_direction`.

Do not rerun live auto workflows unless explicitly requested.

## Follow-Up After Contract Fix

After the news contract fix, re-audit:

- `news_report_structured.status`
- `trader_plan_structured.recommendation` alias compatibility
- `[PM_EMPTY_RESPONSE]` removal/fail-fast behavior from pipeline-level Portfolio Manager

Those are separate but related propagation issues from the same latest run review.
