# TradingAgents Project Analysis & Crypto Spot Trading Adaptation Plan

## 📊 Project Overview

**TradingAgents** is a sophisticated multi-agent LLM-powered financial trading framework that simulates a real-world trading firm's collaborative decision-making process. The system leverages specialized AI agents to analyze markets, debate strategies, and make informed trading decisions for equity markets.

### 🏗️ Architecture Overview

The framework is built on **LangGraph** and follows a multi-agent architecture where different specialists collaborate to make trading decisions:

```
Data Sources → Analysts → Researchers → Trader → Risk Management → Final Decision
```

## 🔍 Detailed System Analysis

### **Core Components**

#### 1. **Multi-Agent System Architecture**
- **Analyst Team**: 4 specialized analysts (Market, Sentiment, News, Fundamentals)
- **Researcher Team**: Bull & Bear researchers that debate investment strategies
- **Trader Agent**: Makes final trading recommendations based on collective analysis
- **Risk Management**: Evaluates and approves/rejects trading proposals
- **Memory System**: Learns from past decisions to improve future performance

#### 2. **Data Integration Layer** (`tradingagents/dataflows/`)
The system supports multiple data vendors with flexible routing:
- **Core Stock APIs**: yfinance, Alpha Vantage, local data
- **Technical Indicators**: stockstats integration for technical analysis
- **Fundamental Data**: Company financials, balance sheets, cash flow
- **News Data**: Global and company-specific news from multiple sources
- **Social Media**: Reddit sentiment analysis

#### 3. **Agent Specializations**

##### **Analyst Team**
- **Market Analyst** (`analysts/market_analyst.py`):
  - Focuses on technical indicators (MACD, RSI, Bollinger Bands, Moving Averages)
  - Selects up to 8 complementary indicators for analysis
  - Provides detailed trend analysis and market condition assessment

- **Fundamentals Analyst** (`analysts/fundamentals_analyst.py`):
  - Analyzes company financials, balance sheets, cash flow statements
  - Evaluates intrinsic value and identifies financial red flags
  - Provides fundamental strength assessment

- **News Analyst** (`analysts/news_analyst.py`):
  - Monitors global news and macroeconomic indicators
  - Interprets impact of events on market conditions
  - Provides contextual market sentiment

- **Social Media Analyst** (`analysts/social_media_analyst.py`):
  - Analyzes Reddit and social media sentiment
  - Uses sentiment scoring algorithms
  - Gauges short-term market mood and retail investor sentiment

##### **Research & Decision Making**
- **Bull Researcher** (`researchers/bull_researcher.py`): Argues for positive investment opportunities
- **Bear Researcher** (`researchers/bear_researcher.py`): Identifies risks and potential downsides
- **Research Manager** (`managers/research_manager.py`): Facilitates debates and makes investment recommendations

##### **Trading & Risk Management**
- **Trader Agent** (`trader/trader.py`): Makes final BUY/HOLD/SELL decisions
- **Risk Manager** (`managers/risk_manager.py`): Evaluates portfolio risk and provides final approval

#### 4. **Configuration System** (`default_config.py`)
Highly configurable system supporting:
- **LLM Providers**: OpenAI, Anthropic, Google, Ollama, OpenRouter
- **Data Vendors**: Flexible routing between different data providers
- **Debate Parameters**: Configurable rounds and discussion limits

#### 5. **Memory & Learning System** (`agents/utils/memory.py`)
- **Situation Memory**: Stores past trading decisions and outcomes
- **Reflection Mechanism**: Learns from mistakes and successes

### **Key Features**

#### ✅ **Current Strengths**
1. **Multi-Agent Collaboration**: Simulates real trading firm dynamics
2. **Flexible Data Integration**: Multiple vendor support with routing flexibility
3. **Comprehensive Analysis**: Technical, fundamental, news, and sentiment analysis
4. **Learning Capability**: Memory system for continuous improvement
5. **Risk Management**: Built-in risk assessment and approval process
6. **Configurable Architecture**: Easy to customize models, providers, and parameters

#### ⚡ **Technical Architecture**
- **Framework**: LangGraph for workflow orchestration
- **Language**: Python 3.10+
- **Key Dependencies**: LangChain ecosystem, yfinance/Alpha Vantage, stockstats, chromadb

## 🚀 How to Run the Project

### **Prerequisites**
```bash
# Required API Keys
export OPENAI_API_KEY=your_openai_api_key
export ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
```

### **Installation**
```bash
# Clone repository
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents

# Create virtual environment
conda create -n tradingagents python=3.13
conda activate tradingagents

# Install dependencies
pip install -r requirements.txt
```

### **Running Methods**

#### **1. CLI Interface (Recommended for beginners)**
```bash
python -m cli.main
```

#### **2. Python API (For developers)**
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Basic usage
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

## 🔄 Workflow Process

1. **Data Collection**: Gather market data, news, fundamentals
2. **Analyst Reports**: Each specialist generates detailed analysis
3. **Research Debate**: Bull vs Bear researchers debate investment merits
4. **Trading Decision**: Trader agent makes BUY/HOLD/SELL recommendation
5. **Risk Assessment**: Risk manager evaluates and approves/rejects
6. **Memory Update**: System learns from decision outcomes

---

## 💼 Portfolio Management & Crypto Adaptation Requirements

### **🔍 Current System Gaps**
The existing system has **significant limitations** for both portfolio management and crypto trading:

#### **❌ Critical Missing Features**
1. **No Portfolio Context**: Individual decisions without considering current holdings, available capital, or allocation targets
2. **No Position Sizing**: Only BUY/HOLD/SELL signals without dollar amounts or percentages
3. **Equity-Only Focus**: Traditional stock market data, fundamentals, and risk models
4. **Market Hours Limitation**: No 24/7 trading for crypto markets
5. **No Crypto Infrastructure**: Missing exchange integrations, on-chain analytics, DeFi protocols

#### **✅ Strong Foundation to Build Upon**
- Multi-agent collaborative framework
- Memory and learning capabilities
- Flexible data source routing
- Risk assessment and debate mechanisms

---

## **📋 INTEGRATED PROJECT MANAGER ACTION ITEMS**

### **PHASE 1: Portfolio Foundation & Crypto Infrastructure** ⏱️ *3-4 weeks*

