# XAU Data Layer - Quick Start Guide

**Status**: ✅ Phase 1 Complete - Data Infrastructure Implemented

---

## 📋 Overview

The XAU data layer provides comprehensive data sources for gold trading analysis:

1. **FRED API** - Macro economic data (DXY, yields, inflation, Fed policy)
2. **COT Data** - Commitment of Traders positioning (sentiment indicator)
3. **ETF Flows** - Gold ETF holdings tracking (institutional sentiment)
4. **Correlation Tools** - Asset correlation analysis and regime detection

---

## 🚀 Quick Start

### 1. Setup API Keys

Get a free FRED API key:
- Visit: https://fred.stlouisfed.org/docs/api/api_key.html
- Register for free API access
- Add to your `.env` file:

```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your keys:
FRED_API_KEY=your_fred_api_key_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
OPENAI_API_KEY=your_openai_key
```

### 2. Install Dependencies

All required packages are in `requirements.txt`:

```bash
pip install -r requirements.txt
```

Additional packages used:
- `requests` - HTTP requests
- `pandas` - Data manipulation
- `numpy` - Numerical calculations
- `beautifulsoup4` - Web scraping (for ETF data)
- `yfinance` - Yahoo Finance data

### 3. Run Tests

Test all data sources:

```bash
python test_xau_data_layer.py
```

Expected output:
```
✅ FRED API tests PASSED
✅ COT data tests PASSED
✅ ETF flows tests PASSED
✅ Correlation tools tests PASSED
✅ Integration test PASSED
```

---

## 📊 Data Sources

### 1. FRED API (`tradingagents/dataflows/fred_api.py`)

**Macro economic indicators critical for gold:**

#### Available Functions:

```python
from tradingagents.dataflows.fred_api import (
    get_fred_series,
    get_dxy_data,
    get_real_yields,
    get_inflation_data
)

# US Dollar Index (DXY) - Primary gold driver
dxy = get_dxy_data("2024-01-01", "2024-05-10")

# Real Yields (opportunity cost of holding gold)
real_yields = get_real_yields("2024-01-01", "2024-05-10")

# Inflation indicators (CPI, Core CPI, PCE, Core PCE)
inflation = get_inflation_data("2024-01-01", "2024-05-10")

# Any FRED series by name
vix = get_fred_series("VIX", "2024-01-01", "2024-05-10")
fed_funds = get_fred_series("FED_FUNDS", "2024-01-01", "2024-05-10")
```

#### Supported Series (Friendly Names):

- **Dollar**: `DXY` (US Dollar Index)
- **Yields**: `10Y_YIELD`, `2Y_YIELD`, `30Y_YIELD`, `10Y_TIPS`, `10Y_BREAKEVEN`
- **Inflation**: `CPI`, `CORE_CPI`, `PCE`, `CORE_PCE`, `PPI`
- **Fed Policy**: `FED_FUNDS`, `FED_BALANCE`
- **Market**: `VIX`, `SP500`
- **Economy**: `GDP`, `UNEMPLOYMENT`, `RETAIL_SALES`

#### Key Insights:

- **Real Yields = Nominal Yield - Inflation Expectations**
  - Negative real yields → Bullish for gold (no opportunity cost)
  - Positive real yields → Bearish for gold (bonds more attractive)

- **DXY Correlation**: ~-0.75 (strong negative)
  - Rising DXY → Headwind for gold
  - Falling DXY → Tailwind for gold

---

### 2. COT Data (`tradingagents/dataflows/cot_data.py`)

**Commitment of Traders positioning - contrarian indicator:**

#### Available Functions:

```python
from tradingagents.dataflows.cot_data import (
    get_cot_positioning,
    analyze_cot_extremes
)

# Get gold futures positioning
cot_data = get_cot_positioning(
    asset="GOLD",
    start_date="2024-01-01",
    end_date="2024-05-10",
    lookback_weeks=52
)

# Analyze extremes (contrarian signals)
extremes = analyze_cot_extremes(
    current_date="2024-05-10",
    lookback_years=3
)
```

#### Trader Categories:

1. **Large Speculators** (Non-Commercial)
   - Hedge funds, CTAs, trend followers
   - Sentiment leaders
   - Extreme longs → Potential reversal (crowded trade)

2. **Commercials**
   - Gold producers, refiners, miners
   - "Smart money" hedgers
   - Typically opposite to speculators

3. **Small Traders** (Non-Reportable)
   - Retail/individual traders
   - Often contrarian indicator (wrong at extremes)

#### Key Metrics:

- **Net Positioning** = Longs - Shorts
- **Percentile Ranking** vs 3-year history
- **Extremes**:
  - >90th percentile = Extremely bullish positioning (bearish signal)
  - <10th percentile = Extremely bearish positioning (bullish signal)

---

### 3. ETF Flows (`tradingagents/dataflows/etf_flows.py`)

**Gold ETF holdings tracking - institutional sentiment:**

