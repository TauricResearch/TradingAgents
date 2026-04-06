## Comprehensive Plan: Customizing the Repository for Forex Trading

### TL;DR
Transform the equity-focused trading agents architecture into a multi-asset system supporting forex by:
1. Creating an abstract `Instrument` layer (equity vs currency pairs)
2. Establishing a unified configuration framework
3. Implementing forex-specific data integrations
4. Building forex-aware agents with proper leverage & commission handling
5. Adding 24/5 market monitoring and compliance features

---

## Architecture Overview

### Current State (Equity-Focused)
- Agents designed for stock trading (tickers, market hours, fundamental analysis)
- Data models assume single market open/close times
- Risk management tailored to equity leverage constraints

### Target State (Multi-Asset)
- Agents agnostic to instrument type (extensible to stocks, forex, crypto, commodities)
- Configuration-driven asset switching
- Specialized risk management rules per asset class

---

## Phase 0: Foundation & Configuration (Effort: 3-4 days) — **CRITICAL PATH**

### 0.1 Create Instrument Abstraction Layer
**Why First**: All downstream phases depend on this abstraction.

**Changes**:
- Create `tradingagents/models/instrument.py`:
  - Base `Instrument` class with common fields (symbol, name, type, exchange)
  - `EquityInstrument` subclass (ticker, sector, fundamentals)
  - `CurrencyPairInstrument` subclass (base currency, quote currency, pip size, lot sizes)
- Update `tradingagents/agents/` to use `Instrument` instead of hardcoded ticker handling

**Concrete Example**:
```python
# tradingagents/models/instrument.py
class Instrument(ABC):
    symbol: str
    name: str
    instrument_type: str  # "EQUITY" | "FOREX"
    
class CurrencyPair(Instrument):
    base_currency: str  # "EUR"
    quote_currency: str  # "USD"
    pip_size: float  # 0.0001 for most pairs, 0.01 for JPY pairs
    standard_lot: float  # 100,000
    mini_lot: float  # 10,000
    micro_lot: float  # 1,000
```

### 0.2 Unified Configuration Schema
**Create**: `tradingagents/config/forex_config.py`

**Config Structure**:
```yaml
trading_mode: "forex"  # or "equity"
forex:
  data_provider: "oanda"  # OANDA, Forex.com, Alpha Vantage
  api_keys:
    oanda: ${OANDA_API_KEY}
    account_id: ${OANDA_ACCOUNT_ID}
  default_leverage: 50  # 1:50 leverage
  max_leverage: 500
  lot_type: "micro"  # micro, mini, standard
  base_currency: "USD"
  trading_pairs:
    - "EUR/USD"
    - "GBP/USD"
    - "USD/JPY"
market_hours:
  forex:
    open: "Sunday 17:00 EST"  # 24/5 market
    close: "Friday 17:00 EST"
```

### 0.3 Multi-Provider API Interface
**Create**: `tradingagents/dataflows/forex_provider_factory.py`

- Implement factory pattern for forex data providers
- Define common interface: `ForexDataProvider`
- Fallback strategy between OANDA and Forex.com APIs

---

## Phase 1: Data Integration (Effort: 5-6 days) — *Parallel with Phase 2*

### 1.1 Forex Data Provider Implementation
**Create New Files**:
- `tradingagents/dataflows/oanda_api.py`
- `tradingagents/dataflows/forexcom_api.py`
- `tradingagents/dataflows/forex_common.py` (shared utilities)

**Implement**:
- Real-time tick data fetching for currency pairs
- Historical candle data (1m, 5m, 15m, 1h, 4h, 1d)
- Bid/ask spread tracking
- Account balance & margin info retrieval

**Concrete Example** (`oanda_api.py`):
```python
class OANDADataProvider(ForexDataProvider):
    def get_candles(self, pair: str, timeframe: str, count: int) -> DataFrame:
        """Fetch historical OHLCV data"""
    
    def get_live_quotes(self, pairs: List[str]) -> Dict[str, Quote]:
        """Get real-time bid/ask for multiple pairs"""
    
    def get_account_info(self) -> AccountInfo:
        """Balance, margin used, available margin"""
```

