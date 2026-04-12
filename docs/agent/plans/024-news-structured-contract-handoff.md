# 024 News Structured Contract Handoff

## Context

Latest audited run:

- Run ID: `01KP0QBCXE9J6Z3GB13N14AW3Q`
- Date: `2026-04-10`
- Type: `auto`
- Status: `completed`
- Tickers: `MRVL`, `LWLG`

The current news analyst and fact-checker flow produces usable structured claim JSON, but the resulting `news_report_structured` payload does not yet follow the same canonical status contract used by `market_report_structured`, `fundamentals_report_structured`, `sentiment_report_structured`, and other downstream contracts.

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
      "evidence_id": "art_7715d24cfa223b67"
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
    "claim_count": 1,
    "summary_rows": 1,
    "evidence_ids": 1,
    "removed_claims": 0,
    "below_min_claims": false
  }
}
```

Note: the example values are consistent with the MRVL sample (1 claim, 1 summary row). Production runs with richer evidence will have higher counts.

Status guidance:

- `completed`: at least one verified claim remains.
- `empty`: analyst produced a valid structured payload with zero claims, or sanitization yields zero claims with no removed claims.
- `invalid_structured_payload`: fact-checker rejected malformed payload, a non-canonical status was supplied, malformed claim/table entries reached the normalizer, or one or more submitted claims were all removed during sanitization.
- `missing_structured_payload`: analyst produced no structured payload.
- `aborted`: critical abort, including analyst timeout.

Use `completed` for 1+ verified claims. Use `below_min_claims: true` in `key_metrics` instead of treating sparse output as a separate status.

Do NOT use `completed_sparse` or `timeout_fallback` for news — they add ambiguity with no consumer benefit. Remove them from news documentation and code.

## Design Decisions

### Normalization ownership

The fact-checker is the **sole normalization point**. The news analyst returns raw validated payloads (or best-effort payloads). The fact-checker always calls `build_news_report_structured(...)` before returning, regardless of which branch it takes.

The analyst should NOT attempt to stamp `status`, `contract_version`, or `key_metrics` — that is the fact-checker's job.

Fact-checker early exits must also be folded into normalization. A blank report, existing `[CRITICAL ABORT]` report, missing payload, invalid payload, and all-claims-removed result must all return a canonical `news_report_v1` payload rather than a no-op update.

### Timeout policy

News analyst timeout is a failure, not a fallback success. Remove the news timeout fallback path and stop using `_build_timeout_structured_payload(...)` for news timeouts. On timeout, the analyst should return a critical-abort report; the fact-checker should normalize that to `status: "aborted"` with the abort reason preserved.

`timeout_fallback` remains valid for other contracts where already used, but it is not part of `news_report_v1`.

### `_news_structured_placeholder` removal

The existing `_news_structured_placeholder(...)` helper in `news_fact_checker.py` is superseded by `build_news_report_structured(...)`. It must be **deleted** once the new normalizer is in place. Do not maintain two functions that produce news contracts with different shapes.

### Resilience

The fact-checker must not fail easily. If the normalizer receives a malformed payload, it must produce a valid canonical contract with an appropriate error status (`invalid_structured_payload` or `empty`) rather than raising an exception. If sanitized claims passed evidence-based provenance checks but the rendered markdown fails a secondary quality gate (`validate_news_analysis_detailed`), the fact-checker should log a warning and return the canonical contract with `status: "completed"` — not `[CRITICAL ABORT]`.

Invalid structured payloads should not emit new `[CRITICAL ABORT]` markdown unless the upstream report already was a critical abort. Preserve observability, but let the canonical `status` carry structured validity.

### `scan_date` cleanup

The normalizer owns `scan_date` cleanup:

- Strip `scan_date` from claims where `source != "Finviz Smart Money Scanner"`.
- Retain `scan_date` only for scanner claims.
- Retain `scan_date` on scanner-derived `summary_table` rows.
- Require non-empty `evidence_id` on non-scanner claims and non-scanner summary rows.
- Require non-empty `scan_date` on scanner claims and scanner summary rows.

This is belt-and-suspenders — `sanitize_structured_news_payload` already filters scanner claims by `scan_date` presence upstream, but the normalizer enforces the invariant as a final pass.

### Markdown preservation and downstream gating

Markdown-only news may contain useful audit context, but it is not trusted evidence unless the structured payload passed validation and sanitization. Do not add a markdown salvage parser in this plan; defer salvage to a separate follow-up if audited runs prove it is necessary.

Downstream context builders must treat news as usable evidence only when:

```python
news_report_structured.status == "completed"
and news_report_structured.key_metrics.claim_count > 0
```

Do not require `key_metrics.evidence_ids > 0`, because scanner-only claims can be valid without article evidence IDs.

Keep `news_report` in state/artifacts for audit, but suppress the raw `## News Report` block from downstream context when the structured contract is not usable evidence.

