/**
 * @module: TradingAgents
 * @file: 2026-09-27-credit-debenture-mode-design.md
 * @description: Design spec for Brazilian debenture credit analysis mode
 * @author: Maíra Pontin
 * @created: 2026-09-27T18:15:00
 * @updated: 2026-09-27T18:15:00
 * @version: 1.0.0
 * @reviewer:
 * @ai_reviewer:
 * @reviewer_date:
 */

# Credit/Debenture Mode Design Specification

**Date:** 2026-09-27  
**Status:** Draft  
**Author:** Maíra Pontin  
**Version:** 1.0.0

---

## 1. Overview

### 1.1 Goal

Add a credit/debenture analysis mode to the TradingAgents multi-agent framework to support Brazilian corporate bonds (debêntures) in the secondary market. This extends the existing stock and crypto asset modes with credit-specific analysts, data sources, and decision logic.

### 1.2 Motivation

The TradingAgents framework currently supports equity (stock) and crypto asset analysis. Brazilian corporate bonds (debêntures) represent a significant asset class with distinct analytical requirements:

- **Credit analysis** focuses on downside protection (leverage, coverage, cash flow, recovery rate) rather than upside potential (P/E, revenue growth)
- **Data sources** differ: ANBIMA, CVM filings, B3 CETIP instead of Yahoo Finance, Alpha Vantage
- **Return calculation** uses total return (yield change + accrued interest) instead of price return
- **Decision scale** uses credit ratings (Investment Grade / Speculative Grade / Default) instead of equity ratings (Buy / Sell)

### 1.3 Scope

**In scope:**
- Brazilian debentures (corporate bonds under Lei 6.404/1976)
- ANBIMA free data tier (IMA-B index, indicative quotes, yield curve)
- Credit fundamentals analysis (leverage, coverage, cash flow, asset quality)
- Credit news analysis (issuer news, rating actions, covenant amendments)
- Total return calculation (yield change + accrued interest + roll-down)
- Integration with existing framework (committee debate, structured decision, memory/reflection, checkpoint/resume)

**Out of scope:**
- Covenant parser (separate project — requires NLP/OCR for indenture extraction)
- Sovereign bonds, municipal bonds
- Paid data sources (B3 CETIP, broker quotes)
- Multi-currency debentures
- International bonds (Eurobonds, Yankee bonds)

---

## 2. Architecture

### 2.1 Approach: Extend AssetType Enum (Like Crypto Mode)

The design mirrors the proven crypto mode pattern: extend the `AssetType` enum, add credit-specific analysts and data vendor, and adapt the return loop for credit total return.

**Rationale:**
- Crypto mode touched only 6 files — minimal framework changes
- Clean separation: credit mode is a first-class citizen
- Reuses existing infrastructure (committee debate, structured decision, memory/reflection, checkpoint/resume)
- Proven pattern: equity → crypto → credit follows the same extension model

**Alternatives considered:**
- **Credit-specific subgraph (separate pipeline):** Cleaner isolation but duplicates framework code (committee debate, decision logic, checkpoint). Rejected: too much duplication.
- **Out-of-graph decision support (no new mode):** Fast to prototype but conflates equity and credit analysis. Rejected: produces a hybrid that's neither good equity nor good credit analysis.

### 2.2 High-Level Data Flow

