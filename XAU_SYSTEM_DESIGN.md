# XAU (Gold) Trading System - Design Document

**Author**: Claude Code
**Date**: October 6, 2025
**Asset**: XAU/USD (Gold Spot)
**Framework**: TradingAgents Multi-Agent LLM System

---

## 📋 Executive Summary

Design a specialized multi-agent trading system for XAU (Gold) that leverages the existing TradingAgents framework with gold-specific enhancements. Gold trading requires unique considerations due to its role as a safe-haven asset, sensitivity to macro factors (USD, inflation, geopolitics), and different technical behavior compared to equities.

---

## 🎯 Objectives

1. **Adapt TradingAgents framework** for commodity/forex trading (XAU/USD pair)
2. **Enhance analyst agents** with gold-specific indicators and macro factors
3. **Add gold-specific data sources** (DXY, real yields, central bank activity, geopolitical events)
4. **Optimize for gold's unique characteristics** (24/5 trading, safe-haven flows, correlation dynamics)
5. **Create specialized prompts** for gold market analysis

---

## 🏗️ System Architecture

### Current Framework Adaptation

**Existing Flow** (unchanged):
```
Analyst Team → Research Team → Trader → Risk Management → Portfolio Manager
```

**XAU-Specific Enhancements**:
1. Gold-specific technical indicators
2. Macro factor integration (USD Index, Treasury Yields, Fed Policy)
3. Geopolitical event monitoring
4. Correlation analysis tools
5. Safe-haven flow detection

---

## 📊 Component Design

### 1. Enhanced Analyst Team

#### A. Market Analyst (Technical) - **XAU Specialization**

**Current**: Uses equity-focused indicators (RSI, MACD, Bollinger Bands, SMA/EMA)

**XAU Enhancements**:

**Gold-Specific Technical Indicators**:
- **Pivot Points** (S1, S2, S3, R1, R2, R3) - Gold respects technical levels strongly
- **ATR (Average True Range)** - Critical for gold's volatility assessment
- **Ichimoku Cloud** - Popular in forex/commodity trading
- **Fibonacci Retracements** - Gold frequently respects Fib levels
- **Volume Profile / Volume Weighted Average Price (VWAP)** - Institutional participation
- **Bollinger Band Width** - Volatility breakout detection

**Timeframe Analysis**:
- Multi-timeframe approach: 1H, 4H, Daily, Weekly
- Key support/resistance from higher timeframes
- Trend alignment across timeframes

**Implementation**:
```python
# tradingagents/agents/analysts/xau_market_analyst.py
- Extended indicator list specific to gold
- Multi-timeframe analysis capability
- Support/resistance level identification
- Chart pattern recognition (double top/bottom, H&S for gold)
```

---

#### B. Fundamentals Analyst - **Macro-Focused for Gold**

**Current**: Analyzes company earnings, balance sheets, P/E ratios (equity-focused)

**XAU Transformation** → **Macro Fundamentals Analyst**:

**Primary Macro Drivers**:

1. **US Dollar Index (DXY)**
   - Inverse correlation with gold (~-0.7 to -0.9)
   - Track DXY technical levels and trends
   - Monitor USD strength/weakness narratives

2. **Real Treasury Yields** (10-Year TIPS)
   - Gold's opportunity cost metric
   - Negative yields = bullish for gold
   - Track yield curve dynamics

3. **Federal Reserve Policy**
   - Interest rate decisions and forward guidance
   - QE/QT programs (liquidity conditions)
   - Fed speak and policy pivot signals
   - FOMC meeting minutes and dot plot