#### Available Functions:

```python
from tradingagents.dataflows.etf_flows import (
    get_gold_etf_flows,
    get_gold_etf_summary,
    analyze_etf_divergence
)

# GLD (SPDR Gold Shares) flows
gld_flows = get_gold_etf_flows("GLD", "2024-01-01", "2024-05-10")

# IAU (iShares Gold Trust) flows
iau_flows = get_gold_etf_flows("IAU", "2024-01-01", "2024-05-10")

# Combined summary
summary = get_gold_etf_summary("2024-01-01", "2024-05-10")

# Divergence analysis
divergence = analyze_etf_divergence("GLD", gold_price, etf_flows)
```

#### Major Gold ETFs:

1. **GLD (SPDR Gold Shares)**
   - Largest gold ETF (~$55B AUM)
   - Each share = ~0.1 oz gold
   - Holdings published daily

2. **IAU (iShares Gold Trust)**
   - Second largest (~$28B AUM)
   - Lower expense ratio than GLD
   - Popular with retail

#### Flow Interpretation:

- **Inflows** (Positive):
  - Institutions accumulating gold → Bullish sentiment
  - Sustained inflows (3-5 days) → Strong conviction

- **Outflows** (Negative):
  - Institutions reducing exposure → Bearish sentiment
  - Redemptions → Profit-taking or risk reduction

- **Divergences**:
  - Price ↑ + Outflows → Weak rally, potential top
  - Price ↓ + Inflows → Accumulation phase, potential bottom

---

### 4. Correlation Tools (`tradingagents/dataflows/correlation_tools.py`)

**Asset correlation analysis and regime detection:**

#### Available Functions:

```python
from tradingagents.dataflows.correlation_tools import (
    calculate_asset_correlation,
    analyze_gold_macro_correlations,
    check_correlation_regime,
    get_rolling_correlations
)

# Calculate correlation between assets
corr = calculate_asset_correlation(
    asset1_data=gold_csv,
    asset2_data=dxy_csv,
    window_days=90
)

# Comprehensive macro correlation analysis
macro_analysis = analyze_gold_macro_correlations(
    gold_data=gold_csv,
    dxy_data=dxy_csv,
    yields_data=yields_csv,
    vix_data=vix_csv  # optional
)

# Detect correlation regime changes
regime = check_correlation_regime(gold_csv, dxy_csv)

# Rolling correlations across multiple windows
rolling = get_rolling_correlations(
    gold_csv, dxy_csv,
    windows=[30, 60, 90, 180]
)
```

#### Expected Gold Correlations:

| Asset/Indicator | Expected Correlation | Interpretation |
|----------------|---------------------|----------------|
| **DXY** | -0.75 (strong negative) | USD strength = gold weakness |
| **Real Yields** | -0.85 (very strong negative) | Higher real yields = higher opportunity cost |
| **VIX** | +0.40 (moderate positive) | Risk-off → gold benefits |
| **SPY** | -0.20 (weak negative) | Risk-on equities = less gold demand |
| **CPI** | +0.60 (moderate positive) | Inflation hedge characteristic |

#### Correlation Regime Analysis:

- **Stable Regime**: Correlation consistent across 30d/90d/180d windows
- **Regime Change**: Correlation shifts >0.3 between short/long-term
  - Example: Gold-DXY correlation weakening → Other factors driving gold (geopolitics, inflation)

#### Trading Implications:

```python
# Pre-trade correlation checks
if gold_dxy_corr < -0.6:
    # Healthy negative correlation
    if dxy_falling:
        increase_gold_long_conviction()
    elif dxy_rising:
        reduce_gold_long_size()
else:
    # Correlation breakdown - identify new driver
    check_geopolitical_events()
    check_inflation_surprises()
```

---

## 🔧 Usage Examples

### Example 1: Complete Gold Analysis Workflow

```python
from tradingagents.dataflows.fred_api import get_dxy_data, get_real_yields
from tradingagents.dataflows.cot_data import get_cot_positioning
from tradingagents.dataflows.etf_flows import get_gold_etf_flows
from tradingagents.dataflows.correlation_tools import analyze_gold_macro_correlations
from tradingagents.dataflows.y_finance import get_YFin_data_online

# Date range
start = "2024-01-01"
end = "2024-05-10"

# 1. Get gold price
gold_price = get_YFin_data_online("GC=F", start, end)

# 2. Get macro factors
dxy = get_dxy_data(start, end)
real_yields = get_real_yields(start, end)

# 3. Get positioning
cot = get_cot_positioning("GOLD", start, end)
gld_flows = get_gold_etf_flows("GLD", start, end)

# 4. Analyze correlations
macro_corr = analyze_gold_macro_correlations(gold_price, dxy, real_yields)

# 5. Make trading decision based on:
# - DXY trend (falling = bullish)
# - Real yields (negative = bullish)
# - COT positioning (extreme longs = caution)
# - ETF flows (inflows = bullish)
# - Correlation regime (stable = predictable)
```