```
User input: "PETR4" (Petrobras debenture issuer)
  ↓
detect_asset_type → CREDIT (via .SA suffix or debenture ticker pattern)
  ↓
filter_analysts → [credit_fundamentals, credit_news]
  ↓
Credit fundamentals analyst:
  - Fetch leverage ratios from CVM filings (Net Debt/EBITDA, Debt/Equity)
  - Fetch interest coverage (EBITDA/Interest Expense)
  - Fetch cash flow adequacy (FCF/Debt, FCF/Interest)
  - Fetch yield curve from ANBIMA (zero rates by maturity)
  - Calculate credit spread vs CDI
  - Estimate recovery rate (asset quality, seniority, collateral)
  ↓
Credit news analyst:
  - Fetch issuer news (CVM filings, press releases)
  - Scan for rating agency actions (Moody's, S&P, Fitch)
  - Detect covenant amendments or waiver requests
  ↓
Bull/Bear debate → Research Manager → Trader → Risk debate → Portfolio Manager
  ↓
Decision: "Investment Grade" with conviction score and spread target
  ↓
Return loop: 30-day total return vs IMA-B index
  ↓
Memory/reflection: store lesson for future runs
```

---

## 3. Components

### 3.1 AssetType Enum Extension

**File:** `cli/models.py:13-15`

**Change:** Add `CREDIT = "credit"` to the `AssetType` enum.

```python
class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
    CREDIT = "credit"  # NEW
```

**Detection:** Extend `cli/utils.py:81-87` `detect_asset_type` function:

```python
def detect_asset_type(ticker: str) -> AssetType:
    canonical = normalize_symbol(ticker)
    # Crypto: -USD suffix
    if canonical.endswith("-USD"):
        return AssetType.CRYPTO
    # Credit: .SA suffix (Brazil) or explicit debenture pattern
    if canonical.endswith(".SA") or is_debenture_ticker(canonical):
        return AssetType.CREDIT
    # Default: stock
    return AssetType.STOCK
```

**Debenture ticker pattern:** Brazilian debentures are identified by issuer stock ticker + series (e.g., `PETR4` for Petrobras, `VALE3` for Vale). For the prototype, treat all `.SA` tickers as credit if the user explicitly selects credit mode, or if the ticker matches a known debenture issuer list.

**Future enhancement:** Add CUSIP/ISIN support for explicit debenture identification.

### 3.2 Analyst Set

**Change:** Add two new credit-specific analysts, drop market and social/sentiment analysts for credit mode.

#### 3.2.1 Credit Fundamentals Analyst

**Directory:** `tradingagents/agents/analysts/credit_fundamentals/`

**Responsibilities:**
- Leverage ratios: Net Debt/EBITDA, Debt/Equity, Debt/Assets
- Interest coverage: EBITDA/Interest Expense, EBIT/Interest Expense
- Cash flow adequacy: FCF/Debt, FCF/Interest, Operating Cash Flow/Debt
- Asset quality: tangible assets, collateral value, recovery rate estimation
- Profitability: EBITDA margin, ROA, ROE (context for creditworthiness)

**Tools:**
- `get_financial_ratios(ticker, date)` — fetch from CVM filings (free)
- `get_yield_curve(date)` — fetch from ANBIMA (free)
- `get_credit_spreads(ticker, date)` — calculate spread vs CDI
- `get_balance_sheet(ticker, date)` — fetch from CVM filings

**Prompt framing:**
```
You are a credit analyst evaluating the creditworthiness of {company_name} ({ticker}).
Focus on downside protection: leverage, interest coverage, cash flow adequacy, 
asset quality, and recovery rate. Do not analyze upside potential or price momentum.
Provide a credit assessment: Investment Grade (BBB- or higher) or Speculative Grade 
(BB+ or lower), with conviction score (0-100) and key risk factors.
```

#### 3.2.2 Credit News Analyst

**Directory:** `tradingagents/agents/analysts/credit_news/`

**Responsibilities:**
- Issuer news: CVM filings, press releases, earnings calls
- Rating agency actions: Moody's, S&P, Fitch upgrades/downgrades/outlook changes
- Covenant amendments: waiver requests, consent solicitations
- Market sentiment: credit spreads widening/tightening, peer comparison

**Tools:**
- `get_news(ticker, date_window)` — fetch from CVM, Yahoo Finance news
- `get_rating_actions(ticker, date_window)` — fetch from rating agency APIs (if available) or scrape from news
- `get_credit_spreads_history(ticker, date_window)` — historical spread evolution