#### **🔥 P0 CRITICAL - Portfolio State & Crypto Data**
- [ ] **1.1** Design portfolio state management with crypto infrastructure
  - **Owner**: Architecture Team
  - **Tasks**:
    - Create `PortfolioState` class with crypto holdings, capital allocation, sector targets
    - Add crypto exchange integrations (Binance, Coinbase, CoinGecko)
    - Create `PortfolioManager` agent for allocation decisions and position sizing
    - Implement 24/7 market operations for continuous crypto trading
  - **Acceptance Criteria**: System tracks crypto portfolio with specific dollar allocations

- [ ] **1.2** Replace equity fundamentals with crypto-native analysis
  - **Owner**: Research Team
  - **Tasks**:
    - Replace balance sheets/P&E ratios with on-chain metrics (TVL, active addresses, token economics)
    - Add crypto news sources (CoinDesk, The Block, crypto Twitter)
    - Integrate blockchain analytics (whale tracking, institutional flows)
    - Update technical indicators for crypto markets (funding rates, liquidation levels)
  - **Acceptance Criteria**: Comprehensive crypto analysis with portfolio context

### **PHASE 2: Portfolio-Aware Trading & Risk Management** ⏱️ *3-4 weeks*

#### **⚠️ P0 CRITICAL - Portfolio Trading Integration**
- [ ] **2.1** Implement portfolio-aware crypto trading decisions
  - **Owner**: Trading & Risk Teams
  - **Tasks**:
    - Modify `trader.py` to output specific dollar amounts and position sizes
    - Add portfolio-level risk metrics (VaR, correlation analysis, sector limits)
    - Create dynamic position sizing based on portfolio targets and available capital
    - Implement crypto-specific risk parameters (volatility tolerance, smart contract risk)
    - Add portfolio rebalancing triggers and recommendations
  - **Acceptance Criteria**: Trading decisions include specific dollar allocations with portfolio context

- [ ] **2.2** Create Portfolio Analytics & Rebalancing Engine
  - **Owner**: Portfolio Team  
  - **Tasks**:
    - Create `portfolio_analyst.py` for portfolio health monitoring
    - Implement automated rebalancing logic (trigger when drift >5% from targets)
    - Add sector allocation management (DeFi, L1, L2, Gaming sectors)
    - Create tax-loss harvesting and yield optimization for crypto
    - Generate specific rebalancing recommendations ("sell $X BTC, buy $Y ETH")
  - **Acceptance Criteria**: Complete portfolio management with dollar-specific recommendations

### **PHASE 3: Advanced Features & Optimization** ⏱️ *3-4 weeks*

#### **🔗 P2 MEDIUM - Advanced Crypto Integration**
- [ ] **3.1** DeFi protocol integration and yield optimization
  - **Owner**: DeFi Team
  - **Tasks**:
    - Monitor yield farming opportunities and factor into portfolio allocation decisions
    - Track liquidity mining rewards and governance participation
    - Implement cross-chain bridge monitoring and portfolio optimization
    - Create yield optimization recommendations with capital allocation
  - **Acceptance Criteria**: System optimizes DeFi yields within portfolio constraints

- [ ] **3.2** On-chain analytics with portfolio intelligence
  - **Owner**: Blockchain Team
  - **Tasks**:
    - Create whale wallet tracking relevant to current holdings
    - Add institutional flow analysis for portfolio positioning
    - Create `onchain_analyst.py` for blockchain data analysis
    - Implement smart money following strategies for portfolio assets
  - **Acceptance Criteria**: On-chain data drives portfolio-aware trading decisions

### **PHASE 4: Testing & Deployment** ⏱️ *2-3 weeks*

#### **🧪 P0 CRITICAL - System Validation**
- [ ] **4.1** Comprehensive testing and performance optimization
  - **Owner**: QA & Performance Teams
  - **Tasks**:
    - Create crypto portfolio simulation environment with backtesting
    - Implement stress testing for high volatility periods
    - Optimize for 24/7 operations and real-time portfolio calculations
    - Add integration tests for all crypto data sources and portfolio state
  - **Acceptance Criteria**: System robust with portfolio tracking across market conditions

- [ ] **4.2** Monitoring and analytics deployment
  - **Owner**: DevOps Team
  - **Tasks**:
    - Implement real-time portfolio performance dashboards
    - Add crypto-specific alerting with portfolio impact analysis
    - Create comprehensive trading and portfolio analytics
    - Add compliance monitoring for different jurisdictions
  - **Acceptance Criteria**: Complete monitoring for crypto trading and portfolio management

## **🔧 Technical Implementation Overview**

### **Key File Structure Changes**
```
tradingagents/
├── dataflows/
│   ├── crypto_exchanges.py          # NEW: Binance, Coinbase APIs
│   ├── onchain_analytics.py         # NEW: Glassnode, blockchain data
│   └── portfolio_data.py           # NEW: Portfolio state management
├── agents/
│   ├── analysts/
│   │   ├── crypto_fundamentals_analyst.py  # REPLACE: On-chain metrics
│   │   └── portfolio_analyst.py            # NEW: Portfolio health
│   ├── managers/
│   │   └── portfolio_manager.py            # NEW: Position sizing & allocation
├── configs/
│   └── crypto_portfolio_config.py  # NEW: Targets, limits, parameters
```

### **Portfolio State Integration**
```python
class PortfolioState(TypedDict):
    current_holdings: Dict[str, float]      # {"BTC": 1.5, "ETH": 10.0}
    available_capital: float                # USD available for trading
    allocation_targets: Dict[str, float]    # {"BTC": 0.35, "ETH": 0.25}
    total_portfolio_value: float           # Current portfolio value

class AgentState(MessagesState):
    # ... existing fields ...
    portfolio_state: Annotated[PortfolioState, "Portfolio context"]
    position_size_recommendation: Annotated[float, "USD amount to invest"]
    rebalancing_needed: Annotated[bool, "Portfolio needs rebalancing"]
```

### **Configuration with Portfolio Targets**
```python
CRYPTO_PORTFOLIO_CONFIG = {
    "portfolio_targets": {
        "BTC": 0.35, "ETH": 0.25, "L1_TOKENS": 0.20, 
        "DEFI_TOKENS": 0.15, "STABLECOINS": 0.05
    },
    "available_capital": 50000,            # $50k total
    "max_position_size": 0.10,             # Max 10% per asset
    "rebalancing_threshold": 0.05,         # Rebalance when >5% drift
}
```

## **💡 Portfolio Management Examples**

