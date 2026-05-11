# A-Shares Support via AKShare — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AKShare as a third data vendor so TradingAgents supports A-shares (Shanghai `.SS`, Shenzhen `.SZ`) and Hong Kong (`.HK`) with reliable OHLCV, fundamentals, financial statements, news, and Chinese-name ticker resolution.

**Architecture:** New `akshare_data.py` module following the exact vendor pattern of `y_finance.py`. Registered in `interface.py` via `VENDOR_LIST` / `VENDOR_METHODS`. Ticker normalization strips exchange suffixes for AKShare calls. Chinese name resolution happens at the CLI and `propagate()` entry points.

**Tech Stack:** AKShare, pandas, stockstats (existing), pytest with mocks

---

### Task 1: Add AKShare dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add akshare to pyproject.toml dependencies**

Add `"akshare>=1.17.0"` to the `dependencies` list in `pyproject.toml`, alphabetically sorted (it goes before `"langchain-core>=0.3.81"`).

```toml
dependencies = [
    "akshare>=1.17.0",
    "langchain-core>=0.3.81",
    ...
]
```

- [ ] **Step 2: Install the dependency**

Run: `pip install akshare>=1.17.0`

- [ ] **Step 3: Verify akshare imports**

Run: `python -c "import akshare as ak; print(ak.__version__)"`
Expected: prints version number, no errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add akshare dependency for A-share data support"
```

---

### Task 2: Write tests for ticker normalization

**Files:**
- Create: `tests/test_akshare_data.py`

- [ ] **Step 1: Write ticker normalization and name resolution tests**

Create `tests/test_akshare_data.py`:

```python
import pytest
from tradingagents.dataflows.akshare_data import (
    _normalize_akshare_ticker,
    resolve_ticker_name,
)


class TestNormalizeAkshareTicker:
    @pytest.mark.unit
    def test_plain_shanghai_code(self):
        code, exchange = _normalize_akshare_ticker("600000")
        assert code == "600000"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_plain_shenzhen_code_starting_0(self):
        code, exchange = _normalize_akshare_ticker("000001")
        assert code == "000001"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_plain_shenzhen_code_starting_3(self):
        code, exchange = _normalize_akshare_ticker("300750")
        assert code == "300750"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_suffixed_shanghai(self):
        code, exchange = _normalize_akshare_ticker("600000.SS")
        assert code == "600000"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_suffixed_shenzhen(self):
        code, exchange = _normalize_akshare_ticker("000001.SZ")
        assert code == "000001"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_suffixed_hk(self):
        code, exchange = _normalize_akshare_ticker("0700.HK")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_plain_hk_code(self):
        code, exchange = _normalize_akshare_ticker("00700")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_hk_pads_to_5_digits(self):
        code, exchange = _normalize_akshare_ticker("700.HK")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_star_market_shanghai(self):
        code, exchange = _normalize_akshare_ticker("688001")
        assert code == "688001"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_beijing_exchange(self):
        code, exchange = _normalize_akshare_ticker("830799")
        assert code == "830799"
        assert exchange == "shenzhen"


class TestResolveTickerName:
    @pytest.mark.unit
    def test_chinese_name_detected(self):
        assert _is_chinese_name("贵州茅台") is True

    @pytest.mark.unit
    def test_english_ticker_not_chinese(self):
        assert _is_chinese_name("600000.SS") is False

    @pytest.mark.unit
    def test_mixed_is_chinese(self):
        assert _is_chinese_name("平安银行") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_akshare_data.py -v`
Expected: FAIL — module `tradingagents.dataflows.akshare_data` doesn't exist yet.

- [ ] **Step 3: Commit**

```bash
git add tests/test_akshare_data.py
git commit -m "test: add ticker normalization tests for AKShare"
```

---

### Task 3: Implement ticker normalization and Chinese name resolution

**Files:**
- Create: `tradingagents/dataflows/akshare_data.py`

- [ ] **Step 1: Create the module with normalization helpers**

Create `tradingagents/dataflows/akshare_data.py`:

```python
"""AKShare data vendor for A-shares (Shanghai/Shenzhen) and Hong Kong stocks."""