**Prompt framing:**
```
You are a credit news analyst monitoring {company_name} ({ticker}).
Focus on credit-relevant news: rating actions, covenant amendments, 
material events affecting creditworthiness, peer credit spread movements.
Do not analyze stock price momentum or retail sentiment.
Provide a credit news summary with impact assessment (positive/negative/neutral)
and materiality score (0-100).
```

#### 3.2.3 Analyst Filtering

**File:** `cli/utils.py:90-98`

**Change:** Extend `filter_analysts_for_asset_type` to drop market and social/sentiment analysts for credit mode.

```python
def filter_analysts_for_asset_type(analysts: list[AnalystType], asset_type: AssetType) -> list[AnalystType]:
    if asset_type == AssetType.CRYPTO:
        return [a for a in analysts if a != AnalystType.FUNDAMENTALS]
    if asset_type == AssetType.CREDIT:
        # Credit mode: only credit_fundamentals and credit_news
        return [a for a in analysts if a in (AnalystType.CREDIT_FUNDAMENTALS, AnalystType.CREDIT_NEWS)]
    return analysts
```

**New AnalystType enum values:**

```python
class AnalystType(str, Enum):
    MARKET = "market"
    SOCIAL = "social"  # Wire value stays "social" for back-compat
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    CREDIT_FUNDAMENTALS = "credit_fundamentals"  # NEW
    CREDIT_NEWS = "credit_news"  # NEW
```

### 3.3 Data Vendor: ANBIMA

**Directory:** `tradingagents/dataflows/credit/`

**Responsibilities:**
- Fetch ANBIMA free data: IMA-B index returns, indicative quotes, yield curve
- Provide credit-specific tools: `get_yield_curve`, `get_credit_spreads`, `get_debenture_quote`

**Data sources:**
- **ANBIMA website:** https://www.anbima.com.br/en_us/home/
  - IMA-B index (Brazil inflation-linked bond index) — daily returns
  - Indicative quotes for benchmark debentures
  - Yield curve (zero rates by maturity)
- **CVM (Brazilian SEC):** https://www.gov.br/cvm/pt-br
  - Company filings (financial statements, material facts)
  - Free, no API key required

**Implementation:**

```python
# tradingagents/dataflows/credit/anbima.py

import requests
from datetime import date, timedelta
import pandas as pd

def get_ima_b_index(start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch IMA-B index daily returns from ANBIMA.
    
    Returns DataFrame with columns: date, index_value, daily_return
    """
    # ANBIMA provides CSV downloads
    # Implementation: download CSV, parse, return DataFrame
    pass

def get_yield_curve(as_of_date: date) -> pd.DataFrame:
    """Fetch ANBIMA yield curve (zero rates by maturity).
    
    Returns DataFrame with columns: maturity_years, zero_rate
    """
    # ANBIMA publishes daily yield curve
    # Implementation: fetch from ANBIMA API or scrape from website
    pass

def get_indicative_quote(ticker: str, as_of_date: date) -> dict:
    """Fetch indicative quote for a benchmark debenture.
    
    Returns dict with: price, yield, spread_vs_cdi, accrued_interest
    """
    # ANBIMA publishes indicative quotes for benchmark debentures
    # Implementation: fetch from ANBIMA API or scrape from website
    pass
```

**Vendor registration:**

```python
# tradingagents/dataflows/interface.py

VENDOR_LIST = ["alpha_vantage", "yfinance", "fred", "polymarket", "anbima"]  # ADD "anbima"

TOOLS_CATEGORIES = {
    # ... existing categories ...
    "credit_data": ["anbima"],  # NEW category
}
```

### 3.4 Return Loop Adaptation

**File:** `tradingagents/graph/trading_graph.py:310-330`