### **Investment Decision with Portfolio Context**
```
Current: 40% BTC ($20k), 30% ETH ($15k), 30% Cash ($15k)
Signal: "Strong bullish signal for SOL"
Decision: "Allocate $8k to SOL from cash → achieves 16% L1 target allocation"
```

### **Automatic Rebalancing**
```
Current: 50% BTC ($30k), 25% ETH ($15k), 25% MATIC ($15k)
Trigger: BTC 15% over target (35%)
Action: "Sell $9k BTC → Buy $4k DeFi + $3k stables + $2k ETH"
```

### **Risk-Based Position Sizing**
```
Portfolio Risk: High correlation alert (BTC+ETH = 95%)
Decision: "Reduce BTC+ETH from 75% to 50%, increase stables to 20%"
```

## **⚠️ Risk Mitigation Strategies**

1. **Technical Risks**: Implement gradual rollout with feature flags, maintain comprehensive test coverage
2. **Market Risks**: Start with paper trading and simulations, implement conservative position sizing
3. **Operational Risks**: Maintain redundancy across exchanges, implement robust error handling
4. **Portfolio Risks**: Implement maximum position size limits, monitor correlation risks continuously

## **🎯 Success Metrics**

- **Technical**: System uptime > 99.5% for 24/7 operations
- **Performance**: Latency < 100ms for trading decisions
- **Accuracy**: > 90% data quality across all crypto sources
- **Coverage**: Support for top 100 cryptocurrencies by market cap
- **Portfolio**: Maintain target allocations within 5% drift tolerance
- **Risk**: Portfolio maximum drawdown < 20% in stress conditions
- **Performance**: Portfolio Sharpe ratio > 1.5 vs crypto market benchmark

---

*This enhanced adaptation plan transforms TradingAgents into a comprehensive crypto spot trading platform with sophisticated portfolio management capabilities, addressing specific needs for capital allocation, position sizing, and portfolio balancing decisions.*

---

## **🎯 MVP - MILESTONE 1: BTC/USDT Portfolio-Aware Trading**

### **📋 SIMPLIFIED REQUIREMENTS (MVP)**

**Goal**: Enhance existing system to provide BUY/HOLD/SELL recommendations for BTC/USDT with specific dollar amounts based on user's current assets.

#### **MVP Scope - Keep It Simple**
- **Single Pair Focus**: BTC/USDT only
- **Portfolio Awareness**: Track user's current BTC holdings and available USDT
- **Amount-Based Recommendations**: Instead of just "BUY", output "BUY $500 BTC" based on available capital
- **Existing System**: Keep all current agents and analysis - just add portfolio context

#### **🔥 MVP IMPLEMENTATION TASKS** ⏱️ *1-2 weeks*

##### **Task 1.1: Add Portfolio State for BTC/USDT**
```python
# Add to agent_states.py
@dataclass
class BTCPortfolioState:
    btc_balance: float = 0.0          # Current BTC holdings
    usdt_balance: float = 1000.0      # Available USDT for trading
    max_trade_amount: float = 200.0   # Max $ per trade (20% of balance)
    
class AgentState(MessagesState):
    # ... existing fields ...
    btc_portfolio: Annotated[BTCPortfolioState, "BTC portfolio state"]
    trade_amount: Annotated[float, "Dollar amount to trade"]
```

##### **Task 1.2: Modify Trader Agent for Amount-Based Decisions**
```python
# Update trader.py to output specific amounts
def make_decision(self, state):
    portfolio = state["btc_portfolio"]
    
    # Existing BUY/HOLD/SELL logic stays the same
    decision = self.analyze_signals(state)
    
    # NEW: Add dollar amount based on portfolio
    if decision == "BUY":
        max_buy = min(portfolio.usdt_balance, portfolio.max_trade_amount)
        amount = self.calculate_position_size(max_buy, confidence_level)
        return f"BUY ${amount:.0f} BTC"
    
    elif decision == "SELL":
        btc_value = portfolio.btc_balance * current_btc_price
        max_sell = min(btc_value, portfolio.max_trade_amount)
        amount = self.calculate_position_size(max_sell, confidence_level)
        return f"SELL ${amount:.0f} BTC"
    
    else:
        return "HOLD - No position change recommended"
```

##### **Task 1.3: Add BTC Price Data Integration**
```python
# Add to dataflows/crypto_exchanges.py (simple version)
def get_btc_usdt_price():
    """Get current BTC/USDT price from Binance API"""
    import requests
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    response = requests.get(url)
    return float(response.json()['price'])
```

##### **Task 1.4: Update Configuration for MVP**
```python
# Simple MVP config
MVP_CONFIG = {
    "target_pair": "BTC/USDT",
    "initial_usdt_balance": 1000.0,
    "initial_btc_balance": 0.0,
    "max_trade_percentage": 0.20,  # Max 20% of balance per trade
    "data_source": "binance",      # Simple free API
}
```

#### **📊 MVP EXAMPLE OUTPUT**

**Before (Current System)**:
```
Analysis: Strong bullish signals for BTC
Decision: BUY
Risk Assessment: Approved
```

**After (MVP Enhancement)**:
```
Analysis: Strong bullish signals for BTC
Portfolio: $800 USDT available, 0.1 BTC ($4,200) held
Decision: BUY $160 BTC (20% of available USDT)
Risk Assessment: Approved - within position limits
New Portfolio: $640 USDT, ~0.104 BTC after trade
```

#### **🔧 MVP INTEGRATION POINTS**

1. **Minimal Code Changes**: Only modify `agent_states.py`, `trader.py`, and add simple price fetching
2. **Keep Existing Agents**: All analysts, researchers, and risk managers work as-is
3. **Add Portfolio Context**: Just pass portfolio state through existing workflow
4. **Simple UI**: Update CLI to show portfolio status and amount-based recommendations

#### **✅ MVP SUCCESS CRITERIA**

- [ ] System tracks BTC and USDT balances
- [ ] Recommendations include specific dollar amounts: "BUY $200 BTC" or "SELL $150 BTC"
- [ ] Amount calculations respect available balance and risk limits
- [ ] All existing analysis and agent collaboration remains functional
- [ ] Single API integration for BTC/USDT price data

---

## **📋 FULL INTEGRATED PROJECT MANAGER ACTION ITEMS**
5. **Risk Management**: Built-in risk assessment and approval process
6. **Configurable Architecture**: Easy to customize models, providers, and parameters
7. **CLI Interface**: User-friendly command-line interface
8. **Real-time Processing**: Live market data integration