import re
from typing import Tuple


def _is_chinese_name(name: str) -> bool:
    """Check if input contains Chinese characters."""
    return bool(re.search(r'[一-鿿]', name))


def _normalize_akshare_ticker(ticker: str) -> Tuple[str, str]:
    """Normalize a ticker to AKShare code and exchange.

    Args:
        ticker: Raw ticker, e.g. '600000', '600000.SS', '0700.HK'

    Returns:
        (code, exchange) where code is the plain digits and exchange
        is 'shanghai', 'shenzhen', or 'hongkong'
    """
    ticker = ticker.strip().upper()

    # Hong Kong: .HK suffix or 5-digit code starting with 0
    if ticker.endswith('.HK'):
        code = ticker.replace('.HK', '').lstrip('0') or '0'
        return (code.zfill(5), 'hongkong')

    # Strip exchange suffix for A-shares
    if ticker.endswith('.SS'):
        code = ticker.replace('.SS', '')
        return (code, 'shanghai')
    if ticker.endswith('.SZ'):
        code = ticker.replace('.SZ', '')
        return (code, 'shenzhen')

    # Plain 6-digit code — detect exchange from first digit
    if ticker.isdigit():
        if ticker.startswith('6'):
            return (ticker, 'shanghai')
        if ticker.startswith(('0', '3')):
            return (ticker, 'shenzhen')
        # 5-digit code starting with 0 — Hong Kong
        if ticker.startswith('0') and len(ticker) <= 5:
            return (ticker.zfill(5), 'hongkong')

    raise ValueError(f"Cannot normalize ticker: {ticker!r}")
```

- [ ] **Step 2: Run ticker normalization tests**

Run: `pytest tests/test_akshare_data.py::TestNormalizeAkshareTicker -v`
Expected: All 9 tests PASS.

- [ ] **Step 3: Implement Chinese name resolution**

Add to `akshare_data.py`:

```python
from typing import Optional

# Cache for name-to-code mappings, populated lazily
_name_cache: Optional[dict] = None
_hk_name_cache: Optional[dict] = None


def _ensure_name_cache():
    """Populate A-share name→code cache from AKShare."""
    global _name_cache
    if _name_cache is None:
        try:
            import akshare as ak
            df = ak.stock_info_a_code_name()
            _name_cache = dict(zip(df['name'], df['code']))
        except Exception:
            _name_cache = {}


def _ensure_hk_name_cache():
    """Populate HK name→code cache from AKShare."""
    global _hk_name_cache
    if _hk_name_cache is None:
        try:
            import akshare as ak
            df = ak.stock_hk_spot_em()
            _hk_name_cache = dict(zip(df['名称'], df['代码']))
        except Exception:
            _hk_name_cache = {}


def resolve_ticker_name(name: str) -> str:
    """Resolve a ticker name to exchange-suffixed format.

    Handles:
    - Chinese stock names: '贵州茅台' → '600519.SS', '腾讯控股' → '00700.HK'
    - Plain A-share codes: '600000' → '600000.SS'
    - Already suffixed codes: '600000.SS' → '600000.SS' (pass-through)

    Args:
        name: Stock name or ticker code

    Returns:
        Exchange-suffixed ticker string
    """
    name = name.strip()

    # Already suffixed — pass through
    if name.upper().endswith(('.SS', '.SZ', '.HK')):
        return name

    # Chinese name — look up
    if _is_chinese_name(name):
        _ensure_name_cache()
        if _name_cache and name in _name_cache:
            code = _name_cache[name]
            # Determine exchange from first digit
            if code.startswith('6'):
                return f"{code}.SS"
            else:
                return f"{code}.SZ"
        _ensure_hk_name_cache()
        if _hk_name_cache and name in _hk_name_cache:
            code = _hk_name_cache[name].zfill(5)
            return f"{code}.HK"
        raise ValueError(f"Cannot resolve Chinese name: {name!r}")

    # Plain numeric code — auto-suffix
    code, exchange = _normalize_akshare_ticker(name)
    suffix = {'shanghai': '.SS', 'shenzhen': '.SZ', 'hongkong': '.HK'}
    return f"{code}{suffix[exchange]}"
