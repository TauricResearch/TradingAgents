
# XAU Data Layer - Quick Reference Card

**One-page cheatsheet for XAU trading data**

---

## 🚀 Quick Start

```bash
# 1. Setup
cp .env.example .env
# Add FRED_API_KEY to .env (get free at fred.stlouisfed.org)

# 2. Test
python test_xau_data_layer.py

# 3. Use in code
from tradingagents.dataflows.fred_api import get_dxy_data
from tradingagents.dataflows.cot_data import get_cot_positioning
from tradingagents.dataflows.etf_flows import get_gold_etf_flows
```

---

## 📊 Data Sources at a Glance

| Source | What It Provides | Why It Matters | Key Metric |
|--------|-----------------|----------------|------------|
| **FRED** | DXY, yields, CPI, VIX | Macro drivers | DXY ↓ = Gold ↑ |
| **COT** | Futures positioning | Contrarian signals | >90th %ile = reversal |
| **ETF** | GLD/IAU flows | Institutional sentiment | Inflows = bullish |
| **Correlation** | Asset relationships | Trade filters | Gold-DXY: -0.75 |

---

## 🔑 Essential Functions

### Macro Data (FRED)
```python
from tradingagents.dataflows.fred_api import *

# Most important for gold
get_dxy_data(start, end)           # US Dollar Index
get_real_yields(start, end)        # Real yields (gold's opportunity cost)
get_inflation_data(start, end)     # CPI, PCE inflation metrics

# Other macro
get_fred_series("VIX", start, end)        # Risk sentiment
get_fred_series("FED_FUNDS", start, end)  # Fed rate
get_fred_series("10Y_YIELD", start, end)  # Treasury yield
```

### Positioning Data
```python
from tradingagents.dataflows.cot_data import *
from tradingagents.dataflows.etf_flows import *

# COT (weekly)
get_cot_positioning("GOLD", start, end)
analyze_cot_extremes(current_date, lookback_years=3)

# ETF flows (daily)
get_gold_etf_flows("GLD", start, end)
get_gold_etf_flows("IAU", start, end)
get_gold_etf_summary(start, end)
```

### Correlation Analysis
```python
from tradingagents.dataflows.correlation_tools import *

# Quick correlation
calculate_asset_correlation(gold_csv, dxy_csv, window_days=90)

# Comprehensive analysis
analyze_gold_macro_correlations(gold_csv, dxy_csv, yields_csv, vix_csv)

# Regime detection
check_correlation_regime(gold_csv, dxy_csv)
```

---

## 💡 Gold Trading Decision Framework

### 1. Macro Environment Check
```python
✅ BULLISH SETUP:
- DXY falling (USD weakness)
- Real yields negative (no opportunity cost)
- CPI rising (inflation hedge demand)
- VIX elevated (safe-haven bid)

❌ BEARISH SETUP:
- DXY rallying (USD strength)
- Real yields rising (bonds attractive)
- CPI falling (no inflation fears)
- VIX low (risk-on, equities preferred)
```

### 2. Positioning Check (Contrarian)
```python
⚠️ EXTREME LONGS (>90th percentile):
- Large specs heavily long in COT
- GLD holdings at multi-year highs
→ Crowded trade, potential reversal

💡 EXTREME SHORTS (<10th percentile):
- Large specs heavily short
- GLD outflows for weeks
→ Washed out, potential bottom
```

### 3. Correlation Filter
```python
if gold_dxy_corr < -0.6:
    # Healthy relationship
    if dxy_falling:
        increase_conviction()
    else:
        reduce_size()
else:
    # Correlation breakdown
    identify_new_driver()  # Geopolitics? Inflation surprise?
```

---

## 📈 Expected Gold Correlations

| Indicator | Expected Corr | Strength | Interpretation |
|-----------|--------------|----------|----------------|
| DXY | **-0.75** | Strong | USD ↑ → Gold ↓ |
| Real Yields | **-0.85** | Very Strong | Yields ↑ → Gold ↓ |
| VIX | **+0.40** | Moderate | Fear ↑ → Gold ↑ |
| SPY | **-0.20** | Weak | Stocks ↑ → Gold ↓ |
| CPI | **+0.60** | Moderate | Inflation ↑ → Gold ↑ |

---

## 🎯 Key Gold Levels & Thresholds

### Real Yields
- **< 0%**: Structural tailwind (no cost to hold gold)
- **0-1%**: Neutral
- **> 1%**: Headwind (bonds more attractive)

### DXY Levels (example - update based on current levels)
- **< 100**: Weak USD, gold bullish
- **100-105**: Neutral zone
- **> 105**: Strong USD, gold bearish

### COT Positioning (Net Long)
- **> 200k contracts**: Extremely bullish (contrarian bearish)
- **50k-150k**: Normal range
- **< 0 (net short)**: Extremely bearish (contrarian bullish)

### GLD Holdings
- **> 1000 tonnes**: Very high investor interest
- **800-1000 tonnes**: Elevated interest
- **< 800 tonnes**: Lower interest

---

## 🔧 Common Patterns

### Pattern 1: Macro Tailwind Alignment
```
DXY falling + Real yields negative + CPI rising
→ STRONG BULLISH (all factors aligned)
```

### Pattern 2: Divergence (Reversal Signal)
```
Gold rising + GLD outflows + COT extreme longs
→ DISTRIBUTION, potential top
```

### Pattern 3: Correlation Regime Change
```
Gold-DXY correlation weakens from -0.8 to -0.3
→ Check for new driver (geopolitics, inflation surprise)
```

---

## 🧪 Testing Checklist

```bash
# Quick validation
python test_xau_data_layer.py

# Should see:
✅ FRED API tests PASSED
✅ COT data tests PASSED
✅ ETF flows tests PASSED
✅ Correlation tools tests PASSED
✅ Integration test PASSED
```

---

## 🐛 Troubleshooting

| Error | Solution |
|-------|----------|
| `FRED API key required` | Add `FRED_API_KEY` to `.env` |
| `Rate limit exceeded` | Wait 1 minute, retry (120 req/min limit) |
| `No data available` | Check date format (YYYY-MM-DD) |
| `Correlation calculation failed` | Ensure date ranges overlap |

---

## 📚 Resources

- **FRED Data**: https://fred.stlouisfed.org/
- **COT Reports**: https://www.cftc.gov/MarketReports/CommitmentsofTraders/
- **GLD Holdings**: https://www.spdrgoldshares.com/
- **Design Doc**: `XAU_SYSTEM_DESIGN.md`
- **Full Guide**: `XAU_DATA_LAYER_README.md`

---

## 🎯 Next Phase Preview

**Phase 2**: Create XAU-specific agents that USE this data:

1. **XAU Macro Analyst** → Uses FRED data
2. **XAU Positioning Analyst** → Uses COT + ETF data
3. **XAU Market Analyst** → Uses correlations for filtering
4. **XAU News Analyst** → Monitors geopolitical catalysts

---

**Quick Start Example**:
```python
from tradingagents.dataflows.fred_api import get_dxy_data, get_real_yields
from tradingagents.dataflows.etf_flows import get_gold_etf_flows

# Check macro environment for gold trade
dxy = get_dxy_data("2024-01-01", "2024-05-10")
yields = get_real_yields("2024-01-01", "2024-05-10")
flows = get_gold_etf_flows("GLD", "2024-01-01", "2024-05-10")

# Decision:
# If DXY ↓ + Real Yields < 0 + GLD Inflows → BULLISH
```

---

**Phase 1 Status**: ✅ COMPLETE - All data sources ready for agent integration!