#### ⚡ **Technical Architecture**
- **Framework**: LangGraph for workflow orchestration
- **Language**: Python 3.10+
- **Key Dependencies**: 
  - LangChain ecosystem for LLM integration
  - yfinance/Alpha Vantage for market data
  - stockstats for technical indicators
  - chromadb for memory storage
  - backtrader for trading simulation

## 🚀 How to Run the Project

### **Prerequisites**
```bash
# Required API Keys
export OPENAI_API_KEY=your_openai_api_key
export ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
```

### **Installation**
```bash
# Clone repository
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents

# Create virtual environment
conda create -n tradingagents python=3.13
conda activate tradingagents

# Install dependencies
pip install -r requirements.txt
```

### **Running Methods**

#### **1. CLI Interface (Recommended for beginners)**
```bash
python -m cli.main
```
- Interactive interface for ticker selection, date, LLM choices
- Real-time progress tracking
- Visual display of agent activities

#### **2. Python API (For developers)**
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Basic usage
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# Custom configuration
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 3
ta = TradingAgentsGraph(debug=True, config=config)
```

#### **3. Advanced Configuration**
```python
# Configure data vendors
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance", 
    "fundamental_data": "alpha_vantage",
    "news_data": "alpha_vantage",
}

# Select specific analysts
selected_analysts = ["market", "social", "news", "fundamentals"]
ta = TradingAgentsGraph(
    selected_analysts=selected_analysts,
    debug=True, 
    config=config
)
```

## 🔄 Workflow Process

1. **Data Collection**: Gather market data, news, fundamentals
2. **Analyst Reports**: Each specialist generates detailed analysis
3. **Research Debate**: Bull vs Bear researchers debate investment merits
4. **Trading Decision**: Trader agent makes BUY/HOLD/SELL recommendation
5. **Risk Assessment**: Risk manager evaluates and approves/rejects
6. **Memory Update**: System learns from decision outcomes
7. **Reflection**: Continuous improvement through past experience analysis

---

# 🪙 Crypto Spot Trading Adaptation Plan

## **Current State vs Target State Analysis**

### **Current State** (Equity-Focused)
- ✅ Technical indicators applicable to crypto
- ✅ Multi-agent architecture (transferable)
- ✅ News and sentiment analysis (adaptable)
- ❌ Equity-specific fundamental analysis
- ❌ Stock market data sources only
- ❌ Traditional market hours assumptions
- ❌ Equity-specific risk metrics

### **Target State** (Crypto Spot Trading)
- 🎯 24/7 market operation
- 🎯 Crypto-native fundamental analysis
- 🎯 DeFi and blockchain-specific metrics
- 🎯 Multiple cryptocurrency exchanges
- 🎯 Crypto-specific risk management
- 🎯 Cross-chain analysis capabilities

## 📋 **PROJECT MANAGER ACTION ITEMS**

### **PHASE 1: Infrastructure & Data Layer Migration** ⏱️ *2-3 weeks*

#### **🔥 CRITICAL - Data Source Integration**
- [ ] **1.1** Replace equity data sources with crypto exchanges
  - **Priority**: P0 (Blocking)
  - **Owner**: Backend Team
  - **Tasks**:
    - Integrate Binance API for spot trading data
    - Add Coinbase Pro/Advanced Trade API
    - Implement CoinGecko for market data and metadata
    - Add CryptoCompare for historical data
    - Create crypto data source routing in `tradingagents/dataflows/crypto_exchanges.py`
  - **Acceptance Criteria**: System can fetch OHLCV data for major crypto pairs

- [ ] **1.2** Modify technical indicators for crypto markets
  - **Priority**: P0 (Blocking)
  - **Owner**: Quant Team
  - **Tasks**:
    - Update `tradingagents/dataflows/stockstats_utils.py` for crypto specifics
    - Add crypto-specific indicators (funding rates, liquidation levels)
    - Implement 24/7 market hour handling
    - Add volatility indicators suitable for crypto
  - **Acceptance Criteria**: All technical indicators work with crypto price data

- [ ] **1.3** Create crypto-specific configuration
  - **Priority**: P1 (High)
  - **Owner**: Architecture Team
  - **Tasks**:
    - Create `crypto_config.py` based on `default_config.py`
    - Add crypto exchange configurations
    - Configure 24/7 trading parameters
    - Add crypto asset categorization (DeFi, L1, L2, meme coins, etc.)
  - **Acceptance Criteria**: Crypto config supports all major exchanges and asset types

#### **🚨 HIGH PRIORITY - Market Hours & Operations**
- [ ] **1.4** Implement 24/7 market operations
  - **Priority**: P1 (High)
  - **Owner**: Core Team
  - **Tasks**:
    - Remove market hour restrictions from trading logic
    - Update time zone handling for global crypto markets
    - Modify `tradingagents/graph/trading_graph.py` for continuous operations
    - Add weekend trading capabilities
  - **Acceptance Criteria**: System operates continuously without market hour constraints

### **PHASE 2: Agent Specialization for Crypto** ⏱️ *3-4 weeks*

#### **🔄 MAJOR REFACTORING - Fundamentals Analyst**
- [ ] **2.1** Replace traditional fundamental analysis with crypto-native metrics
  - **Priority**: P0 (Blocking)
  - **Owner**: Research Team
  - **Tasks**:
    - **Remove**: Balance sheets, income statements, P/E ratios
    - **Add**: On-chain metrics (active addresses, transaction volume, TVL)
    - **Add**: Network health metrics (hash rate for PoW, staking ratio for PoS)
    - **Add**: Token economics analysis (inflation rate, token distribution, vesting schedules)
    - **Add**: Protocol revenue and fee analysis
    - Create `tradingagents/agents/analysts/crypto_fundamentals_analyst.py`
  - **Data Sources**: Glassnode, Nansen, Dune Analytics APIs
  - **Acceptance Criteria**: Analyst provides comprehensive crypto fundamental analysis

- [ ] **2.2** Enhance Market Analyst for crypto-specific patterns
  - **Priority**: P1 (High)
  - **Owner**: Quant Team
  - **Tasks**:
    - Add crypto-specific support/resistance levels
    - Implement funding rate analysis for perpetuals
    - Add liquidation cascade detection
    - Include whale movement analysis
    - Enhance `tradingagents/agents/analysts/market_analyst.py` with crypto indicators
  - **Acceptance Criteria**: Market analyst identifies crypto-specific trading patterns

#### **📰 CONTENT ADAPTATION - News & Sentiment**
- [ ] **2.3** Adapt News Analyst for crypto ecosystem
  - **Priority**: P1 (High)
  - **Owner**: NLP Team
  - **Tasks**:
    - Add crypto-native news sources (CoinDesk, The Block, Decrypt, CryptoSlate)
    - Monitor regulatory news and policy changes
    - Track DeFi protocol updates and governance proposals
    - Implement macro crypto market sentiment tracking
    - Update `tradingagents/agents/analysts/news_analyst.py`
  - **Acceptance Criteria**: Comprehensive crypto news coverage and analysis

- [ ] **2.4** Enhance Social Media Analyst for crypto communities
  - **Priority**: P1 (High)
  - **Owner**: Social Data Team
  - **Tasks**:
    - Add Crypto Twitter sentiment analysis
    - Monitor Discord and Telegram channels
    - Track crypto-specific Reddit communities (r/cryptocurrency, r/defi)
    - Implement influencer sentiment tracking
    - Add meme coin trend detection
    - Enhance `tradingagents/agents/analysts/social_media_analyst.py`
  - **Acceptance Criteria**: Captures crypto community sentiment accurately

### **PHASE 3: Risk Management & Trading Logic** ⏱️ *2-3 weeks*

#### **⚠️ CRITICAL - Risk Management Overhaul**
- [ ] **3.1** Implement crypto-specific risk management
  - **Priority**: P0 (Blocking)
  - **Owner**: Risk Team
  - **Tasks**:
    - Add higher volatility tolerance parameters
    - Implement smart contract risk assessment
    - Add exchange security rating system
    - Create liquidity depth analysis
    - Account for regulatory risks per jurisdiction
    - Update `tradingagents/agents/managers/risk_manager.py`
  - **Acceptance Criteria**: Risk system appropriate for crypto market volatility

- [ ] **3.2** Enhanced portfolio management for crypto assets
  - **Priority**: P1 (High)
  - **Owner**: Portfolio Team
  - **Tasks**:
    - Implement crypto correlation analysis
    - Add rebalancing logic for crypto portfolios
    - Create sector allocation (DeFi, L1, L2, Gaming, etc.)
    - Add staking rewards consideration
    - Implement tax optimization for crypto trades
  - **Acceptance Criteria**: Portfolio management suited for crypto asset classes

#### **💱 TRADING ADAPTATIONS**
- [ ] **3.3** Modify trading execution for crypto markets
  - **Priority**: P1 (High)
  - **Owner**: Trading Team
  - **Tasks**:
    - Implement multi-exchange trading logic
    - Add slippage calculation for different liquidity levels
    - Create order book depth analysis
    - Add MEV (Maximum Extractable Value) protection
    - Handle gas fees and network congestion
    - Update `tradingagents/agents/trader/trader.py`
  - **Acceptance Criteria**: Efficient execution across crypto exchanges

### **PHASE 4: Advanced Crypto Features** ⏱️ *4-5 weeks*

#### **🔗 BLOCKCHAIN INTEGRATION**
- [ ] **4.1** Add DeFi protocol integration
  - **Priority**: P2 (Medium)
  - **Owner**: DeFi Team
  - **Tasks**:
    - Monitor yield farming opportunities
    - Track liquidity mining rewards
    - Analyze protocol token emissions
    - Implement cross-chain bridge monitoring
    - Add governance participation analysis
  - **Acceptance Criteria**: System can evaluate DeFi investment opportunities

- [ ] **4.2** Implement on-chain analytics
  - **Priority**: P2 (Medium)
  - **Owner**: Blockchain Team
  - **Tasks**:
    - Create whale wallet tracking
    - Implement smart money following strategies
    - Add institutional flow analysis
    - Monitor large transaction patterns
    - Track exchange inflows/outflows
    - Create `tradingagents/agents/analysts/onchain_analyst.py`
  - **Acceptance Criteria**: On-chain data informs trading decisions

#### **🤖 ADVANCED AGENTS**
- [ ] **4.3** Create specialized crypto agents
  - **Priority**: P2 (Medium)
  - **Owner**: AI Team
  - **Tasks**:
    - **MEV Analyst**: Detects arbitrage and MEV opportunities
    - **Macro Analyst**: Analyzes macroeconomic impact on crypto
    - **Regulatory Analyst**: Monitors policy changes affecting crypto
    - **Cross-chain Analyst**: Analyzes multi-chain opportunities
  - **Acceptance Criteria**: Specialized agents provide unique crypto insights

### **PHASE 5: Testing & Deployment** ⏱️ *2-3 weeks*

#### **🧪 VALIDATION & TESTING**
- [ ] **5.1** Comprehensive testing framework
  - **Priority**: P0 (Blocking)
  - **Owner**: QA Team
  - **Tasks**:
    - Create crypto market simulation environment
    - Implement backtesting with historical crypto data
    - Add stress testing for high volatility periods
    - Create integration tests for all crypto data sources
    - Validate 24/7 operation stability
  - **Acceptance Criteria**: System robust across various crypto market conditions

- [ ] **5.2** Performance optimization
  - **Priority**: P1 (High)
  - **Owner**: Performance Team
  - **Tasks**:
    - Optimize for high-frequency crypto data updates
    - Implement caching for expensive on-chain queries
    - Add rate limiting for exchange APIs
    - Optimize memory usage for 24/7 operations
  - **Acceptance Criteria**: System maintains performance under continuous load

#### **📊 MONITORING & ANALYTICS**
- [ ] **5.3** Create crypto-specific monitoring
  - **Priority**: P1 (High)
  - **Owner**: DevOps Team
  - **Tasks**:
    - Implement real-time performance dashboards
    - Add crypto-specific alerting (flash crashes, pump/dumps)
    - Create trading performance analytics
    - Monitor exchange connectivity and latency
    - Add compliance monitoring for different jurisdictions
  - **Acceptance Criteria**: Comprehensive monitoring for crypto trading operations

## **🔧 Technical Implementation Details**

### **New File Structure**
```
tradingagents/
├── dataflows/
│   ├── crypto_exchanges.py          # NEW: Crypto exchange integrations
│   ├── onchain_analytics.py         # NEW: Blockchain data sources
│   └── defi_protocols.py           # NEW: DeFi protocol data
├── agents/
│   ├── analysts/
│   │   ├── crypto_fundamentals_analyst.py  # MODIFIED
│   │   ├── onchain_analyst.py              # NEW
│   │   └── defi_analyst.py                 # NEW
│   └── utils/
│       └── crypto_tools.py         # NEW: Crypto-specific utilities
├── configs/
│   └── crypto_config.py            # NEW: Crypto-specific configuration
└── risk/
    └── crypto_risk_models.py       # NEW: Crypto risk assessment
