/**
 * @module: TradingAgents
 * @file: 2026-09-27-credit-debenture-mode.md
 * @description: Implementation plan for Brazilian debenture credit analysis mode
 * @author: Maíra Pontin
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */

# Brazilian Debenture Credit Analysis Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a credit/debenture analysis mode to TradingAgents for Brazilian corporate bonds (debêntures) using ANBIMA free data, extending the existing stock and crypto asset modes with credit-specific analysts, data sources, and decision logic.

**Architecture:** Extend `AssetType` enum with `CREDIT` (mirroring the crypto mode pattern), add two credit-specific analysts (credit fundamentals and credit news), integrate ANBIMA as a data vendor for yield curve and credit spreads, adapt the return loop for credit total return calculation (yield change + accrued interest), and extend the benchmark map for Brazilian bonds (.SA suffix).

**Tech Stack:** Python 3.11+, LangGraph, LangChain, yfinance (for Brazilian equities), ANBIMA API (free tier), CVM filings (free), pytest

**Spec:** `docs/superpowers/specs/2026-09-27-credit-debenture-mode-design.md`

## Global Constraints

- Python 3.11+ (match existing codebase)
- Follow existing code patterns (crypto mode touched 6 files; credit mode will touch ~15)
- ANBIMA free tier only (no paid data sources in v1)
- 30-day holding period for credit (vs 5-day for equity)
- Benchmark: IMA-B index or ^IRFM for Brazilian bonds
- Decision scale: Investment Grade / Speculative Grade / Default (not Buy/Sell)
- All new code must have >80% unit test coverage
- Governance headers required in all new/modified Python files

---

## File Structure

### Modify Existing Files

1. **`cli/models.py`** — Add `CREDIT = "credit"` to `AssetType` enum; add `CREDIT_FUNDAMENTALS` and `CREDIT_NEWS` to `AnalystType` enum
2. **`cli/utils.py`** — Extend `detect_asset_type` to recognize debenture CUSIP patterns; extend `filter_analysts_for_asset_type` to drop market analyst for credit mode
3. **`tradingagents/default_config.py`** — Add `.SA: "^IRFM"` to `benchmark_map`; add `credit_holding_period_days: 30`
4. **`tradingagents/agents/utils/agent_utils.py`** — Add credit-specific prompt branches for instrument context
5. **`tradingagents/graph/trading_graph.py`** — Add `_fetch_credit_returns` method; add conditional logic to call it for credit mode
6. **`tradingagents/dataflows/interface.py`** — Add `anbima` to `VENDOR_LIST`; add `credit_data` category to `TOOLS_CATEGORIES`

### Create New Files

1. **`tradingagents/agents/analysts/credit_fundamentals_analyst.py`** — Credit fundamentals analyst agent (leverage, coverage, cash flow, recovery rate)
2. **`tradingagents/agents/analysts/credit_news_analyst.py`** — Credit news analyst agent (issuer news, rating actions, covenant amendments)
3. **`tradingagents/dataflows/credit/__init__.py`** — Credit data vendor module
4. **`tradingagents/dataflows/credit/anbima.py`** — ANBIMA API client (yield curve, credit spreads, indicative quotes, IMA-B index)
5. **`tradingagents/dataflows/credit/cvm.py`** — CVM filing parser (financial statements, material facts)
6. **`tests/test_credit_mode.py`** — Integration tests for credit mode

---

## Task 1: Extend AssetType and AnalystType Enums

**Files:**
- Modify: `cli/models.py:13-15`

**Interfaces:**
- Consumes: None (foundational change)
- Produces: `AssetType.CREDIT`, `AnalystType.CREDIT_FUNDAMENTALS`, `AnalystType.CREDIT_NEWS`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_models.py
 * @description: Tests for CLI models (AssetType, AnalystType enums)
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from cli.models import AssetType, AnalystType


def test_asset_type_has_credit():
    """AssetType enum should include CREDIT."""
    assert hasattr(AssetType, "CREDIT")
    assert AssetType.CREDIT.value == "credit"


def test_analyst_type_has_credit_fundamentals():
    """AnalystType enum should include CREDIT_FUNDAMENTALS."""
    assert hasattr(AnalystType, "CREDIT_FUNDAMENTALS")
    assert AnalystType.CREDIT_FUNDAMENTALS.value == "credit_fundamentals"


def test_analyst_type_has_credit_news():
    """AnalystType enum should include CREDIT_NEWS."""
    assert hasattr(AnalystType, "CREDIT_NEWS")
    assert AnalystType.CREDIT_NEWS.value == "credit_news"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with "AttributeError: AssetType has no attribute 'CREDIT'"

- [ ] **Step 3: Write minimal implementation**

Edit `cli/models.py`:

```python
from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    # Wire value stays "social" for saved-config and string-keyed-caller
    # back-compat; the user-facing label is "Sentiment Analyst".
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    CREDIT_FUNDAMENTALS = "credit_fundamentals"  # NEW
    CREDIT_NEWS = "credit_news"  # NEW


class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
    CREDIT = "credit"  # NEW
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add cli/models.py tests/test_models.py
git commit -m "feat(credit): add CREDIT to AssetType and credit analysts to AnalystType enums

Extends the enum to support Brazilian debenture credit analysis mode.
Mirrors the crypto mode pattern for asset type routing."
```

---

## Task 2: Extend detect_asset_type for Credit

**Files:**
- Modify: `cli/utils.py:81-87`
- Test: `tests/test_utils.py`

**Interfaces:**
- Consumes: `AssetType.CREDIT` from Task 1
- Produces: `detect_asset_type(ticker: str) -> AssetType` that recognizes debenture CUSIP patterns

- [ ] **Step 1: Write the failing test**

Create `tests/test_utils.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_utils.py
 * @description: Tests for CLI utilities (detect_asset_type, filter_analysts)
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from cli.models import AssetType
from cli.utils import detect_asset_type


def test_detect_asset_type_credit_cusip():
    """Debenture CUSIP pattern (4 letters + 2 digits) should be CREDIT."""
    assert detect_asset_type("PETR41") == AssetType.CREDIT
    assert detect_asset_type("VALE32") == AssetType.CREDIT
    assert detect_asset_type("OIBR33") == AssetType.CREDIT


def test_detect_asset_type_brazilian_equity():
    """Brazilian equity (.SA suffix) should be STOCK."""
    assert detect_asset_type("PETR4.SA") == AssetType.STOCK
    assert detect_asset_type("VALE3.SA") == AssetType.STOCK


def test_detect_asset_type_crypto():
    """Crypto suffixes should be CRYPTO."""
    assert detect_asset_type("BTC-USD") == AssetType.CRYPTO
    assert detect_asset_type("ETH-USD") == AssetType.CRYPTO


def test_detect_asset_type_us_equity():
    """US equity (no suffix) should be STOCK."""
    assert detect_asset_type("AAPL") == AssetType.STOCK
    assert detect_asset_type("MSFT") == AssetType.STOCK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_utils.py::test_detect_asset_type_credit_cusip -v`
Expected: FAIL with "AssertionError: assert <AssetType.STOCK: 'stock'> == <AssetType.CREDIT: 'credit'>"

- [ ] **Step 3: Write minimal implementation**

Edit `cli/utils.py:81-87`:

```python
import re

# Debenture CUSIP pattern: 4 letters + 2 digits (e.g., PETR41, VALE32)
_DEBENTURE_CUSIP_PATTERN = re.compile(r"^[A-Z]{4}\d{2}$")


def detect_asset_type(ticker: str) -> AssetType:
    """Classify on the canonical symbol so e.g. BTCUSD and BTC-USDT both read as
    crypto (#981/#982), matching what the data path will actually fetch.
    
    Credit mode: debenture CUSIP pattern (4 letters + 2 digits) -> CREDIT.
    """
    canonical = normalize_ticker_symbol(ticker)
    
    # Credit: debenture CUSIP pattern (e.g., PETR41, VALE32)
    if _DEBENTURE_CUSIP_PATTERN.match(canonical):
        return AssetType.CREDIT
    
    # Crypto: -USD, -USDT, -USDC, etc.
    if canonical.endswith(CRYPTO_SUFFIXES):
        return AssetType.CRYPTO
    
    # Default: stock
    return AssetType.STOCK
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_utils.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add cli/utils.py tests/test_utils.py
git commit -m "feat(credit): extend detect_asset_type for debenture CUSIP pattern

Recognizes Brazilian debenture CUSIP pattern (4 letters + 2 digits, e.g., PETR41)
as CREDIT asset type. Brazilian equity (.SA suffix) remains STOCK."
```

---

## Task 3: Extend filter_analysts_for_asset_type for Credit

**Files:**
- Modify: `cli/utils.py:90-98`
- Test: `tests/test_utils.py` (append)

**Interfaces:**
- Consumes: `AssetType.CREDIT`, `AnalystType.CREDIT_FUNDAMENTALS`, `AnalystType.CREDIT_NEWS` from Task 1
- Produces: `filter_analysts_for_asset_type` that drops market/sentiment analysts for credit mode

- [ ] **Step 1: Write the failing test**

Append to `tests/test_utils.py`:

```python
from cli.models import AnalystType
from cli.utils import filter_analysts_for_asset_type


def test_filter_analysts_credit_mode():
    """Credit mode should keep only credit fundamentals and credit news."""
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
        AnalystType.CREDIT_FUNDAMENTALS,
        AnalystType.CREDIT_NEWS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, AssetType.CREDIT)
    assert filtered == [AnalystType.CREDIT_FUNDAMENTALS, AnalystType.CREDIT_NEWS]


def test_filter_analysts_crypto_mode():
    """Crypto mode should drop fundamentals (existing behavior)."""
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, AssetType.CRYPTO)
    assert AnalystType.FUNDAMENTALS not in filtered
    assert AnalystType.MARKET in filtered


def test_filter_analysts_stock_mode():
    """Stock mode should keep all analysts (existing behavior)."""
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, AssetType.STOCK)
    assert filtered == all_analysts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_utils.py::test_filter_analysts_credit_mode -v`