### Deferred fields

Do NOT add `sentiment`, `materiality`, or `risk_direction` to the claim schema in this plan. They would all default to `"unknown"` with no consumer, adding contract noise. Defer to a follow-up plan where the analyst or fact-checker actually populates them.

## Implementation Plan

### Step 1: Add `build_news_report_structured(...)` in `output_validation.py`

Inputs:

- `ticker: str`
- `as_of_date: str`
- `payload: dict[str, Any]` — the sanitized payload from `sanitize_structured_news_payload`
- `status: str` — one of the canonical news statuses
- `abort_reason: str = ""`
- `removed_claims: list[dict] | None = None`

Responsibilities:

- Validate `status` against the canonical news status set: `completed`, `empty`, `invalid_structured_payload`, `missing_structured_payload`, `aborted`.
- If `status` is not canonical, return a valid contract with `status: "invalid_structured_payload"` and an explanatory `abort_reason`.
- Stamp `contract_version: "news_report_v1"`.
- Stamp `as_of_date`.
- Stamp `abort_reason`.
- Synthesize `report_title` as `"{TICKER} News Analysis"` when missing.
- Reconstruct output claims and summary rows without mutating the input payload.
- Whitelist the public contract fields rather than copying arbitrary analyst keys.
- Treat malformed claim or summary-row entries as `invalid_structured_payload`; do not silently drop them inside the normalizer.
- Compute `key_metrics`:
  - `claim_count`: number of reconstructed output claims
  - `summary_rows`: number of reconstructed output summary rows
  - `evidence_ids`: count of unique non-empty `evidence_id` values across claims
  - `removed_claims`: `len(removed_claims or [])`
  - `below_min_claims`: `True` if `payload.get("below_min_claims")` is truthy, else `False`
- Strip `scan_date` from article claims (where `source != "Finviz Smart Money Scanner"`).
- Retain `scan_date` for scanner claims and scanner summary rows.
- Omit blank optional scanner fields such as `published_at` and `evidence_id`.
- Wrap in try/except — if anything fails, return a valid contract with `status: "invalid_structured_payload"`.

Return type: `dict[str, Any]` — always a valid canonical contract, never raises.

### Step 2: Delete `_news_structured_placeholder` and update `news_fact_checker.py`

Delete `_news_structured_placeholder(...)`.

Update `create_news_fact_checker` so that **every return path** calls `build_news_report_structured(...)`:

| Branch | Status | Notes |
|--------|--------|-------|
| Blank `news_report` and missing payload | `missing_structured_payload` | Pass empty payload `{}` |
| Existing `[CRITICAL ABORT]` report | `aborted` | Pass empty payload `{}`, extract abort reason |
| Missing payload (`not isinstance(structured_payload, dict)`) | `missing_structured_payload` | Pass empty payload `{}` |
| Invalid payload (validation fails) | `invalid_structured_payload` | Pass empty payload `{}`, include validation reason in `abort_reason`; do not emit a new critical-abort report |
| Zero claims after sanitization with removed claims | `invalid_structured_payload` | Claims were submitted but all rejected by fact-checking |
| Zero claims after sanitization without removed claims | `empty` | No validated claims were produced |
| Rendered report fails `validate_news_analysis_detailed` | `completed` | **Do not abort.** Log a warning. Return the sanitized canonical contract. Provenance-checked claims should not be discarded because of a secondary rendering quality check. |
| Happy path (1+ claims, rendering valid) | `completed` | Pass sanitized payload |

Key resilience change: The current code (lines 109-117 of `news_fact_checker.py`) returns `[CRITICAL ABORT]` when the rendered report fails `validate_news_analysis_detailed`. This is too aggressive — the sanitized claims already passed evidence-based provenance checks. Downgrade to a warning log and return `status: "completed"`.

For structured failure branches, keep untrusted markdown out of downstream evidence. The raw `news_report` may remain in state/artifacts for audit, but only completed canonical claims are evidence.

### Step 3: Update `news_analyst.py` timeout behavior

The analyst still should not stamp canonical contract fields, but it must stop returning a synthetic structured timeout fallback for news.

Update timeout branches so they return a critical-abort markdown report and an empty structured payload:

```python
report = f"[CRITICAL ABORT] Reason: News analyst timed out after {timeout_seconds}s for {ticker}"
return {
    "messages": [AIMessage(content=report)],
    "news_report": report,
    "news_report_structured": {},
}
```

The fact-checker remains the sole canonical normalization point and will convert the critical abort into `status: "aborted"`.

### Step 4: Add `_format_news_structured(...)` in `summary_context.py`

