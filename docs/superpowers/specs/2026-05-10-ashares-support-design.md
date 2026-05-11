# A-Shares Support via AKShare

**Date**: 2026-05-10
**Status**: Approved

## Context

TradingAgents currently supports yfinance and Alpha Vantage as data vendors. yfinance technically accepts Chinese tickers (`.SS` Shanghai, `.SZ` Shenzhen) but data quality is unreliable — sparse OHLCV, missing fundamentals, and US-centric news. This spec adds AKShare as a third data vendor to provide proper Chinese market coverage.

## Design Decisions

- **Single vendor**: AKShare only (not Tushare). Free, no API key, pip-installable.
- **Ticker format**: Both plain 6-digit codes (`600000`) and exchange-suffixed (`600000.SS`) accepted. System auto-normalizes.
- **Scope**: A-shares (Shanghai `.SS`, Shenzhen `.SZ`) + Hong Kong (`.HK`).
- **News language**: Chinese news preserved as-is. LLM models read Chinese natively.
- **Chinese name input**: User can enter Chinese stock names (e.g., `贵州茅台`, `腾讯控股`). System resolves to ticker code before the pipeline runs.

## Architecture

New file: `tradingagents/dataflows/akshare_data.py`

Modified files:
- `tradingagents/dataflows/interface.py` — register AKShare as third vendor
- `tradingagents/default_config.py` — add `"akshare"` to vendor comment options
- `tradingagents/agents/utils/agent_utils.py` — update `build_instrument_context()` to mention `.SS`/`.SZ`
- `cli/main.py` — update CLI ticker prompt examples to include A-shares
- `pyproject.toml` — add `akshare` dependency

## Ticker Normalization

Helper `_normalize_akshare_ticker(ticker)` returns `(code, exchange)`:

| Input | Code | Exchange |
|-------|------|----------|
| `600000` | `600000` | Shanghai |
| `600000.SS` | `600000` | Shanghai |
| `000001` | `000001` | Shenzhen |
| `000001.SZ` | `000001` | Shenzhen |
| `00700` | `00700` | Hong Kong |
| `0700.HK` | `00700` | Hong Kong |

Exchange detection: codes starting with `6` → Shanghai, `0`/`3` → Shenzhen, `.HK` suffix → Hong Kong. HK codes are zero-padded to 5 digits.

## Chinese Name Resolution

Users can enter Chinese stock names like `贵州茅台` or `腾讯控股` instead of ticker codes. Resolution via `ak.stock_info_a_code_name()` (A-shares) and `ak.stock_hk_spot_em()` (HK):

```python
# New utility in akshare_data.py
def resolve_ticker_name(name: str) -> str:
    """Resolve Chinese stock name to exchange-suffixed ticker.
    
    '贵州茅台' → '600519.SS'
    '腾讯控股' → '00700.HK'
    '600000'   → '600000.SS'   (auto-append suffix for plain codes)
    '600000.SS' → '600000.SS'  (pass-through)
    """
```

Resolution happens at two entry points:
1. **CLI** `get_ticker()` — if input contains Chinese characters, resolve and confirm with user
2. **`TradingAgentsGraph.propagate()`** — safety net for programmatic use

The resolved value always includes the exchange suffix so downstream code is consistent.


## Tool Function Mapping

Each function matches the existing signature and return type of its yfinance/Alpha Vantage counterpart.

| Tool | AKShare API | Returns |
|------|-----------|---------|
| `get_stock_data` | `ak.stock_zh_a_hist()` / `ak.stock_hk_hist()` | CSV string (Date, Open, High, Low, Close, Volume) |
| `get_indicators` | AKShare OHLCV → stockstats | Indicator value string per date |
| `get_fundamentals` | `ak.stock_individual_info_em()` | Text with mapped field names |
| `get_balance_sheet` | `ak.stock_balance_sheet_by_report_em()` | CSV string |
| `get_cashflow` | `ak.stock_cash_flow_sheet_by_report_em()` | CSV string |
| `get_income_statement` | `ak.stock_profit_sheet_by_report_em()` | CSV string |
| `get_news` | `ak.stock_news_em()` | Markdown news list |
| `get_global_news` | China macro endpoints | Markdown news list |
| `get_insider_transactions` | N/A | "Not supported" message |

## Configuration

```python
# default_config.py — vendor options updated
"data_vendors": {
    "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance, akshare
    "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance, akshare
    "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance, akshare
    "news_data": "yfinance",             # Options: alpha_vantage, yfinance, akshare
},
```

Users configure per-category: `config["data_vendors"]["core_stock_apis"] = "akshare"`. The existing vendor fallback chain works without modification.

## Error Handling

- Empty/missing data → `"No data found for symbol 'XXXXXX'"` (matches yfinance pattern)
- Invalid/delisted codes → empty DataFrame, caught and returned as error message
- AKShare upstream failures → try/except, return descriptive error string
- Non-trading days → existing "N/A: Not a trading day" handling works

## Testing

New file: `tests/test_akshare_data.py`

- **Unit tests** (`@pytest.mark.unit`): `_normalize_akshare_ticker` with plain codes, suffixed codes, HK codes, edge cases. Tool functions with mocked AKShare calls.
- **Integration tests** (`@pytest.mark.integration`): Live AKShare calls, skipped by default in CI.

## Files Changed

1. `tradingagents/dataflows/akshare_data.py` — **new**
2. `tradingagents/dataflows/interface.py` — import + register vendor
3. `tradingagents/default_config.py` — comment updates
4. `tradingagents/agents/utils/agent_utils.py` — `build_instrument_context` update
5. `cli/main.py` — ticker prompt examples update
6. `pyproject.toml` — add `akshare` dependency
7. `tests/test_akshare_data.py` — **new**
