# Debug: get_fundamentals fails for crypto tickers

## Bug Summary

Khi chạy với crypto ticker (e.g. `BTCUSDT`), `get_fundamentals` luôn fail hoặc trả về empty.
Root cause: chỉ có 1 vendor implementation (Alpha Vantage OVERVIEW API) — API này chỉ hỗ trợ equities.

---

## Call Chain

```
Fundamentals Analyst (LLM)
  │  LLM decides to call get_fundamentals("BTCUSDT", "2026-04-25")
  ▼
@tool get_fundamentals(ticker, curr_date)          # fundamental_data_tools.py:7
  │  return route_to_vendor("get_fundamentals", ticker, curr_date)
  ▼
route_to_vendor("get_fundamentals", ...)           # interface.py:109
  │  1. get_category_for_method("get_fundamentals") → "fundamental_data"
  │  2. get_vendor("fundamental_data") → "alpha_vantage"  (from config)
  │  3. VENDOR_METHODS["get_fundamentals"] → {"alpha_vantage": get_alpha_vantage_fundamentals}
  │  4. fallback_chain = ["alpha_vantage"]  ← ONLY ONE vendor, no fallback
  ▼
get_alpha_vantage_fundamentals("BTCUSDT", "2026-04-25")  # alpha_vantage_fundamentals.py:4
  │  _make_api_request("OVERVIEW", {"symbol": "BTCUSDT"})
  ▼
Alpha Vantage OVERVIEW API
  │  OVERVIEW only supports equities (AAPL, MSFT, etc.)
  │  Crypto symbols → returns empty JSON {} or error
  ▼
Empty string / useless response returned to LLM
```

---

## 5 Issues Found

### Issue 1 — CRITICAL: Single vendor, no fallback

**File:** `tradingagents/dataflows/interface.py:61-63`

```python
VENDOR_METHODS = {
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        # ← No Binance impl (crypto exchange has no fundamentals)
        # ← No yfinance impl (not integrated yet)
    },
}
```

`get_fundamentals` has exactly one vendor. When Alpha Vantage returns empty for crypto, there is no fallback. The pipeline gets an empty/useless response.
### Solution:
 - Remove alpha_vantage.
 - Cal yFinance api get_fundamentals, cashflow, financials

### Issue 2 — CRITICAL: Default vendor mismatch

**File:** `tradingagents/dataflows/interface.py:106`

```python
def get_vendor(category: str, method: str | None = None) -> str:
    return config.get("data_vendors", {}).get(category, "binance")  # ← default "binance"
```

If `fundamental_data` key is missing from config, `get_vendor()` returns `"binance"`. But Binance is not in `VENDOR_METHODS["get_fundamentals"]` → `route_to_vendor` skips it → raises `RuntimeError: No available vendor for 'get_fundamentals'`.

### Solution: Fallback vendors in list
- 1. Bianance dont support data
- 2. Call Yfinance
- 3. Call alpha_advantage
- You have to setup a linked list to store vendors

### Issue 3 — HIGH: Crypto config override is incomplete

**File:** `cli/main.py:918-923`

```python
if is_crypto_ticker(selections["ticker"]):
    config["data_vendors"] = {
        **config.get("data_vendors", {}),
        "core_stock_apis": "binance",
        "technical_indicators": "binance",
        # ← fundamental_data NOT overridden
        # ← news_data NOT overridden
    }
```

Crypto override only covers 2 of 4 categories. `fundamental_data` stays as `"alpha_vantage"`, which doesn't support crypto. If user selects "fundamentals" analyst with a crypto ticker, the LLM will call `get_fundamentals("BTCUSDT")` and get empty results.

### Issue 4 — HIGH: No symbol validation

**File:** `tradingagents/dataflows/alpha_vantage_fundamentals.py:4-19`

```python
def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    params = {"symbol": ticker}
    return _make_api_request("OVERVIEW", params)
    # ← No check: is this a crypto ticker? is the response empty?
```

Function blindly passes any symbol to OVERVIEW API. Should guard against crypto tickers and return a clear message.
### Solution
Symbol should be normailized before pass to other steps in CLI flow

### Issue 5 — MEDIUM: Fallback only triggers on rate limit

**File:** `tradingagents/dataflows/interface.py:133-135`

```python
try:
    return impl_func(*args, **kwargs)
except AlphaVantageRateLimitError:
    continue  # only rate limits trigger fallback
```

### Solution
- Fallback should be cover Binance Exception, Yfinance exception.

### Fix 3: Broaden fallback chain in route_to_vendor

```python
# interface.py — route_to_vendor()

for vendor in fallback_chain:
    if vendor not in VENDOR_METHODS[method]:
        continue
    impl_func = VENDOR_METHODS[method][vendor]
    if isinstance(impl_func, list):
        impl_func = impl_func[0]
    try:
        result = impl_func(*args, **kwargs)
        if result and str(result).strip():
            return result
        logger.warning("Vendor '%s' returned empty for '%s', trying next", vendor, method)
        continue
    except AlphaVantageRateLimitError:
        continue
    except Exception as e:
        logger.warning("Vendor '%s' failed for '%s': %s, trying next", vendor, method, e)
        continue

raise RuntimeError(f"No available vendor for '{method}'")
```
Any other exception (network error, empty response, invalid symbol) crashes the entire pipeline instead of trying the next vendor.

---

### Fix : Integrate yfinance as third vendor

After yfinance module is implemented (see `docs/yfinance-integration.md`), add to VENDOR_METHODS:

```python
VENDOR_METHODS = {
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,  # NEW
    },
    "get_stock_data": {
        "binance": get_binance_klines,
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_yfinance_stock,          # NEW
    },
}
```

---

## Files to Change

| File | Change | Priority |
|---|---|---|
| `dataflows/alpha_vantage_fundamentals.py` | Add crypto guard to all 4 functions | P0 |
| `cli/main.py` | Auto-skip fundamentals analyst for crypto | P0 |
| `dataflows/interface.py:route_to_vendor` | Catch all exceptions + empty response guard | P1 |
| `dataflows/interface.py:get_vendor` | Fix default from "binance" → smart lookup | P1 |
| `dataflows/yfinance.py` (new) | yfinance vendor implementation | P2 |
| `dataflows/interface.py` | Add yfinance to VENDOR_METHODS + VENDOR_LIST | P2 |

---

## How to Reproduce

```bash
python -m cli.main
# Step 1: Enter ticker → BTCUSDT
# Step 3: Select analysts → include "Fundamentals Analyst"
# Observe: Fundamentals Analyst returns empty/error report
```

## Expected vs Actual

| | Expected | Actual |
|---|---|---|
| Crypto + fundamentals | Clear message: "not available for crypto" or auto-skip | Empty report or RuntimeError |
| Stock + fundamentals | Alpha Vantage OVERVIEW data | Works correctly |