Expected: FAIL with "AssertionError: assert [...] == [AnalystType.CREDIT_FUNDAMENTALS, AnalystType.CREDIT_NEWS]"

- [ ] **Step 3: Write minimal implementation**

Edit `cli/utils.py:90-98`:

```python
def filter_analysts_for_asset_type(
    analysts: list[AnalystType], asset_type: AssetType
) -> list[AnalystType]:
    """Filter analysts based on asset type.
    
    Credit mode: keep only CREDIT_FUNDAMENTALS and CREDIT_NEWS.
    Crypto mode: drop FUNDAMENTALS (no company fundamentals for crypto).
    Stock mode: keep all.
    """
    if asset_type == AssetType.CREDIT:
        return [
            analyst
            for analyst in analysts
            if analyst in (AnalystType.CREDIT_FUNDAMENTALS, AnalystType.CREDIT_NEWS)
        ]
    
    if asset_type == AssetType.CRYPTO:
        return [
            analyst
            for analyst in analysts
            if analyst != AnalystType.FUNDAMENTALS
        ]
    
    return analysts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_utils.py -v`
Expected: PASS (7 tests total)

- [ ] **Step 5: Commit**

```bash
git add cli/utils.py tests/test_utils.py
git commit -m "feat(credit): extend filter_analysts_for_asset_type for credit mode

Credit mode keeps only CREDIT_FUNDAMENTALS and CREDIT_NEWS analysts.
No retail sentiment analysis for institutional debenture markets."
```

---

## Task 4: Create ANBIMA Data Vendor

**Files:**
- Create: `tradingagents/dataflows/credit/__init__.py`
- Create: `tradingagents/dataflows/credit/anbima.py`
- Test: `tests/test_anbima.py`

**Interfaces:**
- Consumes: None (new vendor)
- Produces: `get_yield_curve()`, `get_credit_spreads()`, `get_debenture_quote()`, `get_ima_b_index()`

- [ ] **Step 1: Write the failing test**

Create `tests/test_anbima.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_anbima.py
 * @description: Tests for ANBIMA data vendor
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import patch, MagicMock
from tradingagents.dataflows.credit.anbima import (
    get_yield_curve,
    get_credit_spreads,
    get_debenture_quote,
    get_ima_b_index,
)


def test_get_yield_curve_returns_dict():
    """get_yield_curve should return dict[maturity_years] = rate_percent."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "yield_curve": {1: 10.5, 2: 11.0, 3: 11.5, 5: 12.0}
        }
        result = get_yield_curve()
        assert isinstance(result, dict)
        assert 1 in result
        assert result[1] == 10.5


def test_get_credit_spreads_returns_dict():
    """get_credit_spreads should return dict[maturity_years] = spread_bps."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "credit_spreads": {"PETR": {1: 150, 2: 160, 3: 170}}
        }
        result = get_credit_spreads("PETR")
        assert isinstance(result, dict)
        assert 1 in result
        assert result[1] == 150


def test_get_debenture_quote_returns_dict():
    """get_debenture_quote should return dict with price, yield, maturity, coupon, face_value."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "quotes": {"PETR41": {"price": 95.5, "yield": 12.5, "maturity": 3, "coupon": 10.0, "face_value": 1000}}
        }
        result = get_debenture_quote("PETR41")
        assert isinstance(result, dict)
        assert "price" in result
        assert result["price"] == 95.5


def test_get_ima_b_index_returns_list():
    """get_ima_b_index should return list of (date, index_value) tuples."""
    with patch("tradingagents.dataflows.credit.anbima._fetch_anbima_data") as mock_fetch:
        mock_fetch.return_value = {
            "ima_b": [("2026-09-01", 1000.0), ("2026-09-02", 1005.0)]
        }
        result = get_ima_b_index()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == ("2026-09-01", 1000.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_anbima.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'tradingagents.dataflows.credit'"

- [ ] **Step 3: Write minimal implementation**

Create `tradingagents/dataflows/credit/__init__.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: __init__.py
 * @description: Credit data vendor module (ANBIMA, CVM)
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

from .anbima import (
    get_yield_curve,
    get_credit_spreads,
    get_debenture_quote,
    get_ima_b_index,
)