**Current implementation (equity/crypto):**
```python
def _fetch_returns(self, ticker: str, start_date: date, end_date: date) -> dict:
    # Fetch daily price bars from Yahoo Finance
    # Calculate N-day price return
    # Compare to benchmark (SPY, ^NSEI, etc.)
    pass
```

**Credit adaptation:**
```python
def _fetch_credit_returns(self, ticker: str, start_date: date, end_date: date) -> dict:
    """Calculate total return for a debenture.
    
    Total return = yield change + accrued interest + roll-down
    """
    # Fetch yield at start_date and end_date from ANBIMA
    # Calculate price change from yield change (duration-adjusted)
    # Add accrued interest
    # Add roll-down (yield curve slope)
    # Compare to benchmark (IMA-B index or CDI+spread)
    pass
```

**Holding period:** Configurable, default 30 days (debentures trade less frequently than equities).

```python
# tradingagents/default_config.py

"holding_period_days": 30,  # Change from 5 to 30 for credit mode
```

**Conditional logic:**
```python
if asset_type == AssetType.CREDIT:
    returns = self._fetch_credit_returns(ticker, start_date, end_date)
else:
    returns = self._fetch_returns(ticker, start_date, end_date)
```

### 3.5 Benchmark Map

**File:** `tradingagents/default_config.py:161-172`

**Change:** Add `.SA` (Brazil) entry to `benchmark_map`.

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

**Alternative:** Use `^IMA-B` (ANBIMA debenture index) instead of `^IRFM`. Decision: use `^IRFM` for consistency with Yahoo Finance symbol conventions, but fetch actual returns from ANBIMA API.

### 3.6 CLI Changes

**File:** `cli/utils.py`

**Changes:**
1. Extend `detect_asset_type` for credit (see 3.1)
2. Extend `filter_analysts_for_asset_type` for credit (see 3.2.3)

**File:** `cli/main.py`

**Changes:**
- Add credit-specific help text
- Add credit-specific examples

### 3.7 Prompts

**File:** `tradingagents/agents/utils/agent_utils.py:156,168,193-197`

**Changes:** Add credit-specific prompt branches.

```python
if asset_type == "credit":
    context += (
        " Treat it as a corporate bond issuer rather than an equity. "
        "Focus on creditworthiness: leverage, coverage, cash flow, asset quality. "
        "Do not analyze upside potential or price momentum."
    )
```

**Decision scale:**
- Equity: Buy / Overweight / Hold / Underweight / Sell
- Credit: Investment Grade / Speculative Grade / Default (with conviction score 0-100)

---

## 4. Files to Create/Modify

### 4.1 Modify

| File | Change |
|------|--------|
| `cli/models.py` | Add `CREDIT = "credit"` to `AssetType` enum; add `CREDIT_FUNDAMENTALS`, `CREDIT_NEWS` to `AnalystType` enum |
| `cli/utils.py` | Extend `detect_asset_type` for `.SA` suffix; extend `filter_analysts_for_asset_type` for credit mode |
| `tradingagents/default_config.py` | Add `.SA: "^IRFM"` to `benchmark_map`; change default `holding_period_days` to 30 for credit mode |
| `tradingagents/agents/utils/agent_utils.py` | Add credit-specific prompt branches |
| `tradingagents/graph/trading_graph.py` | Add `_fetch_credit_returns` method; add conditional logic to call it for credit mode |
| `tradingagents/dataflows/interface.py` | Add `"anbima"` to `VENDOR_LIST`; add `"credit_data"` category to `TOOLS_CATEGORIES` |

### 4.2 Create