Add a formatter following the pattern of `_format_market_structured` and `_format_fundamentals_structured`:

```python
def _format_news_structured(structured: object) -> str:
    if not isinstance(structured, dict):
        return ""
    key_metrics = structured.get("key_metrics") or {}
    if not isinstance(key_metrics, dict):
        key_metrics = {}
    lines = [
        f"- status: {structured.get('status', '')}",
        f"- contract_version: {structured.get('contract_version', '')}",
        f"- claim_count: {key_metrics.get('claim_count', '')}",
        f"- summary_rows: {key_metrics.get('summary_rows', '')}",
        f"- evidence_ids: {key_metrics.get('evidence_ids', '')}",
        f"- removed_claims: {key_metrics.get('removed_claims', '')}",
        f"- below_min_claims: {key_metrics.get('below_min_claims', '')}",
    ]
    return "\n".join(line for line in lines if _has_value_after_colon(line))
```

Wire it into `build_research_packet()` — insert after the sentiment structured contract block (line 196) and before the raw report blocks (line 199):

```python
news_structured = _format_news_structured(state.get("news_report_structured"))
if news_structured:
    sections.append(f"## News Structured Contract\n{news_structured}")
```

Also add a compact deterministic news metrics section to `build_debate_evidence_brief()`. This section should use only `news_report_structured.key_metrics` and `status`; do not ask an LLM to compute or infer these values. Keep it shorter than the research packet and exclude claim text:

```text
## News
- News status: completed
- News claims: 2
- Evidence IDs: 2
- Removed claims: 0
```

For non-completed statuses, still include status/metrics so downstream agents can see why news is not usable evidence.

### Step 5: Update `render_structured_news_payload` — add Evidence ID column

The current markdown summary table drops `evidence_id` even though the structured table has it. Add an `Evidence ID` column:

Current:
```
| Date | Event | Metric | Value | Source |
```

New:
```
| Date | Event | Metric | Value | Source | Evidence ID |
```

Update the row rendering to include `evidence_id`:
```python
evidence_id = str(row.get("evidence_id") or "").strip()
lines.append(
    f"| {date} | {event} | {metric} | {value} | {source} | {evidence_id} |"
)
```

For scanner summary rows, keep `scan_date` in the structured payload. The markdown renderer may continue showing the table date and source fields; the key contract requirement is that scanner rows retain `scan_date` structurally.

### Step 6: Update downstream propagation checks

After this fix, downstream logic should read:

- `news_report_structured.status` — always present, never `null`
- `news_report_structured.contract_version` — always `"news_report_v1"`
- `news_report_structured.key_metrics.claim_count` — integer, 0+

In `build_research_manager_fallback()` (output_validation.py, line 399-442), add a status check before iterating claims:

```python
news_status = str(news_structured.get("status") or "").strip()
key_metrics = news_structured.get("key_metrics") or {}
claim_count = key_metrics.get("claim_count", 0) if isinstance(key_metrics, dict) else 0
news_has_usable_evidence = news_status == "completed" and claim_count > 0
if not news_has_usable_evidence:
    lines.append(f"- Bear: News structured contract has status '{news_status}' (MED)")
```

Gate all news-claim iteration behind `news_has_usable_evidence`. Avoid testing `news_report_structured` only by truthiness — always check `.status` and `key_metrics.claim_count`.

In `build_research_packet()`, include `## News Structured Contract` for every canonical status, but include the raw `## News Report` block only when `news_has_usable_evidence` is true. This prevents unverified markdown from influencing downstream agents while preserving it in state/artifacts.

### Step 7: Update documentation

Update `docs/SYSTEM_TECHNICAL_DOCUMENTATION.md` so the `news_report_structured` section reflects:

- `contract_version: "news_report_v1"`
- status set: `completed | empty | invalid_structured_payload | missing_structured_payload | aborted`
- `abort_reason`
- `key_metrics.claim_count`, `summary_rows`, `evidence_ids`, `removed_claims`, `below_min_claims`

Remove `timeout_fallback` and `completed_sparse` from news-specific documentation.

## Tests To Add

### Unit tests in `tests/unit/test_output_validation.py`

Add a `TestNewsStructuredContract` class:

1. **`test_build_news_report_structured_completed`**
   - Pass a sanitized payload with 2 claims, `status="completed"`.
   - Assert `status == "completed"`, `contract_version == "news_report_v1"`, `key_metrics.claim_count == 2`.

2. **`test_build_news_report_structured_empty`**
   - Pass empty payload, `status="empty"`.
   - Assert `status == "empty"`, `key_metrics.claim_count == 0`.