__all__ = [
    "get_yield_curve",
    "get_credit_spreads",
    "get_debenture_quote",
    "get_ima_b_index",
]
```

Create `tradingagents/dataflows/credit/anbima.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: anbima.py
 * @description: ANBIMA data vendor (yield curve, credit spreads, indicative quotes, IMA-B index)
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def _fetch_anbima_data() -> dict:
    """Fetch data from ANBIMA API or website.
    
    TODO: Implement actual ANBIMA API client or web scraper.
    For now, return mock data for testing.
    
    ANBIMA provides:
    - Yield curve (zero rates by maturity)
    - Credit spreads vs CDI
    - Indicative quotes for benchmark debentures
    - IMA-B index daily values
    """
    # Mock implementation for testing
    return {
        "yield_curve": {1: 10.5, 2: 11.0, 3: 11.5, 5: 12.0, 10: 13.0},
        "credit_spreads": {
            "PETR": {1: 150, 2: 160, 3: 170, 5: 180},
            "VALE": {1: 120, 2: 130, 3: 140, 5: 150},
        },
        "quotes": {
            "PETR41": {"price": 95.5, "yield": 12.5, "maturity": 3, "coupon": 10.0, "face_value": 1000},
            "VALE32": {"price": 98.0, "yield": 11.5, "maturity": 2, "coupon": 9.5, "face_value": 1000},
        },
        "ima_b": [
            ("2026-09-01", 1000.0),
            ("2026-09-02", 1005.0),
            ("2026-09-03", 1010.0),
        ],
    }


def get_yield_curve() -> Dict[int, float]:
    """Fetch ANBIMA yield curve (zero rates by maturity).
    
    Returns:
        dict[maturity_years] = rate_percent
        Example: {1: 10.5, 2: 11.0, 3: 11.5}
    """
    data = _fetch_anbima_data()
    return data.get("yield_curve", {})


def get_credit_spreads(issuer: str) -> Dict[int, float]:
    """Fetch credit spread vs CDI for issuer's debentures.
    
    Args:
        issuer: Issuer code (e.g., "PETR", "VALE")
    
    Returns:
        dict[maturity_years] = spread_bps
        Example: {1: 150, 2: 160, 3: 170}
    """
    data = _fetch_anbima_data()
    spreads = data.get("credit_spreads", {})
    return spreads.get(issuer, {})


def get_debenture_quote(cusip: str) -> dict:
    """Fetch indicative quote for specific debenture.
    
    Args:
        cusip: Debenture CUSIP (e.g., "PETR41")
    
    Returns:
        dict with keys: price, yield, maturity, coupon, face_value
        Example: {"price": 95.5, "yield": 12.5, "maturity": 3, "coupon": 10.0, "face_value": 1000}
    """
    data = _fetch_anbima_data()
    quotes = data.get("quotes", {})
    return quotes.get(cusip, {})