4. **Inflation Indicators**
   - CPI, Core CPI, PCE (Fed's preferred metric)
   - Inflation expectations (breakeven rates)
   - Producer prices (PPI)

5. **Central Bank Activity**
   - Central bank gold purchases (demand driver)
   - Reserve diversification trends
   - CBGA (Central Bank Gold Agreement) updates

6. **Geopolitical Risk**
   - Conflicts, sanctions, trade wars
   - Political instability events
   - Currency crisis developments

**Data Sources**:
- FRED (Federal Reserve Economic Data) API
- Alpha Vantage for forex/macro data (DXY, USD pairs)
- Custom news scraping for geopolitical events
- CME FedWatch Tool data (rate probabilities)

**Implementation**:
```python
# tradingagents/agents/analysts/xau_macro_analyst.py (NEW)
# Replace fundamentals_analyst for XAU trading
- USD Index trend analysis
- Real yield calculation and trends
- Fed policy stance interpretation
- Inflation regime assessment
- Geopolitical risk scoring
```

---

#### C. News Analyst - **Gold-Specific Focus**

**Current**: General market news monitoring

**XAU Enhancements**:

**Targeted News Sources**:
- **Central Bank Communications**: Fed, ECB, BoE, PBoC statements
- **Geopolitical Developments**: Conflicts, sanctions, safe-haven triggers
- **Inflation Reports**: CPI, PCE releases and surprises
- **US Dollar Events**: Economic data affecting USD (NFP, GDP, retail sales)
- **Mining Supply News**: Major producer disruptions, strikes
- **ETF Flows**: GLD, IAU inflow/outflow trends (sentiment indicator)

**Sentiment Analysis Categories**:
- Safe-haven demand (bullish)
- Risk-on sentiment (bearish)
- Inflation concerns (bullish)
- USD strength narratives (bearish)
- Central bank hawkish/dovish tone

**Implementation**:
```python
# tradingagents/agents/analysts/xau_news_analyst.py
- Geopolitical event detection and impact scoring
- Central bank communication parsing
- Macro data release monitoring
- Gold-specific keyword filtering
```

---

#### D. Sentiment Analyst - **COT & Positioning**

**Current**: Social media sentiment for equities

**XAU Transformation** → **Market Positioning Analyst**:

**Data Sources**:

1. **COT Report (Commitment of Traders)**
   - Large Speculators net positioning
   - Commercials (producers/refiners) hedging activity
   - Extreme positioning as contrarian indicator
   - Week-over-week changes in open interest

2. **Gold ETF Flows**
   - GLD (SPDR Gold Shares) holdings trends
   - IAU (iShares Gold Trust) flows
   - Daily/weekly net inflows as sentiment

3. **Options Market**
   - GLD/GC options: Put/Call ratio
   - Implied volatility (GVZ - Gold VIX)
   - Skew analysis (demand for upside vs downside)

4. **Social Sentiment** (Secondary)
   - FinTwit gold discussions (Twitter/X)
   - Reddit r/Gold, r/wallstreetbets mentions
   - Institutional research sentiment from Seeking Alpha, Bloomberg

**Implementation**:
```python
# tradingagents/agents/analysts/xau_positioning_analyst.py
- COT report parsing and trend analysis
- ETF flow tracking
- Options sentiment metrics
- Contrarian positioning signals
```

---

### 2. Research Team - **Gold Context**

**Bull Researcher**:
- Emphasize safe-haven narratives
- Inflation hedge thesis
- USD weakness scenarios
- Central bank demand trends
- Technical breakout potential

**Bear Researcher**:
- Opportunity cost arguments (rising real yields)
- Risk-on equity market strength
- USD strength cases
- Profit-taking from overbought levels
- Technical resistance failures

**Research Manager**:
- Synthesize macro vs technical signals
- Weight fundamental drivers appropriately
- Consider gold's dual nature (commodity + safe-haven)

---

### 3. Trading Team - **XAU Execution**

**Trader Agent Enhancements**:

**Position Sizing for Gold**:
- Account for higher volatility vs equities (1-2% daily moves common)
- Use ATR-based position sizing
- Respect gold's leverage conventions (100:1 in forex)

**Entry/Exit Refinement**:
- Key round numbers (1900, 2000, 2100, etc.) as psychological levels
- London Fix times (10:30 AM, 3:00 PM London) - high liquidity periods
- Avoid thin liquidity periods (Asian session gaps)

**Stop Loss Strategies**:
- ATR-based stops (2x-3x ATR from entry)
- Technical stops (below/above key S/R)
- Volatility-adjusted trailing stops

**Time Horizon Considerations**:
- Intraday: 1H-4H trends
- Swing: Daily-Weekly trends
- Position: Monthly macro themes

---

### 4. Risk Management - **Gold-Specific Risks**

**Unique Gold Risks**:

1. **Flash Crashes**: Gold prone to liquidity gaps (e.g., May 2021 flash crash)
2. **Overnight Gaps**: 24/5 trading means weekend geopolitical gaps
3. **USD Correlation**: Strong negative correlation can amplify moves
4. **Volatility Spikes**: VIX spikes → gold volatility spikes
5. **Macro Event Risk**: FOMC, CPI, NFP can cause 2-5% moves

**Risk Management Enhancements**:

**Aggressive Analyst**:
- Leverage up during strong macro tailwinds (QE environments)
- Ride momentum in safe-haven flows
- Scale into breakouts of multi-year resistances

**Conservative Analyst**:
- Reduce size around FOMC, CPI releases
- Respect ATR-based stops strictly
- Exit partial positions at Fibonacci resistance levels
- Avoid trading during thin liquidity (holiday periods)

**Neutral Analyst**:
- Balance technical signals with macro backdrop
- Use correlation filters (if DXY rallying hard, be cautious on gold longs)
- Monitor VIX for risk-off confirmations

---

## 🔧 Technical Implementation Plan

### Phase 1: Data Layer Enhancement

**New Data Vendors** (`tradingagents/dataflows/`):

1. **`fred_api.py`** - Federal Reserve Economic Data
   - DXY (US Dollar Index)
   - 10-Year Treasury Yield
   - 10-Year TIPS (real yields)
   - CPI, PCE, PPI data
   - Fed Funds Rate

2. **`forex_data.py`** - Forex/Commodity Data
   - XAU/USD from Alpha Vantage or OANDA API
   - EUR/USD, GBP/USD for correlation
   - Gold futures (GC) data from CME

3. **`cot_data.py`** - Commitment of Traders
   - CFTC COT report parsing
   - Net positioning calculations
   - Historical extremes tracking

4. **`etf_flows.py`** - Gold ETF Holdings
   - GLD holdings scraping (from SPDR website)
   - IAU holdings tracking
   - Daily/weekly flow calculations

**Data Abstraction Update** (`tradingagents/agents/utils/agent_utils.py`):
```python
# New abstract tool functions
def get_macro_data(indicator: str, start_date: str, end_date: str) -> str:
    """Fetch macro data (DXY, yields, CPI, etc.)"""

def get_cot_data(asset: str, lookback_weeks: int) -> str:
    """Fetch COT positioning data"""

def get_etf_flows(etf_ticker: str, start_date: str, end_date: str) -> str:
    """Track ETF inflows/outflows"""

def get_correlation(asset1: str, asset2: str, window: int) -> float:
    """Calculate rolling correlation between assets"""
```

---

### Phase 2: Agent Specialization

**Create XAU-Specific Agent Files**:

1. **`tradingagents/agents/analysts/xau_market_analyst.py`**
   - Gold-specific technical indicators
   - Multi-timeframe analysis
   - Key level identification (Fibonacci, pivots)
   - Chart pattern recognition

2. **`tradingagents/agents/analysts/xau_macro_analyst.py`** (replaces fundamentals)
   - USD Index analysis
   - Real yields calculation and trend
   - Fed policy stance interpretation
   - Inflation regime assessment
   - Central bank activity monitoring

3. **`tradingagents/agents/analysts/xau_news_analyst.py`**
   - Geopolitical event filtering
   - Macro data release monitoring
   - Central bank communication parsing
   - Safe-haven narrative detection

4. **`tradingagents/agents/analysts/xau_positioning_analyst.py`** (replaces social)
   - COT report analysis
   - ETF flow tracking
   - Options sentiment (Put/Call, IV)
   - Contrarian signals from extremes

**Prompt Engineering** (System Messages):

Each XAU agent gets gold-specific system prompts:
- Market Analyst: "You are analyzing XAU/USD (Gold). Gold is a safe-haven asset highly sensitive to USD strength, real yields, and geopolitical risk..."
- Macro Analyst: "Your role is to assess fundamental drivers of gold prices: USD Index, real yields, Fed policy, inflation, central bank demand, geopolitical risk..."
- News Analyst: "Monitor news for gold-specific catalysts: Fed communications, inflation surprises, geopolitical crises, USD-impacting events..."
- Positioning Analyst: "Analyze market positioning through COT data, ETF flows, and options. Extreme positioning can signal reversals..."

---

### Phase 3: Configuration & Integration

**XAU-Specific Config** (`tradingagents/xau_config.py`):
```python
XAU_CONFIG = DEFAULT_CONFIG.copy()

# Override data vendors for XAU-specific sources
XAU_CONFIG["data_vendors"] = {
    "core_stock_apis": "alpha_vantage",  # For XAU/USD price data
    "technical_indicators": "yfinance",   # Or custom forex indicators
    "fundamental_data": "fred",           # Macro data from FRED
    "news_data": "alpha_vantage",         # Keep existing
    "macro_data": "fred",                 # NEW: FRED for macro
    "positioning_data": "cot_api",        # NEW: COT data
    "etf_data": "scraper",                # NEW: ETF flows
}

# XAU-specific parameters
XAU_CONFIG["asset_class"] = "commodity"
XAU_CONFIG["trading_hours"] = "24/5"  # Sunday 5pm - Friday 5pm ET
XAU_CONFIG["tick_size"] = 0.01
XAU_CONFIG["contract_size"] = 100  # oz for futures
XAU_CONFIG["max_leverage"] = 50  # Conservative for retail

# Risk parameters tuned for gold volatility
XAU_CONFIG["max_position_size_pct"] = 2.0  # % of portfolio
XAU_CONFIG["atr_multiplier_stop"] = 2.5    # ATR-based stops
XAU_CONFIG["correlation_threshold"] = -0.6  # DXY correlation filter
```

**Graph Setup for XAU** (`tradingagents/graph/xau_graph.py`):
```python
class XAUTradingGraph(TradingAgentsGraph):
    """Specialized graph for XAU trading"""

    def __init__(self, debug=False, config=None):
        # Use XAU-specific analysts
        xau_analysts = ["xau_market", "xau_macro", "xau_news", "xau_positioning"]

        # Initialize with XAU config
        xau_config = config or XAU_CONFIG

        super().__init__(
            selected_analysts=xau_analysts,
            debug=debug,
            config=xau_config
        )

    def _create_tool_nodes(self):
        """Override to include XAU-specific tools"""
        return {
            "xau_market": ToolNode([
                get_stock_data,       # XAU/USD price data
                get_indicators,       # Technical indicators
                get_correlation,      # NEW: Correlation analysis
            ]),
            "xau_macro": ToolNode([
                get_macro_data,       # NEW: DXY, yields, CPI
                get_news,             # Macro news
            ]),
            "xau_news": ToolNode([
                get_news,
                get_global_news,
            ]),
            "xau_positioning": ToolNode([
                get_cot_data,         # NEW: COT report
                get_etf_flows,        # NEW: GLD/IAU flows
            ]),
        }
```

---

### Phase 4: Execution & Backtesting

**Entry Point** (`xau_main.py`):
```python
from tradingagents.graph.xau_graph import XAUTradingGraph
from tradingagents.xau_config import XAU_CONFIG
from dotenv import load_dotenv

load_dotenv()

# Initialize XAU-specific graph
xau_system = XAUTradingGraph(debug=True, config=XAU_CONFIG)

# Run analysis
trade_date = "2024-05-10"
final_state, decision = xau_system.propagate("XAU", trade_date)

print(f"Gold Trading Decision for {trade_date}:")
print(decision)

# Optionally backtest on historical data
# xau_system.backtest(start_date="2023-01-01", end_date="2024-12-31")
```

**CLI Enhancement** (`cli/xau_main.py`):
```python
# Add XAU mode to existing CLI
@app.command()
def xau():
    """Run XAU (Gold) trading analysis"""
    # Use XAU-specific workflow
    # Select macro factors instead of equity analysts
    # Display gold-specific metrics (DXY correlation, real yields, COT)
```

---

## 📈 Gold-Specific Features

### 1. Macro Dashboard

Real-time dashboard showing:
- **DXY (US Dollar Index)**: Current level, trend, support/resistance
- **10Y Real Yield**: Current level, direction, historical context
- **Fed Funds Rate**: Current rate, expected changes (CME FedWatch)
- **CPI (YoY)**: Latest inflation reading, trend
- **XAU/DXY Correlation**: Rolling 30/60/90 day correlation
- **VIX**: Risk sentiment proxy

### 2. COT Positioning Indicator

- Large Spec Net Positioning (Long - Short)
- Commercials Positioning (hedging activity)
- Percentile ranking (is positioning extreme?)
- Week-over-week changes
- Contrarian signals (extreme long = caution, extreme short = opportunity)

### 3. Multi-Timeframe Technical Analysis

**Timeframe Alignment**:
- **Weekly**: Major trend direction (above/below 200 SMA)
- **Daily**: Intermediate trend and key S/R levels
- **4H**: Entry/exit timing, momentum shifts
- **1H**: Precision entries, stop placement

**Confluence Zones**:
- Identify areas where multiple timeframes show S/R
- Fibonacci + pivot + moving average confluence
- Volume profile nodes (high activity zones)

### 4. Correlation Filters

**Pre-Trade Checks**:
- If DXY rallying strongly (+0.5% day) → reduce gold long conviction
- If DXY breaking down → increase gold long conviction
- If VIX spiking (risk-off) → gold should benefit (safe-haven check)
- If real yields rising → headwind for gold

**Dynamic Position Sizing**:
- Increase size when macro tailwinds align (weak USD + rising inflation + dovish Fed)
- Reduce size when macro headwinds present (strong USD + rising real yields + hawkish Fed)

---

## 🧪 Testing & Validation

### Backtesting Strategy

**Historical Periods to Test**:
1. **QE Environment (2020-2021)**: Gold rally to $2075
2. **Rate Hike Cycle (2022-2023)**: Gold decline to $1620, then recovery
3. **Geopolitical Crisis (Feb 2022)**: Russia-Ukraine invasion safe-haven spike
4. **Inflation Surge (2021-2022)**: CPI spike and gold's response

**Metrics to Track**:
- Win rate on BUY/SELL signals
- Average holding period
- Max drawdown during trending vs ranging markets
- Signal quality during high-volatility events (FOMC, CPI)
- Correlation to actual XAU/USD price changes

### Paper Trading

Before live deployment:
1. Run system daily for 3 months
2. Track hypothetical P&L vs actual gold moves
3. Analyze false signals and improve filters
4. Refine risk management (stop sizes, position sizing)

---

## 🚀 Implementation Roadmap

### Week 1-2: Data Infrastructure
- [ ] Implement FRED API integration (`fred_api.py`)
- [ ] Implement COT data parser (`cot_data.py`)
- [ ] Implement ETF flows scraper (`etf_flows.py`)
- [ ] Add correlation calculation tools
- [ ] Test all data sources with historical queries

### Week 3-4: Agent Specialization
- [ ] Create `xau_market_analyst.py` with gold-specific indicators
- [ ] Create `xau_macro_analyst.py` for fundamental drivers
- [ ] Create `xau_news_analyst.py` with geopolitical focus
- [ ] Create `xau_positioning_analyst.py` for COT/ETF analysis
- [ ] Write comprehensive prompts for each agent

### Week 5: Integration & Configuration
- [ ] Create `xau_config.py` with gold-specific parameters
- [ ] Create `XAUTradingGraph` class
- [ ] Update tool routing for XAU-specific data
- [ ] Create `xau_main.py` entry point
- [ ] Test end-to-end flow with sample dates

### Week 6: Testing & Refinement
- [ ] Backtest on 2020-2024 historical data
- [ ] Analyze signal quality and edge cases
- [ ] Refine prompts based on output quality
- [ ] Optimize debate rounds and research depth
- [ ] Document findings and adjust parameters

### Week 7-8: CLI & Deployment
- [ ] Enhance CLI with XAU mode
- [ ] Create macro dashboard visualization
- [ ] Add real-time monitoring scripts
- [ ] Setup paper trading pipeline
- [ ] Create user documentation

---

## 📋 Key Decisions & Trade-offs

### 1. **Fundamental Analysis Approach**
- **Decision**: Replace equity fundamentals analyst with macro analyst
- **Rationale**: Gold doesn't have earnings/revenue; macro factors drive price
- **Trade-off**: Lose equity analysis capability in XAU mode (acceptable - focused system)

### 2. **Data Vendor Selection**
- **Decision**: Use FRED for macro data, custom scrapers for COT/ETF
- **Rationale**: Free, reliable, comprehensive coverage
- **Trade-off**: Rate limits on FRED (acceptable with caching), scraping fragility (mitigate with fallbacks)

### 3. **Timeframe Focus**
- **Decision**: Multi-timeframe (1H, 4H, Daily, Weekly)
- **Rationale**: Gold respects technical levels across timeframes
- **Trade-off**: Increased complexity, potential conflicting signals (resolve with hierarchy: Weekly > Daily > 4H > 1H)

### 4. **Research Depth**
- **Decision**: Keep debate rounds at 1-2 for cost efficiency
- **Rationale**: Gold has clearer macro drivers than equities; less debate needed
- **Trade-off**: May miss nuanced scenarios (acceptable - can increase for critical periods)

### 5. **Real-time vs EOD Analysis**
- **Decision**: Start with EOD (end-of-day) analysis
- **Rationale**: Easier to implement, sufficient for swing trading
- **Trade-off**: Miss intraday opportunities (acceptable for Phase 1; add real-time in Phase 2)

---

## 🎯 Success Metrics

### Quantitative Metrics
- **Signal Accuracy**: >60% directional accuracy on daily moves
- **Macro Alignment**: >75% of signals align with dominant macro regime
- **Risk-Adjusted Returns**: Sharpe ratio >1.0 in backtests
- **Drawdown**: Max drawdown <15% in backtests

### Qualitative Metrics
- **Report Quality**: Coherent, actionable macro narratives
- **Risk Awareness**: Proper identification of geopolitical/macro risks
- **Timing**: Signals generated before major moves (leading, not lagging)
- **Consistency**: Stable performance across different market regimes

---

## 📚 Resources & References

### Gold Market Fundamentals
- World Gold Council: https://www.gold.org/
- LBMA (London Bullion Market Association): https://www.lbma.org.uk/
- GLD ETF Holdings: https://www.spdrgoldshares.com/

### Macro Data Sources
- FRED (Federal Reserve): https://fred.stlouisfed.org/
- CME FedWatch: https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html
- CFTC COT Reports: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm

### Technical Analysis
- TradingView (Gold charts): https://www.tradingview.com/symbols/XAUUSD/
- Investing.com (Gold real-time): https://www.investing.com/commodities/gold

---

## 🔄 Next Steps After Planning

1. **Review this design** with stakeholders/users
2. **Prioritize features** (MVP vs nice-to-have)
3. **Set up development environment** (API keys, test data)
4. **Begin Week 1 implementation** (Data Infrastructure)
5. **Iterate based on testing feedback**

---

**END OF DESIGN DOCUMENT**

This design provides a comprehensive blueprint for building a gold-specific trading system. The modular approach allows incremental development while maintaining compatibility with the existing TradingAgents framework.
