# Plan: Opt-in Vendor Fallback (Fail-Fast by Default)

**Status**: pending
**ADR**: 011 (to be created)
**Branch**: claude/objective-galileo
**Depends on**: PR #16 (Finnhub integration)

## Context

The current `route_to_vendor()` silently tries every available vendor when the primary fails. This is dangerous for trading software — different vendors return different data contracts (e.g., AV news has sentiment scores, yfinance doesn't; stockstats indicator names are incompatible with AV API names). Silent fallback corrupts signal quality without leaving a trace.

**Decision**: Default to fail-fast. Only tools in `FALLBACK_ALLOWED` (where data contracts are vendor-agnostic) get vendor fallback. Everything else raises on primary vendor failure.

## FALLBACK_ALLOWED Whitelist

```python
FALLBACK_ALLOWED = {
    "get_stock_data",           # OHLCV is fungible across vendors
    "get_market_indices",       # SPY/DIA/QQQ quotes are fungible
    "get_sector_performance",   # ETF-based proxy, same approach
    "get_market_movers",        # Approximation acceptable for screening
    "get_industry_performance", # ETF-based proxy
}
```

**Explicitly excluded** (data contracts differ across vendors):
- `get_news` — AV has `ticker_sentiment_score`, `relevance_score`, `overall_sentiment_label`; yfinance has raw headlines only
- `get_global_news` — same reason as get_news
- `get_indicators` — stockstats names (`close_50_sma`, `macdh`, `boll_ub`) ≠ AV API names (`SMA`, `MACD`, `BBANDS`)
- `get_fundamentals` — different fiscal period alignment, different coverage depth
- `get_balance_sheet` — vendor-specific field schemas
- `get_cashflow` — vendor-specific field schemas
- `get_income_statement` — vendor-specific field schemas
- `get_insider_transactions` — Finnhub provides MSPR aggregate data that AV/yfinance don't
- `get_topic_news` — different structure/fields across vendors
- `get_earnings_calendar` — Finnhub-only, nothing to fall back to
- `get_economic_calendar` — Finnhub-only, nothing to fall back to

## Phase 1: Core Logic Change

- [ ] **1.1** Add `FALLBACK_ALLOWED` set to `tradingagents/dataflows/interface.py` (after `VENDOR_LIST`, ~line 108)
- [ ] **1.2** Modify `route_to_vendor()`:
  - Only build extended vendor chain when `method in FALLBACK_ALLOWED`
  - Otherwise limit attempts to configured primary vendor(s) only
  - Capture `last_error` and chain into RuntimeError via `from last_error`
  - Improve error message: `"All vendors failed for '{method}' (tried: {vendors})"`

## Phase 2: Test Updates

- [ ] **2.1** Verify existing fallback tests still pass (`get_stock_data`, `get_market_movers`, `get_sector_performance` are all in `FALLBACK_ALLOWED`)
- [ ] **2.2** Update `tests/test_e2e_api_integration.py::test_raises_runtime_error_when_all_vendors_fail` — error message changes from `"No available vendor"` to `"All vendors failed for..."`
- [ ] **2.3** Create `tests/test_vendor_failfast.py` with:
  - `test_news_fails_fast_no_fallback` — configure AV, make it raise, assert RuntimeError (no silent yfinance fallback)
  - `test_indicators_fail_fast_no_fallback` — same pattern for indicators
  - `test_fundamentals_fail_fast_no_fallback` — same for fundamentals
  - `test_insider_transactions_fail_fast_no_fallback` — configure Finnhub, make it raise, assert RuntimeError
  - `test_topic_news_fail_fast_no_fallback` — verify no cross-vendor fallback
  - `test_calendar_fail_fast_single_vendor` — Finnhub-only, verify fail-fast
  - `test_error_chain_preserved` — verify `RuntimeError.__cause__` is set
  - `test_error_message_includes_method_and_vendors` — verify debuggable error text
  - `test_auth_error_propagates` — verify 401/403 errors don't silently retry

## Phase 3: Documentation

- [ ] **3.1** Create `docs/agent/decisions/011-opt-in-vendor-fallback.md`
  - Context: silent fallback corrupts signal quality
  - Decision: fail-fast by default, opt-in fallback for fungible data
  - Constraints: adding to `FALLBACK_ALLOWED` requires verifying data contract compatibility
  - Actionable Rules: never add news/indicator tools to FALLBACK_ALLOWED
- [ ] **3.2** Update ADR 002 — mark as `superseded-by: 011`
- [ ] **3.3** Update ADR 008 — add opt-in fallback rule to vendor fallback section
- [ ] **3.4** Update ADR 010 — note insider transactions excluded from fallback
- [ ] **3.5** Update `docs/agent/CURRENT_STATE.md`

## Phase 4: Verification

- [ ] **4.1** Run full offline test suite: `pytest tests/ -v -m "not integration"`
- [ ] **4.2** Verify zero new failures introduced
- [ ] **4.3** Smoke test: `python -m cli.main scan --date 2026-03-17`

## Files Changed

| File | Change |
|---|---|
| `tradingagents/dataflows/interface.py` | Add `FALLBACK_ALLOWED`, rewrite `route_to_vendor()` |
| `tests/test_e2e_api_integration.py` | Update error message match pattern |
| `tests/test_vendor_failfast.py` | **New** — 9 fail-fast tests |
| `docs/agent/decisions/011-opt-in-vendor-fallback.md` | **New** ADR |
| `docs/agent/decisions/002-data-vendor-fallback.md` | Mark superseded |
| `docs/agent/decisions/008-lessons-learned.md` | Add opt-in rule |
| `docs/agent/decisions/010-finnhub-vendor-integration.md` | Note insider txn exclusion |
| `docs/agent/CURRENT_STATE.md` | Update progress |

## Edge Cases

| Case | Handling |
|---|---|
| Multi-vendor primary config (`"finnhub,alpha_vantage"`) | All comma-separated vendors tried before giving up — works for both modes |
| Calendar tools (Finnhub-only) | Not in `FALLBACK_ALLOWED`, single-vendor so fail-fast is a no-op |
| `get_topic_news` | Excluded — different vendors have different news schemas |
| Composite tools (`get_ttm_analysis`) | Calls `route_to_vendor()` for sub-tools directly — no action needed |