def get_ima_b_index() -> List[Tuple[str, float]]:
    """Fetch IMA-B index daily values.
    
    Returns:
        list of (date, index_value) tuples
        Example: [("2026-09-01", 1000.0), ("2026-09-02", 1005.0)]
    """
    data = _fetch_anbima_data()
    return data.get("ima_b", [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_anbima.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/credit/__init__.py tradingagents/dataflows/credit/anbima.py tests/test_anbima.py
git commit -m "feat(credit): add ANBIMA data vendor for yield curve, spreads, quotes, IMA-B index

Implements mock ANBIMA API client for Brazilian debenture data.
Provides yield curve, credit spreads vs CDI, indicative quotes, and IMA-B index.
TODO: Replace mock with actual ANBIMA API client or web scraper."
```

---

## Task 5: Register ANBIMA Vendor in interface.py

**Files:**
- Modify: `tradingagents/dataflows/interface.py:85-91`
- Test: `tests/test_interface.py`

**Interfaces:**
- Consumes: ANBIMA vendor functions from Task 4
- Produces: `anbima` in `VENDOR_LIST`, `credit_data` in `TOOLS_CATEGORIES`

- [ ] **Step 1: Write the failing test**

Create `tests/test_interface.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_interface.py
 * @description: Tests for data vendor interface
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from tradingagents.dataflows.interface import VENDOR_LIST, TOOLS_CATEGORIES


def test_anbima_in_vendor_list():
    """ANBIMA should be in VENDOR_LIST."""
    assert "anbima" in VENDOR_LIST


def test_credit_data_in_tools_categories():
    """credit_data should be in TOOLS_CATEGORIES."""
    assert "credit_data" in TOOLS_CATEGORIES
    assert "tools" in TOOLS_CATEGORIES["credit_data"]
    assert "get_yield_curve" in TOOLS_CATEGORIES["credit_data"]["tools"]
    assert "get_credit_spreads" in TOOLS_CATEGORIES["credit_data"]["tools"]
    assert "get_debenture_quote" in TOOLS_CATEGORIES["credit_data"]["tools"]
    assert "get_ima_b_index" in TOOLS_CATEGORIES["credit_data"]["tools"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_interface.py -v`
Expected: FAIL with "AssertionError: assert 'anbima' in [...]"

- [ ] **Step 3: Write minimal implementation**

Edit `tradingagents/dataflows/interface.py:85-91`:

```python
VENDOR_LIST = [
    "yfinance",
    "sec_edgar",
    "fred",
    "polymarket",
    "alpha_vantage",
    "anbima",  # NEW: Brazilian debenture data
]
```

Edit `tradingagents/dataflows/interface.py:41-83` (add new category):

```python
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "macro_data": {
        "description": "Macroeconomic indicators (rates, inflation, labor, growth)",
        "tools": [
            "get_macro_indicators",
        ]
    },
    "prediction_markets": {
        "description": "Market-implied probabilities for forward-looking events",
        "tools": [
            "get_prediction_markets",
        ]
    },
    "credit_data": {  # NEW
        "description": "Brazilian debenture credit data (yield curve, spreads, quotes)",
        "tools": [
            "get_yield_curve",
            "get_credit_spreads",
            "get_debenture_quote",
            "get_ima_b_index",
        ]
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_interface.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/interface.py tests/test_interface.py
git commit -m "feat(credit): register ANBIMA vendor in data interface

Adds 'anbima' to VENDOR_LIST and 'credit_data' category to TOOLS_CATEGORIES.
Credit data includes yield curve, credit spreads, debenture quotes, and IMA-B index."
```

---

## Task 6: Create Credit Fundamentals Analyst

**Files:**
- Create: `tradingagents/agents/analysts/credit_fundamentals_analyst.py`
- Test: `tests/test_credit_fundamentals_analyst.py`

**Interfaces:**
- Consumes: ANBIMA vendor functions from Task 4, CVM data (via yfinance for Brazilian equities)
- Produces: `create_credit_fundamentals_analyst(llm)` function

- [ ] **Step 1: Write the failing test**

Create `tests/test_credit_fundamentals_analyst.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_credit_fundamentals_analyst.py
 * @description: Tests for credit fundamentals analyst
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import MagicMock
from tradingagents.agents.analysts.credit_fundamentals_analyst import create_credit_fundamentals_analyst


def test_create_credit_fundamentals_analyst_returns_function():
    """create_credit_fundamentals_analyst should return a callable node function."""
    llm = MagicMock()
    node = create_credit_fundamentals_analyst(llm)
    assert callable(node)


def test_credit_fundamentals_analyst_invokes_llm():
    """Credit fundamentals analyst should invoke LLM with tools."""
    llm = MagicMock()
    llm.bind_tools.return_value = MagicMock()
    llm.bind_tools.return_value.invoke.return_value = MagicMock(content="Test report", tool_calls=[])
    
    node = create_credit_fundamentals_analyst(llm)
    state = {
        "trade_date": "2026-09-27",
        "messages": [],
        "company_of_interest": "PETR4",
    }
    
    result = node(state)
    
    assert "messages" in result
    assert "fundamentals_report" in result
    assert llm.bind_tools.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_credit_fundamentals_analyst.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'tradingagents.agents.analysts.credit_fundamentals_analyst'"

- [ ] **Step 3: Write minimal implementation**

Create `tradingagents/agents/analysts/credit_fundamentals_analyst.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: credit_fundamentals_analyst.py
 * @description: Credit fundamentals analyst agent (leverage, coverage, cash flow, recovery rate)
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.dataflows.credit.anbima import (
    get_yield_curve,
    get_credit_spreads,
)


def create_credit_fundamentals_analyst(llm):
    """Create a credit fundamentals analyst node.
    
    Analyzes creditworthiness using leverage ratios, interest coverage,
    cash flow adequacy, asset quality, and recovery rate estimation.
    """
    def credit_fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_yield_curve,
            get_credit_spreads,
        ]

        system_message = (
            "You are a credit analyst specializing in Brazilian corporate bonds (debêntures). "
            "Analyze the creditworthiness of the issuer using the following framework:\n\n"
            "1. **Leverage ratios:** Net Debt/EBITDA, Debt/Equity, Debt/Assets\n"
            "2. **Interest coverage:** EBITDA/Interest Expense, EBIT/Interest Expense\n"
            "3. **Cash flow adequacy:** FCF/Debt, Operating Cash Flow/Debt, FCF/Interest\n"
            "4. **Asset quality:** Tangible asset coverage, recovery rate estimation\n"
            "5. **Profitability context:** EBITDA margin, ROA, ROE (for debt service capacity)\n\n"
            "Focus on **downside protection** and **default risk**, not upside potential. "
            "Provide a credit assessment: Investment Grade (BBB- or higher) or "
            "Speculative Grade (BB+ or lower) or Default risk.\n\n"
            "Use the available tools: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, "
            "`get_income_statement` for financial data; `get_yield_curve` and `get_credit_spreads` "
            "for market data."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other analysts."
                    " Use the provided tools to analyze creditworthiness."
                    " If you are unable to fully answer, that's OK; another analyst with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Report what your tools support; another agent decides the credit decision."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return credit_fundamentals_analyst_node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_credit_fundamentals_analyst.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/credit_fundamentals_analyst.py tests/test_credit_fundamentals_analyst.py
git commit -m "feat(credit): add credit fundamentals analyst agent

Analyzes creditworthiness using leverage ratios, interest coverage, cash flow adequacy,
asset quality, and recovery rate estimation. Uses ANBIMA yield curve and credit spreads.
Focus on downside protection and default risk, not upside potential."
```

---

## Task 7: Create Credit News Analyst

**Files:**
- Create: `tradingagents/agents/analysts/credit_news_analyst.py`
- Test: `tests/test_credit_news_analyst.py`

**Interfaces:**
- Consumes: News tools (get_news from existing vendor)
- Produces: `create_credit_news_analyst(llm)` function

- [ ] **Step 1: Write the failing test**

Create `tests/test_credit_news_analyst.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_credit_news_analyst.py
 * @description: Tests for credit news analyst
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import MagicMock
from tradingagents.agents.analysts.credit_news_analyst import create_credit_news_analyst


def test_create_credit_news_analyst_returns_function():
    """create_credit_news_analyst should return a callable node function."""
    llm = MagicMock()
    node = create_credit_news_analyst(llm)
    assert callable(node)


def test_credit_news_analyst_invokes_llm():
    """Credit news analyst should invoke LLM with tools."""
    llm = MagicMock()
    llm.bind_tools.return_value = MagicMock()
    llm.bind_tools.return_value.invoke.return_value = MagicMock(content="Test news report", tool_calls=[])
    
    node = create_credit_news_analyst(llm)
    state = {
        "trade_date": "2026-09-27",
        "messages": [],
        "company_of_interest": "PETR4",
    }
    
    result = node(state)
    
    assert "messages" in result
    assert "news_report" in result
    assert llm.bind_tools.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_credit_news_analyst.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'tradingagents.agents.analysts.credit_news_analyst'"

- [ ] **Step 3: Write minimal implementation**

Create `tradingagents/agents/analysts/credit_news_analyst.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: credit_news_analyst.py
 * @description: Credit news analyst agent (issuer news, rating actions, covenant amendments)
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    get_news,
    get_instrument_context_from_state,
    get_language_instruction,
)


def create_credit_news_analyst(llm):
    """Create a credit news analyst node.
    
    Monitors issuer news, rating agency actions, covenant amendments,
    and restructuring events affecting creditworthiness.
    """
    def credit_news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_news,
        ]

        system_message = (
            "You are a credit news analyst monitoring Brazilian corporate bond issuers. "
            "Scan for material events affecting the issuer's creditworthiness:\n\n"
            "1. **CVM filings:** Fatos Relevantes, Avisos aos Acionistas\n"
            "2. **Rating agency actions:** S&P, Moody's, Fitch upgrades/downgrades/outlook changes\n"
            "3. **Covenant amendments:** Waiver requests, consent solicitations\n"
            "4. **Restructuring news:** M&A, divestitures, refinancing, asset sales\n\n"
            "Focus on events that impact **default risk** and **recovery rate**. "
            "Summarize material events and their credit implications (positive/negative/neutral).\n\n"
            "Use the available tool: `get_news` for issuer news and CVM filings."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other analysts."
                    " Use the provided tools to scan for credit-relevant news."
                    " If you are unable to fully answer, that's OK; another analyst with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Report what your tools support; another agent decides the credit decision."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return credit_news_analyst_node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_credit_news_analyst.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/credit_news_analyst.py tests/test_credit_news_analyst.py
git commit -m "feat(credit): add credit news analyst agent

Monitors issuer news, rating agency actions, covenant amendments, and restructuring events.
Focus on events impacting default risk and recovery rate."
```

---

## Task 8: Add .SA to Benchmark Map and Credit Holding Period

**Files:**
- Modify: `tradingagents/default_config.py:161-172`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: None (configuration change)
- Produces: `.SA: "^IRFM"` in `benchmark_map`, `credit_holding_period_days: 30` in config

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_config.py
 * @description: Tests for default configuration
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from tradingagents.default_config import DEFAULT_CONFIG


def test_benchmark_map_has_brazil():
    """Benchmark map should include .SA (Brazil) entry."""
    assert ".SA" in DEFAULT_CONFIG["benchmark_map"]
    assert DEFAULT_CONFIG["benchmark_map"][".SA"] == "^IRFM"


def test_credit_holding_period_days():
    """Config should include credit_holding_period_days."""
    assert "credit_holding_period_days" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["credit_holding_period_days"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with "AssertionError: assert '.SA' in {...}"

- [ ] **Step 3: Write minimal implementation**

Edit `tradingagents/default_config.py` (find the `benchmark_map` section and add `.SA`):

```python
"benchmark_map": {
    ".NS":  "^NSEI",       # NSE India (Nifty 50)
    ".BO":  "^BSESN",      # BSE India (Sensex)
    ".T":   "^N225",       # Tokyo (Nikkei 225)
    ".HK":  "^HSI",        # Hong Kong (Hang Seng)
    ".L":   "^FTSE",       # London (FTSE 100)
    ".TO":  "^GSPTSE",     # Toronto (TSX Composite)
    ".AX":  "^AXJO",       # Australia (ASX 200)
    ".SS":  "000001.SS",   # Shanghai (SSE Composite)
    ".SZ":  "399001.SZ",   # Shenzhen (SZSE Component)
    ".SA":  "^IRFM",       # Brazil (inflation-linked bond index) — NEW
    "":     "SPY",         # default for US-listed tickers (no suffix)
},
```

Add `credit_holding_period_days` to the config (near `holding_period_days`):

```python
"holding_period_days": 5,
"credit_holding_period_days": 30,  # NEW: separate holding period for credit mode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/default_config.py tests/test_config.py
git commit -m "feat(credit): add Brazil benchmark and credit holding period to config

Adds .SA -> ^IRFM (Brazil inflation-linked bond index) to benchmark_map.
Adds credit_holding_period_days: 30 (separate from equity 5-day holding period)."
```

---

## Task 9: Adapt Return Loop for Credit Total Return

**Files:**
- Modify: `tradingagents/graph/trading_graph.py:310-330`
- Test: `tests/test_credit_returns.py`

**Interfaces:**
- Consumes: ANBIMA vendor functions from Task 4
- Produces: `_fetch_credit_returns(cusip, analysis_date, holding_period=30)` method

- [ ] **Step 1: Write the failing test**

Create `tests/test_credit_returns.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_credit_returns.py
 * @description: Tests for credit return calculation
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from unittest.mock import MagicMock, patch
from tradingagents.graph.trading_graph import TradingAgentsGraph


def test_fetch_credit_returns_calculates_total_return():
    """_fetch_credit_returns should calculate total return from yield change."""
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    
    with patch("tradingagents.graph.trading_graph.get_debenture_quote") as mock_quote:
        mock_quote.side_effect = [
            {"price": 95.0, "yield": 12.0},  # start
            {"price": 96.0, "yield": 11.5},  # end
        ]
        
        raw_return, alpha, holding_days, resolution_date = graph._fetch_credit_returns(
            "PETR41", "2026-09-01", "^IRFM", holding_days=30
        )
        
        assert raw_return is not None
        assert isinstance(raw_return, float)
        assert raw_return > 0  # price increased from 95 to 96


def test_fetch_credit_returns_handles_missing_data():
    """_fetch_credit_returns should return None when data is unavailable."""
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    
    with patch("tradingagents.graph.trading_graph.get_debenture_quote") as mock_quote:
        mock_quote.side_effect = [
            {"price": 95.0, "yield": 12.0},  # start
            {},  # end (missing)
        ]
        
        raw_return, alpha, holding_days, resolution_date = graph._fetch_credit_returns(
            "PETR41", "2026-09-01", "^IRFM", holding_days=30
        )
        
        assert raw_return is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_credit_returns.py -v`
Expected: FAIL with "AttributeError: 'TradingAgentsGraph' object has no attribute '_fetch_credit_returns'"

- [ ] **Step 3: Write minimal implementation**

Edit `tradingagents/graph/trading_graph.py` (add new method after `_fetch_returns`):

```python
def _fetch_credit_returns(
    self,
    cusip: str,
    trade_date: str,
    benchmark: str,
    holding_days: int = 30,
) -> tuple[float | None, float | None, int | None, str | None]:
    """Calculate total return for a debenture over the holding period.
    
    Total return = (price_end - price_start) / price_start
    (Simplified: yield change only; accrued interest and roll-down in v2)
    
    Returns (raw_return, alpha, holding_days, resolution_date) or (None, None, None, None)
    if data is unavailable.
    """
    from tradingagents.dataflows.credit.anbima import get_debenture_quote
    from datetime import datetime, timedelta
    
    try:
        start_date = datetime.strptime(trade_date, "%Y-%m-%d")
        end_date = start_date + timedelta(days=holding_days)
        
        # Fetch quotes at start and end
        # TODO: Implement date-specific quote fetching
        # For now, use current quotes as placeholder
        start_quote = get_debenture_quote(cusip)
        end_quote = get_debenture_quote(cusip)  # TODO: fetch at end_date
        
        if not start_quote or not end_quote:
            return None, None, None, None
        
        price_start = start_quote.get("price")
        price_end = end_quote.get("price")
        
        if price_start is None or price_end is None:
            return None, None, None, None
        
        raw_return = (price_end - price_start) / price_start
        
        # TODO: Calculate benchmark return (IMA-B index)
        # For now, alpha = raw_return (no benchmark comparison)
        alpha = raw_return
        
        resolution_date = end_date.strftime("%Y-%m-%d")
        
        return raw_return, alpha, holding_days, resolution_date
        
    except Exception as e:
        logger.warning(
            "Could not resolve credit outcome for %s on %s (will retry next run): %s",
            cusip, trade_date, e,
        )
        return None, None, None, None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_credit_returns.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/trading_graph.py tests/test_credit_returns.py
git commit -m "feat(credit): add _fetch_credit_returns for total return calculation

Calculates total return from debenture price changes over holding period.
Simplified implementation (yield change only); accrued interest and roll-down in v2.
TODO: Implement date-specific quote fetching and benchmark comparison."
```

---

## Task 10: Integration Test for Credit Mode

**Files:**
- Create: `tests/test_credit_mode_integration.py`

**Interfaces:**
- Consumes: All previous tasks
- Produces: End-to-end integration test

- [ ] **Step 1: Write the integration test**

Create `tests/test_credit_mode_integration.py`:

```python
"""
/**
 * @module: TradingAgents
 * @file: test_credit_mode_integration.py
 * @description: Integration tests for credit mode
 * @author: AI Assistant
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""

import pytest
from cli.models import AssetType, AnalystType
from cli.utils import detect_asset_type, filter_analysts_for_asset_type


def test_credit_mode_end_to_end():
    """End-to-end test: detect credit ticker, filter analysts, verify credit mode."""
    # Detect asset type
    ticker = "PETR41"
    asset_type = detect_asset_type(ticker)
    assert asset_type == AssetType.CREDIT
    
    # Filter analysts
    all_analysts = [
        AnalystType.MARKET,
        AnalystType.SOCIAL,
        AnalystType.NEWS,
        AnalystType.FUNDAMENTALS,
        AnalystType.CREDIT_FUNDAMENTALS,
        AnalystType.CREDIT_NEWS,
    ]
    filtered = filter_analysts_for_asset_type(all_analysts, asset_type)
    
    # Verify only credit analysts remain
    assert len(filtered) == 2
    assert AnalystType.CREDIT_FUNDAMENTALS in filtered
    assert AnalystType.CREDIT_NEWS in filtered
    assert AnalystType.MARKET not in filtered
    assert AnalystType.SOCIAL not in filtered


def test_brazilian_equity_not_credit():
    """Brazilian equity (.SA suffix) should be STOCK, not CREDIT."""
    ticker = "PETR4.SA"
    asset_type = detect_asset_type(ticker)
    assert asset_type == AssetType.STOCK


def test_us_equity_not_credit():
    """US equity should be STOCK, not CREDIT."""
    ticker = "AAPL"
    asset_type = detect_asset_type(ticker)
    assert asset_type == AssetType.STOCK
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_credit_mode_integration.py -v`
Expected: PASS (3 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_credit_mode_integration.py
git commit -m "test(credit): add integration tests for credit mode

End-to-end test: detect credit ticker, filter analysts, verify credit mode.
Verifies Brazilian equity (.SA) and US equity are not mis-classified as credit."
```

---

## Task 11: Update Documentation and Governance Headers

**Files:**
- Modify: All new/modified Python files (add/update governance headers)

- [ ] **Step 1: Verify all files have governance headers**

Check all new/modified files for governance headers:

```bash
# List all new/modified files
git diff --name-only HEAD~10

# For each file, check if it has a governance header
for file in $(git diff --name-only HEAD~10); do
    if [[ $file == *.py ]]; then
        if ! grep -q "@module:" "$file"; then
            echo "Missing header: $file"
        fi
    fi
done
```

- [ ] **Step 2: Add missing headers**

For any files missing headers, add the standard governance header:

```python
"""
/**
 * @module: TradingAgents
 * @file: <filename>
 * @description: <one-line description>
 * @author: Maíra Pontin
 * @created: 2026-09-27T18:45:00
 * @updated: 2026-09-27T18:45:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */
"""
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs(credit): add governance headers to all new/modified files

Ensures all Python files have standard governance headers per AGENTS.md."
```

---

## Summary

**Total tasks:** 11  
**Estimated effort:** 2-3 days  
**Test coverage:** >80% for new code

**Key deliverables:**
1. AssetType.CREDIT enum value
2. Debenture CUSIP detection (4 letters + 2 digits)
3. Credit analyst filtering (CREDIT_FUNDAMENTALS, CREDIT_NEWS only)
4. ANBIMA data vendor (yield curve, spreads, quotes, IMA-B)
5. Credit fundamentals analyst agent
6. Credit news analyst agent
7. Brazil benchmark (.SA -> ^IRFM)
8. Credit holding period (30 days)
9. Credit return calculation (total return from price changes)
10. Integration tests
11. Governance headers

**Next steps after implementation:**
- Replace mock ANBIMA API with actual API client or web scraper
- Implement date-specific quote fetching in `_fetch_credit_returns`
- Add accrued interest and roll-down to total return calculation
- Implement CVM filing parser for structured financial data
- Validate against real credit research reports (S&P, Moody's)