### 1.2 Forex-Specific Metrics & Normalization
**Update**: `tradingagents/utils/` → Add `forex_metrics.py`

- Pip value calculation (varies by pair and lot size)
- Spread normalization (in pips)
- Slippage tracking
- Margin requirement calculation per position

### 1.3 Data Validation & Error Handling
**Add Tests**: `tests/test_forex_data_sources.py`
- Validate bid/ask < spread tolerance
- Verify pip calculations per pair
- Test data continuity across sessions (no gaps at market open)
- Handle connection failures & API rate limits

**Update**: `dataflows/` error handling for 24/5 operation

---

## Phase 2: Abstraction Refactoring (Effort: 6-8 days) — *Parallel with Phase 1*

### 2.1 Refactor Core Data Models
**Update**:
- `tradingagents/agents/utils/agent_states.py` — Store `Instrument` instead of `ticker`
- `tradingagents/graph/trading_graph.py` — Accept generic instruments
- Agent nodes to work with any `Instrument` subclass

### 2.2 Update Graph Structure
**Modify**: `tradingagents/graph/setup.py`

The analysis graph remains the same, but information flows differently:
- **For Equity**: Pull fundamentals, sector data
- **For Forex**: Pull economic indicators, central bank decisions, geopolitical events

Add conditional logic in `conditional_logic.py` to route instrument-specific analysis.

### 2.3 Refactor Existing Agents
**Update Agents** (in `tradingagents/agents/`):
- `fundamentals_analyst.py` → Skip fundamentals for forex, pull macro data instead
- `market_analyst.py` → Add forex-specific technical analysis (moving averages, Fibonacci, support/resistance)
- `news_analyst.py` → Add economic calendar events, central bank statements
- All agents accept `Instrument` instead of ticker

---

## Phase 3: Forex-Specific Strategy Implementation (Effort: 7-10 days) — *After Phase 1 & 2*

### 3.1 Create Forex Strategy Agents
**New Files**:
- `tradingagents/agents/analysts/forex_technician.py` — Technical analysis for pairs
- `tradingagents/agents/analysts/macro_analyst.py` — Economic data & central bank tracking
- `tradingagents/agents/traders/forex_trader.py` — Pair-specific trading decisions

### 3.2 Implement Trading Strategies
**Extend**: `tradingagents/agents/trader/trader.py`

Strategies:
- **Scalping**: Quick trades on micro-trends (1-5 minute candles)
- **Swing Trading**: Hold 1-3 days on support/resistance breakouts
- **Carry Trade**: Long-term holds with interest rate differentials
- **Mean Reversion**: Identification via RSI, Bollinger Bands

### 3.3 Add Reversal & Position Management
- Support both long & short positions (shorting is standard in forex)
- Trailing stop-loss implementation
- Breakeven adjustments

---

## Phase 4: Risk Management & Position Sizing (Effort: 4-5 days)

### 4.1 Forex-Specific Risk Models
**Update**: `tradingagents/agents/risk_mgmt/`

**New Considerations**:
- **Leverage Risk**: Enforce max leverage per position (e.g., max 5:1 on single pair)
- **Margin Requirements**: Track used margin % (warn if >70% used)
- **Liquidation Limits**: Flag if losses would exceed stop-out level (typically 50% margin)
- **Correlation Risk**: Prevent over-exposure to related pairs (EUR/USD + EUR/GBP)

**Modify Debators**:
- `aggressive_debator.py` → Allow higher leverage (up to 100:1)
- `neutral_debator.py` → Medium leverage (20:1 to 50:1)
- `conservative_debator.py` → Low leverage (1:1 to 10:1), wider stops

### 4.2 Position Sizing Engine
**Create**: `tradingagents/utils/forex_position_sizing.py`

**Algorithm**:
```
position_size = (account_equity × risk_percent × leverage) / (spread_in_pips + stop_loss_in_pips)
```

**Constraints**:
- Risk no more than 1-2% of account per trade
- Minimum position: 1 micro lot
- Maximum position: Limited by leverage & margin available