3. **`test_build_news_report_structured_strips_null_scan_date`**
   - Pass payload with an article claim containing `scan_date: null`.
   - Assert `"scan_date" is not a key in the normalized claim.`

4. **`test_build_news_report_structured_retains_scanner_scan_date`**
   - Pass payload with a scanner claim containing `scan_date: "2026-04-10"`.
   - Assert `claim["scan_date"] == "2026-04-10"`.

5. **`test_build_news_report_structured_computes_key_metrics`**
   - Pass payload with 3 claims (2 unique evidence IDs), 2 summary rows, 1 removed claim.
   - Assert `claim_count == 3`, `summary_rows == 2`, `evidence_ids == 2`, `removed_claims == 1`.

6. **`test_build_news_report_structured_survives_malformed_payload`**
   - Pass `payload=None` or `payload="garbage"`.
   - Assert returns valid contract with `status == "invalid_structured_payload"`, does not raise.

7. **`test_build_news_report_structured_below_min_claims_flag`**
   - Pass payload with `below_min_claims: True`.
   - Assert `key_metrics.below_min_claims is True`.

### Unit tests in `tests/unit/test_news_fact_checker.py`

8. **`test_fact_checker_returns_completed_contract_after_sanitization`**
   - Wire mock `NewsEvidenceStore` with known records.
   - Feed state with a valid `news_report_structured` payload.
   - Assert returned `news_report_structured.status == "completed"` and `contract_version == "news_report_v1"`.

9. **`test_fact_checker_returns_invalid_contract_when_all_claims_removed`**
   - Feed state with claims that all fail sanitization.
   - Assert `status == "invalid_structured_payload"`, `key_metrics.claim_count == 0`, and `key_metrics.removed_claims > 0`.

10. **`test_fact_checker_missing_payload_has_canonical_contract`**
    - Feed state with `news_report_structured=None`.
    - Assert `status == "missing_structured_payload"`, `contract_version == "news_report_v1"`.

11. **`test_fact_checker_invalid_payload_has_canonical_contract`**
    - Feed state with `news_report_structured={"ticker": "WRONG"}`.
    - Assert `status == "invalid_structured_payload"`, `contract_version == "news_report_v1"`.

12. **`test_fact_checker_does_not_critical_abort_on_rendering_validation_failure`**
    - Feed state where sanitized claims are valid but `validate_news_analysis_detailed` on the rendered report would fail (e.g., low ticker mentions).
    - Assert `status == "completed"` — NOT `[CRITICAL ABORT]`.

13. **`test_fact_checker_end_to_end_contract_shape`**
    - Assert final `news_report_structured` always has: `status`, `contract_version`, `as_of_date`, `abort_reason`, `key_metrics`, `claims`, `summary_table`.

14. **`test_fact_checker_aborted_report_has_canonical_contract`**
    - Feed state with `news_report` starting with `[CRITICAL ABORT]`.
    - Assert `status == "aborted"` and the abort reason is preserved.

Do not create a new integration test file unless a broader analyst-to-fact-checker flow is added. The fact-checker branch coverage belongs in the existing unit test file.

### Regression assertion for latest observed bug

```python
def test_regression_news_status_never_null(result):
    payload = result["news_report_structured"]
    assert payload["status"] in {
        "completed", "empty", "invalid_structured_payload",
        "missing_structured_payload", "aborted",
    }
    assert payload["contract_version"] == "news_report_v1"
    assert isinstance(payload["key_metrics"], dict)
    assert isinstance(payload["key_metrics"]["claim_count"], int)
```

## Non-Goals

- Do not make the analyst LLM output stricter as the main fix.
- Do not require three claims to consider the node usable. Sparse but verified news is better than failed news.
- Do not add hard failure for missing optional interpretation fields (`sentiment`, `materiality`, `risk_direction`). These are deferred entirely — no `unknown` defaults.
- Do not add `completed_sparse` or `timeout_fallback` as news statuses. They are removed from this plan and must not appear in news code.
- Do not add a markdown salvage parser in this plan. If needed, create a separate follow-up with narrow deterministic parsing and dedicated tests.
- Do not add `raw_report_chars` or other markdown-preservation metadata to `news_report_v1`.
- Do not rerun live auto workflows unless explicitly requested.

## Follow-Up After Contract Fix

After the news contract fix, re-audit:

- `news_report_structured.status` propagation through all downstream consumers
- deterministic markdown salvage for renderer-produced cited bullets, only if audited runs show validated evidence is trapped in markdown
- `trader_plan_structured.recommendation` alias compatibility
- `[PM_EMPTY_RESPONSE]` removal/fail-fast behavior from pipeline-level Portfolio Manager
- Add `sentiment`, `materiality`, `risk_direction` to claim schema when a consumer exists

Those are separate but related propagation issues from the same latest run review.