```

- [ ] **Step 4: Run name resolution unit tests**

Run: `pytest tests/test_akshare_data.py::TestResolveTickerName -v`
Expected: 3 tests PASS (the `_is_chinese_name` ones). The `resolve_ticker_name` tests that hit live AKShare need `@pytest.mark.integration`.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/akshare_data.py
git commit -m "feat: add ticker normalization and Chinese name resolution for AKShare"
```

---

### Task 4: Write tests for AKShare stock data and fundamentals

**Files:**
- Modify: `tests/test_akshare_data.py`

- [ ] **Step 1: Append data function tests**

Append to `tests/test_akshare_data.py`:

```python
from unittest.mock import patch, MagicMock
import pandas as pd
from tradingagents.dataflows.akshare_data import (
    get_akshare_stock_data,
    get_akshare_fundamentals,
    get_akshare_balance_sheet,
    get_akshare_income_statement,
    get_akshare_cashflow,
    get_akshare_news,
    get_akshare_global_news,
)


class TestAkshareStockData:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_returns_csv_for_a_share(self, mock_ak):
        df = pd.DataFrame({
            "日期": ["2024-01-15", "2024-01-16"],
            "开盘": [10.0, 10.5],
            "收盘": [10.3, 10.8],
            "最高": [10.4, 10.9],
            "最低": [9.9, 10.4],
            "成交量": [100000, 120000],
        })
        mock_ak.stock_zh_a_hist.return_value = df

        result = get_akshare_stock_data("600000", "2024-01-01", "2024-01-31")

        assert "Stock data for 600000" in result
        assert "2024-01-15" in result
        mock_ak.stock_zh_a_hist.assert_called_once()

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_empty_dataframe_returns_error(self, mock_ak):
        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()

        result = get_akshare_stock_data("000001", "2024-01-01", "2024-01-31")

        assert "No data found" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_hk_stock_uses_hk_endpoint(self, mock_ak):
        df = pd.DataFrame({
            "日期": ["2024-01-15"],
            "开盘": [300.0], "收盘": [305.0],
            "最高": [306.0], "最低": [299.0], "成交量": [50000],
        })
        mock_ak.stock_hk_hist.return_value = df

        result = get_akshare_stock_data("0700.HK", "2024-01-01", "2024-01-31")

        assert "Stock data for 00700" in result
        mock_ak.stock_hk_hist.assert_called_once()


class TestAkshareFundamentals:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_returns_fundamentals_text(self, mock_ak):
        mock_ak.stock_individual_info_em.return_value = pd.DataFrame(
            {"item": ["总市值", "市盈率"], "value": ["1000亿", "15.2"]}
        )

        result = get_akshare_fundamentals("600519", "2024-06-01")

        assert "总市值" in result
        assert "1000亿" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_empty_fundamentals_returns_error(self, mock_ak):
        mock_ak.stock_individual_info_em.return_value = pd.DataFrame()

        result = get_akshare_fundamentals("999999", "2024-06-01")

        assert "No fundamentals data" in result


class TestAkshareFinancialStatements:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_balance_sheet(self, mock_ak):
        mock_ak.stock_balance_sheet_by_report_em.return_value = pd.DataFrame(
            {"项目": ["总资产"], "2023-12-31": ["500亿"]}
        )
        result = get_akshare_balance_sheet("600519", "quarterly", "2024-06-01")
        assert "总资产" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_income_statement(self, mock_ak):
        mock_ak.stock_profit_sheet_by_report_em.return_value = pd.DataFrame(
            {"项目": ["营业收入"], "2023-12-31": ["100亿"]}
        )
        result = get_akshare_income_statement("600519", "quarterly", "2024-06-01")
        assert "营业收入" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_cashflow(self, mock_ak):
        mock_ak.stock_cash_flow_sheet_by_report_em.return_value = pd.DataFrame(
            {"项目": ["经营活动现金流"], "2023-12-31": ["20亿"]}
        )
        result = get_akshare_cashflow("600519", "quarterly", "2024-06-01")
        assert "经营活动现金流" in result


class TestAkshareNews:
    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_stock_news(self, mock_ak):
        mock_ak.stock_news_em.return_value = pd.DataFrame({
            "title": ["重大公告"],
            "content": ["内容摘要"],
            "发布时间": ["2024-06-01 10:00:00"],
        })
        result = get_akshare_news("600519", "2024-05-01", "2024-06-30")
        assert "重大公告" in result

    @pytest.mark.unit
    @patch("tradingagents.dataflows.akshare_data.ak")
    def test_global_news(self, mock_ak):
        mock_ak.news_economic_baidu.return_value = pd.DataFrame({
            "title": ["央行降准"], "content": [""], "date": ["2024-06-01"],
        })
        result = get_akshare_global_news("2024-06-01", 7, 10)
        assert "央行降准" in result
```