| File | Purpose |
|------|---------|
| `tradingagents/agents/analysts/credit_fundamentals/__init__.py` | Credit fundamentals analyst agent |
| `tradingagents/agents/analysts/credit_fundamentals/prompt.py` | Prompt template for credit fundamentals |
| `tradingagents/agents/analysts/credit_news/__init__.py` | Credit news analyst agent |
| `tradingagents/agents/analysts/credit_news/prompt.py` | Prompt template for credit news |
| `tradingagents/dataflows/credit/__init__.py` | Credit data vendor module |
| `tradingagents/dataflows/credit/anbima.py` | ANBIMA data fetcher (IMA-B, yield curve, indicative quotes) |
| `tradingagents/dataflows/credit/cvm.py` | CVM filings fetcher (financial statements, material facts) |
| `tests/test_credit_mode.py` | Integration tests for credit mode |

---

## 5. Testing Strategy

### 5.1 Unit Tests

- **AssetType detection:** test `.SA` suffix detection, debenture ticker pattern matching
- **Analyst filtering:** test credit mode drops market/social analysts
- **ANBIMA data fetcher:** test IMA-B index fetch, yield curve fetch, indicative quote fetch (mock HTTP requests)
- **Credit return calculation:** test total return formula (yield change + accrued interest + roll-down)

### 5.2 Integration Tests

- **End-to-end credit run:** run the full graph with a known debenture issuer (e.g., Petrobras `PETR4`)
- **Checkpoint/resume:** test credit mode checkpoint and resume
- **Memory/reflection:** test credit mode memory loop (log decision, fetch returns, generate reflection)

### 5.3 Manual Validation

- Compare credit analyst output to a human credit analyst's assessment of the same issuer
- Compare total return calculation to ANBIMA's published IMA-B returns
- Compare credit spread to Bloomberg/Reuters (if available)

---

## 6. Implementation Notes

### 6.1 ANBIMA Data Access

ANBIMA provides free data via:
- **CSV downloads:** https://www.anbima.com.br/en_us/home/ (manual download)
- **API:** No public API; requires web scraping or manual download

**Implementation strategy:**
1. For prototype: provide a utility to download CSV files manually and place them in a local directory
2. For production: implement web scraping (with rate limiting and error handling) or partner with a data provider

### 6.2 CVM Data Access

CVM provides free data via:
- **Website:** https://www.gov.br/cvm/pt-br (manual download)
- **API:** CVM provides a SOAP API (requires registration)

**Implementation strategy:**
1. For prototype: use Yahoo Finance for Brazilian equities (which includes financial statements)
2. For production: implement CVM API client or use a third-party provider (e.g., TradingEconomics, Refinitiv)

### 6.3 Debenture Ticker Identification

Brazilian debentures are not traded on exchanges like equities. They are identified by:
- **Issuer ticker:** e.g., `PETR4` for Petrobras
- **Series:** e.g., `PETR4` series 2023A, 2023B, etc.
- **CUSIP/ISIN:** unique identifier for each debenture series

**Implementation strategy:**
1. For prototype: treat all `.SA` tickers as credit if user explicitly selects credit mode
2. For production: maintain a mapping of issuer ticker → debenture series → CUSIP/ISIN

### 6.4 Covenant Parser (Out of Scope)

Covenant extraction from indentures requires:
- **OCR:** scan PDF indentures
- **NLP:** extract covenant terms (financial covenants, negative covenants, affirmative covenants)
- **Legal expertise:** interpret covenant terms and assess restrictiveness

**Implementation strategy:**
1. For prototype: skip covenant analysis
2. For production: partner with a legal tech provider or build in-house NLP pipeline

---

## 7. Migration Path

### 7.1 Phase 1: Prototype (4 weeks)

- Extend `AssetType` enum
- Add credit fundamentals analyst (using Yahoo Finance for financial data)
- Add ANBIMA data fetcher (manual CSV download)
- Adapt return loop for credit total return
- Add `.SA` to benchmark map
- Integration tests

### 7.2 Phase 2: Production (4 weeks)

- Add credit news analyst
- Implement ANBIMA web scraping (or partner with data provider)
- Implement CVM API client
- Add debenture ticker identification (issuer → series → CUSIP/ISIN)
- Manual validation against human credit analyst