```

### **Key Dependencies to Add**
```python
# Crypto data sources
ccxt>=4.0.0                 # Unified crypto exchange API
python-binance>=1.0.19      # Binance API
coinbase>=2.1.0             # Coinbase API
pycoingecko>=3.1.0          # CoinGecko API

# Blockchain analytics
web3>=6.0.0                 # Ethereum interaction
bitcoinlib>=0.12.0          # Bitcoin utilities
glassnode>=1.0.0            # On-chain analytics

# DeFi protocols
uniswap-python>=1.0.0       # Uniswap integration
aave-python>=1.0.0          # Aave protocol
```

### **Configuration Changes**
```python
CRYPTO_CONFIG = {
    # Trading parameters
    "max_position_size": 0.1,           # Higher risk tolerance
    "volatility_threshold": 0.15,       # Crypto-appropriate volatility
    "trading_hours": "24/7",            # Continuous trading
    
    # Data sources
    "primary_exchange": "binance",
    "backup_exchanges": ["coinbase", "kraken"],
    "onchain_provider": "glassnode",
    "news_sources": ["coindesk", "theblock"],
    
    # Risk management
    "max_drawdown": 0.25,              # Higher drawdown tolerance
    "position_limits": {
        "btc": 0.3,                    # 30% max BTC position
        "eth": 0.25,                   # 25% max ETH position
        "altcoins": 0.05,              # 5% max per altcoin
    }
}
```

## **📈 Expected Outcomes**

### **Immediate Benefits (0-3 months)**
- Crypto market analysis capability
- 24/7 trading operations
- Basic crypto fundamental analysis
- Multi-exchange data integration

### **Medium-term Goals (3-6 months)**
- Advanced on-chain analytics
- DeFi opportunity detection
- Cross-chain arbitrage capabilities
- Regulatory compliance monitoring

### **Long-term Vision (6+ months)**
- Full DeFi ecosystem integration
- MEV opportunity detection
- Institutional-grade crypto trading
- Multi-chain portfolio optimization

## **💼 Portfolio Management & Crypto Adaptation Requirements**

### **🔍 Current System Gaps**
The existing system has **significant limitations** for both portfolio management and crypto trading:

#### **❌ Critical Missing Features**
1. **No Portfolio Context**: Individual decisions without considering current holdings, available capital, or allocation targets
2. **No Position Sizing**: Only BUY/HOLD/SELL signals without dollar amounts or percentages
3. **Equity-Only Focus**: Traditional stock market data, fundamentals, and risk models
4. **Market Hours Limitation**: No 24/7 trading for crypto markets
5. **No Crypto Infrastructure**: Missing exchange integrations, on-chain analytics, DeFi protocols

#### **✅ Strong Foundation to Build Upon**
- Multi-agent collaborative framework
- Memory and learning capabilities
- Flexible data source routing
- Risk assessment and debate mechanisms

---

## **📋 INTEGRATED PROJECT MANAGER ACTION ITEMS**

### **PHASE 1: Portfolio Foundation & Crypto Infrastructure** ⏱️ *3-4 weeks*

#### **🔥 P0 CRITICAL - Portfolio State & Crypto Data**
- [ ] **1.1** Design portfolio state management with crypto infrastructure
  - **Owner**: Architecture Team
  - **Tasks**:
    - Create `PortfolioState` class with crypto holdings, capital allocation, sector targets
    - Add crypto exchange integrations (Binance, Coinbase, CoinGecko)
    - Create `PortfolioManager` agent for allocation decisions and position sizing
    - Implement 24/7 market operations for continuous crypto trading
  - **Acceptance Criteria**: System tracks crypto portfolio with specific dollar allocations

- [ ] **1.2** Replace equity fundamentals with crypto-native analysis
  - **Owner**: Research Team
  - **Tasks**:
    - Replace balance sheets/P&E ratios with on-chain metrics (TVL, active addresses, token economics)
    - Add crypto news sources (CoinDesk, The Block, crypto Twitter)
    - Integrate blockchain analytics (whale tracking, institutional flows)
    - Update technical indicators for crypto markets (funding rates, liquidation levels)
  - **Acceptance Criteria**: Comprehensive crypto analysis with portfolio context

### **PHASE 1: Infrastructure & Data Layer Migration** ⏱️ *2-3 weeks*

#### **🔥 CRITICAL - Data Source Integration**
- [ ] **1.1** Replace equity data sources with crypto exchanges
  - **Priority**: P0 (Blocking)
  - **Owner**: Backend Team
  - **Tasks**:
    - Integrate Binance API for spot trading data
    - Add Coinbase Pro/Advanced Trade API
    - Implement CoinGecko for market data and metadata
    - Add CryptoCompare for historical data
    - Create crypto data source routing in `tradingagents/dataflows/crypto_exchanges.py`
  - **Acceptance Criteria**: System can fetch OHLCV data for major crypto pairs

- [ ] **1.2** Modify technical indicators for crypto markets
  - **Priority**: P0 (Blocking)
  - **Owner**: Quant Team
  - **Tasks**:
    - Update `tradingagents/dataflows/stockstats_utils.py` for crypto specifics
    - Add crypto-specific indicators (funding rates, liquidation levels)
    - Implement 24/7 market hour handling
    - Add volatility indicators suitable for crypto
  - **Acceptance Criteria**: All technical indicators work with crypto price data

- [ ] **1.3** Create crypto-specific configuration
  - **Priority**: P1 (High)
  - **Owner**: Architecture Team
  - **Tasks**:
    - Create `crypto_config.py` based on `default_config.py`
    - Add crypto exchange configurations
    - Configure 24/7 trading parameters
    - Add crypto asset categorization (DeFi, L1, L2, meme coins, etc.)
    - **ADD**: Portfolio allocation targets and limits per crypto category
  - **Acceptance Criteria**: Crypto config supports all major exchanges and portfolio constraints

#### **🚨 HIGH PRIORITY - Market Hours & Operations**
- [ ] **1.4** Implement 24/7 market operations
  - **Priority**: P1 (High)
  - **Owner**: Core Team
  - **Tasks**:
    - Remove market hour restrictions from trading logic
    - Update2: Portfolio-Aware Trading & Risk Management** ⏱️ *3-4 weeks*

#### **⚠️ P0 CRITICAL - Portfolio Trading Integration**
- [ ] **2.1** Implement portfolio-aware crypto trading decisions
  - **Owner**: Trading & Risk Teams
  - **Tasks**:
    - Modify `trader.py` to output specific dollar amounts and position sizes
    - Add portfolio-level risk metrics (VaR, correlation analysis, sector limits)
    - Create dynamic position sizing based on portfolio targets and available capital
    - Implement crypto-specific risk parameters (volatility tolerance, smart contract risk)
    - Add portfolio rebalancing triggers and recommendations
  - **Acceptance Criteria**: Trading decisions include specific dollar allocations with portfolio context

- [ ] **2.2** Create Portfolio Analytics & Rebalancing Engine
  - **Owner**: Portfolio Team  
  - **Tasks**:
    - Create `portfolio_analyst.py` for portfolio health monitoring
    - Implement automated rebalancing logic (trigger when drift >5% from targets)
    - Add sector allocation management (DeFi, L1, L2, Gaming sectors)
    - Create tax-loss harvesting and yield optimization for crypto
    - Generate specific rebalancing recommendations ("sell $X BTC, buy $Y ETH")
  - **Acceptance Criteria**: Complete portfolio management with dollar-specific recommendation
### **PHASE 5: Testing & Deployment with Portfolio Simulation** ⏱️ *2-3 weeks*

#### **🧪 VALIDATION & PORTFOLIO TESTING**
- [ ] **5.1** Comprehensive portfolio testing framework
  - **Priority**: P0 (Blocking)
  - **Owner**: QA Team
  - **Tasks**:
    - Create crypto portfolio simulation environment
    - Implement backtesting with historical crypto data and portfolio tracking
    - Add stress testing for high volatility periods with portfolio impact
    - Create integration tests for all crypto data sources and portfolio state
    - Validate 24/7 operation stability with continuous portfolio monitoring
    - **ADD**: Portfolio performance benchmarking and validation
  - **Acceptance Criteria**: System robust across various crypto market conditions with portfolio tracking

- [ ] **5.2** Performance optimization for portfolio operations
  - **Priority**: P1 (High)
  - **Owner**: Performance Team
  - **Tasks**:
    - Optimize for high-frequency crypto data updates across portfolio
    - Implement caching for expensive on-chain queries and portfolio calculations
    - Add rate limiting for exchange APIs across multiple portfolio assets
    - Optimize memory usage for 24/7 operations and portfolio state management
    - **ADD**: Portfolio calculation optimization for real-time decision making
  - **Acceptance Criteria**: System maintains performance under continuous portfolio load

#### **📊 MONITORING & PORTFOLIO ANALYTICS**
- [ ] **5.3** Create crypto-specific portfolio monitoring
  - **Priority**: P1 (High)
  - **Owner**: DevOps Team
  - **Tasks**:
    - Implement real-time portfolio performance dashboards
    - Add crypto-specific alerting (flash crashes, pump/dumps) with portfolio impact
    - Create comprehensive trading and portfolio performance analytics
    - Monitor exchange connectivity and latency across portfolio assets
    - Add compliance monitoring for different jurisdictions
    - **ADD**: Portfolio health monitoring and alerting system
  - **Acceptance Criteria**: Comprehensive monitoring for crypto trading and portfolio management

## **🔧 Enhanced Technical Implementation**

### **New Portfolio-Aware File Structure**
```
tradingagents/
├── dataflows/
│   ├── crypto_exchanges.py          # NEW: Crypto exchange integrations
│   ├── onchain_analytics.py         # NEW: Blockchain data sources
│   ├── defi_protocols.py           # NEW: DeFi protocol data
│   └── portfolio_data.py           # NEW: Portfolio state management
├── agents/
│   ├── analysts/
│   │   ├── crypto_fundamentals_analyst.py  # MODIFIED
│   │   ├── portfolio_analyst.py            # NEW: Portfolio health analysis
│   │   ├── onchain_analyst.py              # NEW
│   │   └── defi_analyst.py                 # NEW
│   ├── managers/
│   │   ├── portfolio_manager.py            # NEW: Portfolio-wide decisions
│   │   └── rebalancing_manager.py          # NEW: Portfolio rebalancing
│   └── utils/
│       ├── crypto_tools.py         # NEW: Crypto-specific utilities
│       └── portfolio_tools.py      # NEW: Portfolio calculation utilities
├── configs/
│   └── crypto_portfolio_config.py  # NEW: Crypto + portfolio configuration
└── risk/
    ├── crypto_risk_models.py       # NEW: Crypto risk assessment
    └── portfolio_risk_models.py    # NEW: Portfolio risk management