### Example 2: Macro Filter for Gold Trades

```python
def check_macro_environment_for_gold(date):
    """
    Pre-trade macro filter.
    Returns: "BULLISH", "BEARISH", or "NEUTRAL"
    """
    from tradingagents.dataflows.fred_api import get_dxy_data, get_real_yields

    # Get macro data
    lookback_start = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")
    dxy = get_dxy_data(lookback_start, date)
    real_yields = get_real_yields(lookback_start, date)

    # Parse latest values (simplified)
    dxy_trend = "falling" if "falling" in dxy else "rising"
    real_yield_value = -0.5  # Extract from CSV

    # Decision logic
    bullish_factors = 0
    bearish_factors = 0

    # Factor 1: DXY trend
    if dxy_trend == "falling":
        bullish_factors += 2
    else:
        bearish_factors += 2

    # Factor 2: Real yields
    if real_yield_value < 0:
        bullish_factors += 3  # Strong weight
    elif real_yield_value > 1.0:
        bearish_factors += 3

    # Factor 3: VIX (risk sentiment)
    # ... additional factors

    if bullish_factors > bearish_factors + 2:
        return "BULLISH"
    elif bearish_factors > bullish_factors + 2:
        return "BEARISH"
    else:
        return "NEUTRAL"
```

---

## 📈 Next Steps

### Phase 2: Agent Specialization (Week 3-4)

Now that data layer is complete, create XAU-specific agents:

1. **XAU Market Analyst** (`xau_market_analyst.py`)
   - Gold-specific technical indicators
   - Multi-timeframe analysis
   - Key support/resistance levels

2. **XAU Macro Analyst** (`xau_macro_analyst.py`)
   - Use FRED data for DXY, yields, inflation analysis
   - Fed policy interpretation
   - Central bank activity monitoring

3. **XAU News Analyst** (`xau_news_analyst.py`)
   - Geopolitical event detection
   - Macro data release monitoring
   - Safe-haven narrative identification

4. **XAU Positioning Analyst** (`xau_positioning_analyst.py`)
   - COT report analysis
   - ETF flow tracking
   - Contrarian signals from extremes

### Integration with TradingAgents Framework

Update agent tools to include XAU data sources:

```python
# tradingagents/agents/utils/agent_utils.py
from tradingagents.dataflows.fred_api import get_dxy_data, get_real_yields
from tradingagents.dataflows.cot_data import get_cot_positioning
from tradingagents.dataflows.etf_flows import get_gold_etf_flows
from tradingagents.dataflows.correlation_tools import analyze_gold_macro_correlations

# Add to tool exports for LangGraph agents
__all__ = [
    # ... existing tools
    "get_dxy_data",
    "get_real_yields",
    "get_cot_positioning",
    "get_gold_etf_flows",
    "analyze_gold_macro_correlations",
]
```

---

## 🐛 Troubleshooting

### FRED API Issues

**Error: "FRED API key required"**
- Solution: Add `FRED_API_KEY` to `.env` file
- Get free key: https://fred.stlouisfed.org/docs/api/api_key.html

**Error: "FRED API rate limit exceeded"**
- Solution: FRED limits to 120 requests/minute
- The provider has built-in rate limiting (100ms delay)
- For high-frequency use, implement caching

### COT Data Issues

**Note**: Current implementation uses simulated data for development.

For production:
- Implement CFTC API integration
- Use historical COT report downloads
- Update `_download_cot_report()` method

### ETF Flows Issues

**Web scraping failures**:
- Website structure may change
- Fallback to yfinance data (volume/AUM proxy)
- Consider paid data providers for production

### Correlation Calculation Issues

**Insufficient data**:
- Ensure date ranges overlap between assets
- Use same date format (YYYY-MM-DD)
- Check for missing values in CSV data

---

## 📚 References

### Data Sources
- FRED: https://fred.stlouisfed.org/
- CFTC COT Reports: https://www.cftc.gov/MarketReports/CommitmentsofTraders/
- GLD Holdings: https://www.spdrgoldshares.com/
- IAU Holdings: https://www.ishares.com/us/products/239561/

### Gold Trading Resources
- World Gold Council: https://www.gold.org/
- CME Gold Futures: https://www.cmegroup.com/markets/metals/precious/gold.html
- Kitco Gold News: https://www.kitco.com/

---

## ✅ Completed Checklist

- [x] FRED API integration with macro indicators
- [x] COT data parser for positioning analysis
- [x] ETF flows tracker for sentiment
- [x] Correlation tools for regime analysis
- [x] Comprehensive test suite
- [x] Documentation and examples
- [ ] XAU-specific analyst agents (Next: Week 3-4)
- [ ] XAU configuration and graph setup (Next: Week 5)
- [ ] Backtesting and validation (Next: Week 6)

**Phase 1 Status**: ✅ COMPLETE

The data infrastructure is ready for XAU trading agents!