### 7.3 Phase 3: Enhancement (ongoing)

- Add covenant parser (OCR + NLP)
- Add paid data sources (B3 CETIP, broker quotes)
- Add multi-currency debentures
- Add international bonds

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| ANBIMA data access changes | High | Implement fallback to manual CSV download; partner with alternative data provider |
| CVM API rate limits | Medium | Implement caching and rate limiting; use Yahoo Finance as fallback for financial data |
| Debenture ticker identification errors | Medium | Maintain a curated mapping of issuer → debenture series; allow manual override |
| Credit analyst hallucination | High | Ground prompts in credit-specific metrics; validate against human credit analyst |
| Total return calculation errors | High | Validate against ANBIMA's published IMA-B returns; add unit tests for edge cases |

---

## 9. Success Criteria

1. **Functional:** User can run a credit analysis on a Brazilian debenture issuer (e.g., `PETR4`) and receive a credit assessment (Investment Grade / Speculative Grade) with conviction score
2. **Accuracy:** Credit assessment matches human credit analyst's assessment ≥80% of the time (validated on 10 issuers)
3. **Performance:** Total return calculation matches ANBIMA's published IMA-B returns within 0.1%
4. **Usability:** CLI provides clear help text and examples for credit mode

---

## 10. References

- **TradingAgents framework:** https://github.com/TauricResearch/TradingAgents
- **ANBIMA:** https://www.anbima.com.br/en_us/home/
- **CVM:** https://www.gov.br/cvm/pt-br
- **Brazilian Corporate Law (Lei 6.404/1976):** https://www.planalto.gov.br/ccivil_03/leis/l6404consolada.htm
- **CVM Instruction 414/2004:** https://www.gov.br/cvm/pt-br/assuntos/normativos/instrucoes/instrucao-cvm-414-2004

---

## 11. Appendix

### 11.1 Credit Fundamentals Analyst Tools

| Tool | Description | Data Source |
|------|-------------|-------------|
| `get_financial_ratios(ticker, date)` | Fetch leverage, coverage, profitability ratios | CVM filings (via Yahoo Finance) |
| `get_yield_curve(date)` | Fetch ANBIMA yield curve (zero rates by maturity) | ANBIMA |
| `get_credit_spreads(ticker, date)` | Calculate credit spread vs CDI | ANBIMA + B3 CETIP |
| `get_balance_sheet(ticker, date)` | Fetch balance sheet (assets, liabilities, equity) | CVM filings (via Yahoo Finance) |

### 11.2 Credit News Analyst Tools

| Tool | Description | Data Source |
|------|-------------|-------------|
| `get_news(ticker, date_window)` | Fetch issuer news, CVM filings, press releases | CVM, Yahoo Finance |
| `get_rating_actions(ticker, date_window)` | Fetch rating agency actions (upgrades/downgrades/outlook changes) | Rating agency APIs (if available) or news scraping |
| `get_credit_spreads_history(ticker, date_window)` | Fetch historical credit spread evolution | ANBIMA + B3 CETIP |

### 11.3 Credit Decision Scale

| Rating | Definition | Conviction Score |
|--------|------------|------------------|
| Investment Grade (BBB- or higher) | Low credit risk, strong creditworthiness | 70-100 |
| Speculative Grade (BB+ or lower) | High credit risk, speculative creditworthiness | 40-69 |
| Default (D) | Issuer has defaulted on debt obligations | 0-39 |

### 11.4 Total Return Formula

```
Total Return = (Price_End - Price_Start + Accrued_Interest_End - Accrued_Interest_Start + Coupon_Payments) / (Price_Start + Accrued_Interest_Start)

Where:
- Price = f(yield, duration, convexity)
- Accrued_Interest = coupon_rate * days_since_last_coupon / days_in_coupon_period
- Coupon_Payments = sum of coupon payments during holding period
```

---

**End of Specification**