```

### **Enhanced State Management**
```python
# Updated AgentState in agent_states.py
class PortfolioState(TypedDict):
    current_holdings: Dict[str, float]      # {"BTC": 1.5, "ETH": 10.0, "MATIC": 1000.0}
    available_capital: float                # Available USD for trading
    allocation_targets: Dict[str, float]    # {"BTC": 0.40, "ETH": 0.30, "ALTS": 0.30}
    risk_budget: Dict[str, float]          # Risk allocation per asset/sector
    total_portfolio_value: float           # Current portfolio value in USD
    performance_metrics: Dict[str, float]   # Portfolio performance stats

class AgentState(MessagesState):
    # ... existing fields ...
    
    # NEW: Portfolio context
    portfolio_state: Annotated[PortfolioState, "Current portfolio holdings and targets"]
    position_size_recommendation: Annotated[float, "Recommended position size in USD"]
    portfolio_impact_analysis: Annotated[str, "How this trade affects overall portfolio"]
    rebalancing_needed: Annotated[bool, "Whether portfolio needs rebalancing"]
```

### **Enhanced Configuration with Portfolio Management**
```python
CRYPTO_PORTFOLIO_CONFIG = {
    # Portfolio management
    "portfolio_targets": {
        "BTC": 0.35,                       # 35% Bitcoin allocation
        "ETH": 0.25,                       # 25% Ethereum allocation  
        "L1_TOKENS": 0.20,                 # 20% Layer 1 tokens (SOL, AVAX, etc.)
        "DEFI_TOKENS": 0.15,               # 15% DeFi tokens
        "STABLECOINS": 0.05,               # 5% stablecoins for opportunities
    },
    
    # Risk management
    "max_position_size": 0.10,             # Max 10% in any single asset
    "rebalancing_threshold": 0.05,         # Rebalance when drift > 5%
    "risk_budget_per_sector": 0.02,       # Max 2% portfolio risk per sector
    
    # Trading parameters
    "min_trade_amount": 100,               # Minimum $100 trades
    "max_trade_amount": 10000,             # Maximum $10k trades
    "available_capital": 50000,            # $50k total capital
    
    # Portfolio optimization
    "rebalancing_frequency": "weekly",      # Weekly rebalancing checks
    "yield_optimization": True,            # Enable DeFi yield optimization
    "tax_optimization": True,              # Enable tax-loss harvesting
}
```

## **💼 Portfolio Management Use Cases**

### **Example 1: New Investment Decision**
```
Current Portfolio: 40% BTC ($20k), 30% ETH ($15k), 30% Cash ($15k)
Target: 35% BTC, 25% ETH, 20% L1, 15% DeFi, 5% Stable