- [ ] **Step 2: Run to confirm failures**

Run: `pytest tests/test_akshare_data.py -v`
Expected: Tests that hit undefined functions FAIL with ImportError.

- [ ] **Step 3: Commit**

```bash
git add tests/test_akshare_data.py
git commit -m "test: add AKShare data function tests"
```

---

### Task 5: Implement AKShare stock data

**Files:**
- Modify: `tradingagents/dataflows/akshare_data.py`

- [ ] **Step 1: Add imports and get_akshare_stock_data**

Add at top of `akshare_data.py`:

```python
from datetime import datetime
import pandas as pd
```

Append to `akshare_data.py`:

```python
def get_akshare_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Get OHLCV stock data from AKShare.

    Args:
        symbol: Ticker symbol (e.g. '600000', '600000.SS', '0700.HK')
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV-formatted string with header
    """
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    code, exchange = _normalize_akshare_ticker(symbol)

    try:
        import akshare as ak

        if exchange == 'hongkong':
            df = ak.stock_hk_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
            )
            # Map HK columns to standard names
            col_map = {
                '日期': 'Date', '开盘': 'Open', '收盘': 'Close',
                '最高': 'High', '最低': 'Low', '成交量': 'Volume',
            }
        else:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
            )
            col_map = {
                '日期': 'Date', '开盘': 'Open', '收盘': 'Close',
                '最高': 'High', '最低': 'Low', '成交量': 'Volume',
            }
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"
    except Exception as e:
        return f"Error retrieving stock data for {symbol}: {str(e)}"

    if df is None or df.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Rename and select columns
    existing_cols = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=existing_cols)
    output_cols = [c for c in existing_cols.values() if c in df.columns]
    df = df[output_cols]

    # Round numerics
    for col in ['Open', 'High', 'Low', 'Close']:
        if col in df.columns:
            df[col] = df[col].round(2)

    csv_string = df.to_csv(index=False)
    header = (
        f"# Stock data for {code} from {start_date} to {end_date}\n"
        f"# Total records: {len(df)}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string
```

- [ ] **Step 2: Run stock data tests**