**Concrete Example**:
```python
def calculate_position_size(
    account_equity: float,
    risk_percent: float = 0.02,  # 2%
    leverage: int = 50,
    stop_loss_pips: int = 50,
    pair: str = "EUR/USD"
) -> float:
    """Returns position in units"""
    pip_value = get_pip_value(pair, lot_size=1000)  # micro lot
    risk_amount = account_equity * risk_percent
    pips_at_risk = stop_loss_pips
    
    position_units = risk_amount / (pip_value * pips_at_risk / leverage)
    return round(position_units / 1000) * 1000  # Round to micro lots
```

### 4.3 Compliance & Regulation
- **FIFO Rule**: Some jurisdictions (US) require First-In-First-Out closing
- **PDT-like Restrictions**: Pattern day trade equivalents for some firms
- Track & log regulatory compliance

---

## Phase 5: Market Monitoring & Operations (Effort: 3-4 days) — *After Phase 1*

### 5.1 24/5 Market Monitoring
**Create**: `tradingagents/utils/market_monitor.py`

- Track trading sessions (London, NYSE, Asia sessions)
- Monitor volatility spikes (especially at session opens)
- Alert on economic calendar events
- Handle disconnections gracefully (reconnect strategy)

### 5.2 Order Execution & Slippage Tracking
**Update**: `tradingagents/agents/trader/trader.py`

- Simulate slippage based on spreads
- Log actual fill prices vs expected
- Track execution quality metrics

### 5.3 Trade Journaling
**Create**: `tradingagents/utils/forex_trade_journal.py`

Log per trade:
- Entry price, spread at entry
- Exit price, slippage impact
- PnL in pips and account currency
- Trade reason (technical signal, macro event, etc.)

---

## Phase 6: User Interface & CLI (Effort: 3-4 days)

### 6.1 CLI Commands
**Update**: `cli/main.py`

**New Commands**:
```bash
trading-agent --mode forex --pair EUR/USD --leverage 50
trading-agent --mode forex --strategy scalping --pairs EUR/USD,GBP/USD
trading-agent --backtest forex --pair EUR/USD --timeframe 1h --start 2024-01-01
```

### 6.2 Configuration Management
**Update**: `cli/config.py`

```python
class ForexConfig:
    provider: str  # "oanda", "forexcom"
    api_key: str
    leverage: int
    pairs: List[str]
    risk_percent: float
    strategy: str
```

### 6.3 Dashboard/Status Display
**Update**: `cli/static/welcome.txt` → Add forex-specific info
- Current positions, open drawdown
- Margin used / available
- Today's PnL tracking

---

## Phase 7: Testing & Backtesting (Effort: 5-6 days) — *Parallel with Phase 6*

### 7.1 Unit Tests
**Create/Update**:
- `tests/test_forex_position_sizing.py`
- `tests/test_instrument_abstraction.py`
- `tests/test_risk_management_forex.py`
- `tests/test_oanda_provider.py`

### 7.2 Backtesting Engine
**Create**: `tradingagents/backtest/forex_backtest.py`

- Load historical forex data
- Simulate trades with realistic spreads & slippage
- Calculate metrics: Sharpe ratio, max drawdown, win rate
- Compare strategies across pairs & timeframes

### 7.3 Integration Tests
- End-to-end trading workflow (signal → order → execution)
- Error recovery (reconnection, partial fills)
- Regulatory compliance checks

---

## Phase 8: Documentation & Deployment (Effort: 2-3 days)

### 8.1 Update README.md
- Forex setup instructions (API signup, credentials)
- Example configurations for different strategies
- Risk disclaimers for leverage trading

### 8.2 API Documentation
- Document new forex data providers
- Agent configuration reference
- Position sizing formula explanation

### 8.3 Deployment
- Docker configuration updates for 24/5 operation
- Environment variable setup (API keys, secrets)
- Monitoring & alerting setup

---

## Dependency Graph & Critical Path

```
Phase 0: Configuration ◄── CRITICAL (blocks everything)
    ↓
    ├─→ Phase 1: Data Integration (5-6 days)
    │   ├─→ Phase 4: Risk Management (4-5 days)
    │
    └─→ Phase 2: Abstraction (6-8 days)
        └─→ Phase 3: Strategy (7-10 days)
        
Phase 5: Monitoring (3-4 days) ◄── After Phase 1
Phase 6: CLI (3-4 days) ◄── After Phase 2 & 3
Phase 7: Testing (5-6 days) ◄── Parallel throughout
Phase 8: Documentation (2-3 days) ◄── Final
```