Agent Analysis: "Strong bullish signal for SOL"
Portfolio Manager Decision: 
- "Allocate $8k to SOL (16% of portfolio) from cash position"
- "This moves us toward target L1 allocation"
- "Risk impact: Increases portfolio volatility by 2%"
```

### **Example 2: Rebalancing Decision**
```
Current Portfolio: 50% BTC ($30k), 25% ETH ($15k), 25% MATIC ($15k)
Target Drift: BTC 15% over target, need rebalancing

Portfolio Ma3: Advanced Features & Optimization** ⏱️ *3-4 weeks*

#### **🔗 P2 MEDIUM - Advanced Crypto Integration**
- [ ] **3.1** DeFi protocol integration and yield optimization
  - **Owner**: DeFi Team
  - **Tasks**:
    - Monitor yield farming opportunities and factor into portfolio allocation decisions
    - Track liquidity mining rewards and governance participation
    - Implement cross-chain bridge monitoring and portfolio optimization
    - Create yield optimization recommendations with capital allocation
  - **Acceptance Criteria**: System optimizes DeFi yields within portfolio constraints

- [ ] **3.2** On-chain analytics with portfolio intelligence
  - **Owner**: Blockchain Team
  - **Tasks**:
    - Create whale wallet tracking relevant to current holdings
    - Add institutional flow analysis for portfolio positioning
    - Create `onchain_analyst.py` for blockchain data analysis
    - Implement smart money following strategies for portfolio assets
  - **Acceptance Criteria**: On-chain data drives portfolio-aware trading decisions