Run: `pytest tests/test_akshare_data.py::TestAkshareStockData -v`
Expected: 3 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tradingagents/dataflows/akshare_data.py
git commit -m "feat: implement AKShare OHLCV stock data"
```

---

### Task 6: Implement AKShare fundamentals and financial statements

**Files:**
- Modify: `tradingagents/dataflows/akshare_data.py`

- [ ] **Step 1: Add get_akshare_fundamentals, get_akshare_balance_sheet, get_akshare_income_statement, get_akshare_cashflow**

Append to `akshare_data.py`:

```python
def get_akshare_fundamentals(ticker: str, curr_date: str = None) -> str:
    """Get company fundamentals from AKShare (East Money).

    Args:
        ticker: Ticker symbol (e.g. '600519', '600519.SS')
        curr_date: Current date (used for header only)

    Returns:
        Formatted text of fundamental metrics
    """
    code, exchange = _normalize_akshare_ticker(ticker)

    if exchange == 'hongkong':
        return f"No fundamentals data available for HK stock '{code}' via AKShare"

    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=code)
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"

    if df is None or df.empty:
        return f"No fundamentals data found for symbol '{ticker}'"

    lines = []
    for _, row in df.iterrows():
        item = row.iloc[0] if len(row) > 0 else ""
        value = row.iloc[1] if len(row) > 1 else ""
        lines.append(f"{item}: {value}")

    header = (
        f"# Company Fundamentals for {ticker.upper()}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + "\n".join(lines)


def get_akshare_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Get balance sheet from AKShare."""
    code, exchange = _normalize_akshare_ticker(ticker)

    if exchange == 'hongkong':
        return f"No balance sheet data available for HK stock '{code}' via AKShare"

    try:
        import akshare as ak
        df = ak.stock_balance_sheet_by_report_em(symbol=code)
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"

    if df is None or df.empty:
        return f"No balance sheet data found for symbol '{ticker}'"

    csv_string = df.to_csv(index=False)
    header = (
        f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string


def get_akshare_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Get income statement from AKShare."""
    code, exchange = _normalize_akshare_ticker(ticker)

    if exchange == 'hongkong':
        return f"No income statement data available for HK stock '{code}' via AKShare"

    try:
        import akshare as ak
        df = ak.stock_profit_sheet_by_report_em(symbol=code)
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"

    if df is None or df.empty:
        return f"No income statement data found for symbol '{ticker}'"

    csv_string = df.to_csv(index=False)
    header = (
        f"# Income Statement data for {ticker.upper()} ({freq})\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string


def get_akshare_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Get cash flow statement from AKShare."""
    code, exchange = _normalize_akshare_ticker(ticker)

    if exchange == 'hongkong':
        return f"No cash flow data available for HK stock '{code}' via AKShare"

    try:
        import akshare as ak
        df = ak.stock_cash_flow_sheet_by_report_em(symbol=code)
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"

    if df is None or df.empty:
        return f"No cash flow data found for symbol '{ticker}'"

    csv_string = df.to_csv(index=False)
    header = (
        f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string
```

- [ ] **Step 2: Run fundamentals and statements tests**

Run: `pytest tests/test_akshare_data.py::TestAkshareFundamentals tests/test_akshare_data.py::TestAkshareFinancialStatements -v`
Expected: 5 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tradingagents/dataflows/akshare_data.py
git commit -m "feat: implement AKShare fundamentals and financial statements"
```

---

### Task 7: Implement AKShare news and indicators

**Files:**
- Modify: `tradingagents/dataflows/akshare_data.py`

- [ ] **Step 1: Add get_akshare_news, get_akshare_global_news**

Append to `akshare_data.py`:

```python
def get_akshare_news(ticker: str, start_date: str, end_date: str) -> str:
    """Get stock-specific news from AKShare (East Money).

    Args:
        ticker: Ticker symbol
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Markdown-formatted news list
    """
    code, exchange = _normalize_akshare_ticker(ticker)

    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"
    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"

    if df is None or df.empty:
        return f"No news found for {ticker}"

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    news_lines = []
    for _, row in df.iterrows():
        title = row.get("title", row.iloc[0] if len(row) > 0 else "")
        pub_time = row.get("发布时间", row.iloc[3] if len(row) > 3 else "")
        content = row.get("content", row.iloc[2] if len(row) > 2 else "")

        # Filter by date if publish time is available
        if pub_time:
            try:
                pub_str = str(pub_time)[:10]
                pub_dt = datetime.strptime(pub_str, "%Y-%m-%d")
                if not (start_dt <= pub_dt <= end_dt):
                    continue
            except (ValueError, TypeError):
                pass

        news_lines.append(f"### {title}")
        if content:
            news_lines.append(str(content)[:500])
        news_lines.append("")

    if not news_lines:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return f"## {ticker} News, from {start_date} to {end_date}:\n\n" + "\n".join(news_lines)


def get_akshare_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Get macro/economic news relevant to Chinese markets.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Days to look back
        limit: Max articles

    Returns:
        Markdown-formatted news list
    """
    try:
        import akshare as ak
        df = ak.news_economic_baidu()
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"
    except Exception as e:
        return f"Error fetching global news: {str(e)}"

    if df is None or df.empty:
        return f"No global news found for {curr_date}"

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    from dateutil.relativedelta import relativedelta
    start_dt = curr_dt - relativedelta(days=look_back_days)

    news_lines = []
    count = 0
    for _, row in df.iterrows():
        if count >= limit:
            break
        title = row.get("title", row.iloc[0] if len(row) > 0 else "")
        date_str = str(row.get("date", row.iloc[2] if len(row) > 2 else ""))[:10]
        content = row.get("content", row.iloc[1] if len(row) > 1 else "")

        # Date filter
        try:
            pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
            if pub_dt < start_dt or pub_dt > curr_dt:
                continue
        except (ValueError, TypeError):
            pass

        news_lines.append(f"### {title}")
        if content:
            news_lines.append(str(content)[:500])
        news_lines.append("")
        count += 1

    if not news_lines:
        return f"No global news found for {curr_date}"

    start_str = start_dt.strftime("%Y-%m-%d")
    return f"## China Market News, from {start_str} to {curr_date}:\n\n" + "\n".join(news_lines)
```

- [ ] **Step 2: Run news tests**

Run: `pytest tests/test_akshare_data.py::TestAkshareNews -v`
Expected: 2 tests PASS.

- [ ] **Step 3: Implement get_akshare_indicators**

Append to `akshare_data.py`:

```python
def get_akshare_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    """Get technical indicator values using AKShare OHLCV + stockstats.

    Fetches historical data from AKShare, converts to stockstats-compatible
    DataFrame, then calculates the requested indicator for the date range.
    """
    try:
        import akshare as ak
    except ImportError:
        return "Error: akshare package not installed. Run: pip install akshare"

    from .stockstats_utils import StockstatsUtils
    from stockstats import wrap
    from dateutil.relativedelta import relativedelta

    code, exchange = _normalize_akshare_ticker(symbol)

    # Fetch long history for accurate indicator calculation
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days + 365)

    start_str = start_dt.strftime("%Y%m%d")
    end_str = curr_dt.strftime("%Y%m%d")

    try:
        if exchange == 'hongkong':
            df = ak.stock_hk_hist(symbol=code, period="daily",
                                  start_date=start_str, end_date=end_str, adjust="qfq")
        else:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=start_str, end_date=end_str, adjust="qfq")
    except Exception as e:
        return f"Error fetching data for indicator '{indicator}': {str(e)}"

    if df is None or df.empty:
        return ""  # empty string signals no data to the caller

    # Convert to stockstats-compatible format
    col_map = {
        '日期': 'Date', '开盘': 'Open', '收盘': 'Close',
        '最高': 'High', '最低': 'Low', '成交量': 'Volume',
    }
    existing = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=existing)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    price_cols = ['Open', 'High', 'Low', 'Close']
    for c in price_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['Close'])
    df = df[df['Date'] <= pd.to_datetime(curr_date)]

    # Wrap with stockstats and calculate indicator
    wrapped = wrap(df)
    wrapped["Date"] = wrapped["Date"].dt.strftime("%Y-%m-%d")
    wrapped[indicator]

    # Build the result string for the date window
    result_dt = curr_dt
    lines = []
    while result_dt >= curr_dt - relativedelta(days=look_back_days):
        date_str = result_dt.strftime("%Y-%m-%d")
        matching = wrapped[wrapped["Date"].str.startswith(date_str)]
        if not matching.empty:
            val = matching[indicator].values[0]
            lines.append(f"{date_str}: {val if not pd.isna(val) else 'N/A: Not a trading day (weekend or holiday)'}")
        else:
            lines.append(f"{date_str}: N/A: Not a trading day (weekend or holiday)")
        result_dt -= relativedelta(days=1)

    result_str = f"## {indicator} values from {(curr_dt - relativedelta(days=look_back_days)).strftime('%Y-%m-%d')} to {curr_date}:\n\n"
    result_str += "\n".join(lines)
    result_str += f"\n\n{indicator}: Technical indicator calculated from AKShare OHLCV data."
    return result_str