**Total Sequential Time**: ~8-12 weeks (with parallelization)

---

## MVP vs. Enhancements

### MVP (Phase 0, 1, 2, 3, 4, 5) — **Weeks 1-8**
- Single forex pair (EUR/USD)
- Single provider (OANDA)
- Swing trading strategy only
- Basic risk management (leverage limits, position sizing)
- Backtesting capability

### Phase 1 Enhancement (Week 9+)
- Multi-pair support (5-10 major pairs)
- Strategy selection (scalping, carry trade)
- Economic calendar integration

### Phase 2 Enhancement (Week 12+)
- Second provider (Forex.com)
- Regulatory compliance (FIFO)
- Advanced analytics (correlation heatmaps, volatility skew)

---

## File Structure Summary

```
tradingagents/
├── models/
│   ├── instrument.py          [NEW] Base Instrument, CurrencyPair
├── config/
│   ├── forex_config.py        [NEW] Forex configuration schema
├── dataflows/
│   ├── oanda_api.py           [NEW]
│   ├── forexcom_api.py        [NEW]
│   ├── forex_common.py        [NEW]
│   └── forex_provider_factory.py [NEW]
├── agents/
│   ├── analysts/
│   │   ├── forex_technician.py [NEW]
│   │   └── macro_analyst.py    [NEW]
│   ├── traders/
│   │   └── forex_trader.py     [NEW]
│   └── [UPDATED] All agents refactored for Instrument abstraction
├── utils/
│   ├── forex_position_sizing.py [NEW]
│   ├── forex_metrics.py        [NEW]
│   ├── market_monitor.py       [NEW]
│   ├── forex_trade_journal.py  [NEW]
├── backtest/
│   └── forex_backtest.py       [NEW]
├── graph/
│   └── [UPDATED] Conditional logic for asset-specific analysis
└── llm_clients/
    └── [UPDATED] Model selection for forex context

tests/
├── test_forex_data_sources.py [NEW]
├── test_forex_position_sizing.py [NEW]
├── test_instrument_abstraction.py [NEW]
├── test_risk_management_forex.py [NEW]
└── test_oanda_provider.py [NEW]

cli/
├── [UPDATED] main.py with forex commands
├── [UPDATED] config.py with ForexConfig
└── static/
    └── [UPDATED] welcome.txt
```

---

## Success Criteria

✅ **Phase 0**: Configuration loads without errors, supports multi-provider setup  
✅ **Phase 1**: Real-time data streams for EUR/USD, GBP/USD, USD/JPY  
✅ **Phase 2**: Agents work with any instrument type (equity or forex)  
✅ **Phase 3**: Backtest shows consistent profitability across pairs  
✅ **Phase 4**: No positions exceed max leverage; margin alerts trigger correctly  
✅ **Phase 5**: 24/5 operation handles disconnects gracefully  
✅ **Phase 6**: CLI trades EUR/USD via simulated orders  
✅ **Phase 7**: Test coverage >80% for new modules; backtest results reproducible  
✅ **Phase 8**: Documentation covers all forex features; setup takes <30 min  

---

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Factory pattern for providers | Easy to add new data sources (Forex.com, IB, etc.) |
| Instrument abstraction | Enables future crypto, commodities support |
| Config-driven trading mode | No code changes to switch between forex & equity |
| Micro-lot focus for MVP | Reduces capital requirements, good for testing |
| 24/5 monitoring separate from agents | Decouples market ops from trading logic |
| Backtesting module | Validate strategies before live trading |
| FIFO compliance tracking | Regulatory risk mitigation |

---

## References & Compliance
- **Forex Regulations**: FIFO rules (NFA, Canada), leverage limits by jurisdiction
- **Trading Standards**: ISO 4217 (currency codes), OANDA API v20 spec
- **Risk Management**: Position sizing formulas from "Money Management" (Vince, 1990)
- **Technical Analysis**: Standard forex indicators (RSI, MACD, Bollinger Bands)