### **PHASE 4: Testing & Deployment** ⏱️ *2-3 weeks*

#### **🧪 P0 CRITICAL - System Validation**
- [ ] **4.1** Comprehensive testing and performance optimization
  - **Owner**: QA & Performance Teams
  - **Tasks**:
    - Create crypto portfolio simulation environment with backtesting
    - Implement stress testing for high volatility periods
    - Optimize for 24/7 operations and real-time portfolio calculations
    - Add integration tests for all crypto data sources and portfolio state
  - **Acceptance Criteria**: System robust with portfolio tracking across market conditions

- [ ] **4.2** Monitoring and analytics deployment
  - **Owner**: DevOps Team
  - **Tasks**:
    - Implement real-time portfolio performance dashboards
    - Add crypto-specific alerting with portfolio impact analysis
    - Create comprehensive trading and portfolio analytics
    - Add compliance monitoring for different jurisdictions
  - **Acceptance Criteria**: CompletTechnical Implementation Overview**

### **Key File Structure Changes**
```
tradingagents/
├── dataflows/
│   ├── crypto_exchanges.py          # NEW: Binance, Coinbase APIs
│   ├── onchain_analytics.py         # NEW: Glassnode, blockchain data
│   └── portfolio_data.py           # NEW: Portfolio state management
├── agents/
│   ├── analysts/
│   │   ├── crypto_fundamentals_analyst.py  # REPLACE: On-chain metrics
│   │   └── portfolio_analyst.py            # NEW: Portfolio health
│   ├── managers/
│   │   └── portfolio_manager.py            # NEW: Position sizing & allocation
├── configs/
│   └── crypto_portfolio_config.py  # NEW: Targets, limits, parameters
```

### **Portfolio State Integration**
```python
class PortfolioState(TypedDict):
    current_holdings: Dict[str, float]      # {"BTC": 1.5, "ETH": 10.0}
    available_capital: float                # USD available for trading
    allocation_targets: Dict[str, float]    # {"BTC": 0.35, "ETH": 0.25}
    total_portfolio_value: float           # Current portfolio value

class AgentState(MessagesState):
    # ... existing fields ...
    portfolio_state: Annotated[PortfolioState, "Portfolio context"]
    position_size_recommendation: Annotated[float, "USD amount to invest"]
    rebalancing_needed: Annotated[bool, "Portfolio needs rebalancing"]
```

### **Configuration with Portfolio Targets**
```python
CRYPTO_PORTFOLIO_CONFIG = {
    "portfolio_targets": {
        "BTC": 0.35, "ETH": 0.25, "L1_TOKENS": 0.20, 
        "DEFI_TOKENS": 0.15, "STABLECOINS": 0.05
    },
    "available_capital": 50000,            # $50k total
    "max_position_size": 0.10,             # Max 10% per asset
    "rebalancing_threshold": 0.05,         # Rebalance when >5% drift� Portfolio Management Examples**

### **Investment Decision with Portfolio Context**
```
Current: 40% BTC ($20k), 30% ETH ($15k), 30% Cash ($15k)
Signal: "Strong bullish signal for SOL"
Decision: "Allocate $8k to SOL from cash → achieves 16% L1 target allocation"
```

### **Automatic Rebalancing**
```
Current: 50% BTC ($30k), 25% ETH ($15k), 25% MATIC ($15k)
Trigger: BTC 15% over target (35%)
Action: "Sell $9k BTC → Buy $4k DeFi + $3k stables + $2k ETH"
```

### **Risk-Based Position Sizing**
```
Portfolio Risk: High correlation alert (BTC+ETH = 95%)
Decision: "Reduce BTC+ETH from 75% to 50%, increase stables to 20%