```

- [ ] **Step 4: Commit**

```bash
git add tradingagents/dataflows/akshare_data.py
git commit -m "feat: implement AKShare news, global news, and indicators"
```

---

### Task 8: Register AKShare vendor in interface.py

**Files:**
- Modify: `tradingagents/dataflows/interface.py`

- [ ] **Step 1: Add import of AKShare functions**

Add to the imports section in `interface.py`:

```python
from .akshare_data import (
    get_akshare_stock_data,
    get_akshare_indicators,
    get_akshare_fundamentals,
    get_akshare_balance_sheet,
    get_akshare_cashflow,
    get_akshare_income_statement,
    get_akshare_news,
    get_akshare_global_news,
    get_akshare_insider_transactions,
)
```

- [ ] **Step 2: Add 'akshare' to VENDOR_LIST**

Change `VENDOR_LIST` in `interface.py`:

```python
VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    "akshare",
]
```

- [ ] **Step 3: Add AKShare entries to VENDOR_METHODS**

Add `"akshare": ...` entries to each method in `VENDOR_METHODS`. Example for `get_stock_data`:

```python
"get_stock_data": {
    "alpha_vantage": get_alpha_vantage_stock,
    "yfinance": get_YFin_data_online,
    "akshare": get_akshare_stock_data,
},
```

Do the same for all 9 methods:
- `get_stock_data` → `get_akshare_stock_data`
- `get_indicators` → `get_akshare_indicators`
- `get_fundamentals` → `get_akshare_fundamentals`
- `get_balance_sheet` → `get_akshare_balance_sheet`
- `get_cashflow` → `get_akshare_cashflow`
- `get_income_statement` → `get_akshare_income_statement`
- `get_news` → `get_akshare_news`
- `get_global_news` → `get_akshare_global_news`
- `get_insider_transactions` → `get_akshare_insider_transactions`

- [ ] **Step 4: Add get_akshare_insider_transactions stub to akshare_data.py**

Append to `akshare_data.py`:

```python
def get_akshare_insider_transactions(ticker: str) -> str:
    """Insider transactions are not available via AKShare."""
    return f"No insider transactions data available for '{ticker}' via AKShare"
```

- [ ] **Step 5: Run all tests to verify wiring**

Run: `pytest tests/test_akshare_data.py -v`
Expected: All 13 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/interface.py tradingagents/dataflows/akshare_data.py
git commit -m "feat: register AKShare as third data vendor in interface"
```

---

### Task 9: Update config, agent utils, and CLI

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `cli/main.py`

- [ ] **Step 1: Add akshare to vendor comments in default_config.py**

Update the `"data_vendors"` comments in `default_config.py`:

```python
"data_vendors": {
    "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance, akshare
    "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance, akshare
    "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance, akshare
    "news_data": "yfinance",             # Options: alpha_vantage, yfinance, akshare
},
```

- [ ] **Step 2: Update build_instrument_context in agent_utils.py**

Change the return statement in `build_instrument_context`:

```python
def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.SS`, `.SZ`, `.TO`, `.L`, `.HK`, `.T`)."
    )
```

- [ ] **Step 3: Update CLI ticker prompt in cli/main.py**

Change line in `create_question_box` call within `get_user_selections`:

```python
"Enter the exact ticker symbol to analyze, including exchange suffix when needed "
"(examples: SPY, 600519.SS, 000001.SZ, CNC.TO, 7203.T, 0700.HK, 贵州茅台)",
```

- [ ] **Step 4: Add name resolution in CLI get_ticker**

Wrap the existing `get_ticker()` call with name resolution. Update `get_ticker()` in `cli/main.py`:

```python
def get_ticker():
    """Get ticker symbol from user input, resolving Chinese names."""
    raw = typer.prompt("", default="SPY")
    from tradingagents.dataflows.akshare_data import _is_chinese_name, resolve_ticker_name
    if _is_chinese_name(raw):
        try:
            resolved = resolve_ticker_name(raw)
            console.print(f"[green]Resolved: {raw} → {resolved}[/green]")
            confirmed = typer.prompt("Confirm?", default="Y").strip().upper()
            if confirmed in ("Y", "YES", ""):
                return resolved
            else:
                console.print("[yellow]Please re-enter the ticker.[/yellow]")
                return get_ticker()
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return get_ticker()
    return raw
```

- [ ] **Step 5: Add ticker resolution in TradingAgentsGraph.propagate**

Modify `propagate()` in `tradingagents/graph/trading_graph.py` to resolve names at entry. Add at the top of the method body (after `self.ticker = company_name`):

```python
def propagate(self, company_name, trade_date):
    # Resolve Chinese stock names before running the pipeline
    from tradingagents.dataflows.akshare_data import _is_chinese_name, resolve_ticker_name
    if _is_chinese_name(company_name):
        try:
            company_name = resolve_ticker_name(company_name)
            logger.info("Resolved Chinese name to ticker: %s", company_name)
        except ValueError:
            logger.warning("Could not resolve Chinese name: %s", company_name)

    self.ticker = company_name
    ...  # rest of method unchanged
```

- [ ] **Step 6: Verify existing tests still pass**

Run: `pytest tests/ -m unit -v`
Expected: All existing unit tests PASS.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/default_config.py tradingagents/agents/utils/agent_utils.py cli/main.py tradingagents/graph/trading_graph.py
git commit -m "feat: wire AKShare into config, CLI, and graph entry points"
```

---

### Task 10: Integration test and final verification

**Files:**
- Modify: `tests/test_akshare_data.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_akshare_data.py`:

```python
class TestAkshareIntegration:
    @pytest.mark.integration
    def test_resolve_chinese_name_live(self):
        """Live test: resolve 贵州茅台 to 600519.SS."""
        result = resolve_ticker_name("贵州茅台")
        assert result == "600519.SS"

    @pytest.mark.integration
    def test_stock_data_live(self):
        """Live test: fetch actual OHLCV for Moutai."""
        result = get_akshare_stock_data("600519", "2024-06-01", "2024-06-07")
        assert "Stock data" in result
        assert "600519" in result
        assert len(result.split("\n")) > 3  # header + data rows

    @pytest.mark.integration
    def test_fundamentals_live(self):
        """Live test: fetch fundamentals for Moutai."""
        result = get_akshare_fundamentals("600519")
        assert "总市值" in result or "Company Fundamentals" in result
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_akshare_data.py -m integration -v`
Expected: 3 integration tests PASS with live AKShare data.

**Note:** These tests require internet access and AKShare installed. If any upstream API changes, update the test accordingly.

- [ ] **Step 3: Run full unit test suite**

Run: `pytest tests/ -m unit -v`
Expected: All unit tests PASS, including existing tests and new AKShare tests.

- [ ] **Step 4: Manual smoke test**

Run a quick CLI test (requires API keys):
```bash
python -c "
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config['data_vendors'] = {
    'core_stock_apis': 'akshare',
    'technical_indicators': 'akshare',
    'fundamental_data': 'akshare',
    'news_data': 'akshare',
}
ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate('贵州茅台', '2024-05-31')
print(decision)
"
```

Expected: The pipeline completes without errors. Decision output printed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_akshare_data.py
git commit -m "test: add AKShare integration tests"
```
