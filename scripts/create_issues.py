#!/usr/bin/env python3
"""
Create GitHub issues for the Investment Platform project.
Run: python scripts/create_issues.py
"""

import subprocess
import sys

REPO = "akaszubski/TradingAgents"

# Issue definitions: (title, labels, body, depends_on)
ISSUES = [
    # Phase 1: Database Foundation
    (
        "[DB-1] Database setup - SQLAlchemy + PostgreSQL/SQLite",
        ["enhancement", "database", "priority-high"],
        """Create database/db.py with:
- SQLAlchemy engine configuration
- PostgreSQL for production, SQLite for development
- Session management (get_db, get_db_session)
- Connection pooling
- Environment variable configuration (DATABASE_URL)

**Acceptance Criteria:**
- Can connect to both PostgreSQL and SQLite
- Session management works correctly
- Environment variables properly loaded""",
        None
    ),
    (
        "[DB-2] User model - profiles, tax jurisdiction, API keys",
        ["enhancement", "database", "priority-high"],
        """Create database/models/user.py with:
- id, email, name, hashed_password
- tax_jurisdiction (AU, US, etc.)
- timezone (default: Australia/Sydney)
- api_key for programmatic access
- is_active, is_verified flags
- created_at, updated_at timestamps

**Acceptance Criteria:**
- Can create, read, update, delete users
- Tax jurisdiction defaults to AU

**Depends on:** #1""",
        None
    ),
    (
        "[DB-3] Portfolio model - live, paper, backtest types",
        ["enhancement", "database", "priority-high"],
        """Create database/models/portfolio.py with:
- PortfolioType enum (live, paper, backtest)
- BrokerType enum (alpaca, ibkr, paper)
- initial_capital, current_cash, currency
- strategy_name, strategy_config (JSON)
- CGT tracking fields
- Relationship to User

**Acceptance Criteria:**
- Can create multiple portfolios per user
- Supports all three portfolio types

**Depends on:** #1, #2""",
        None
    ),
    (
        "[DB-4] Settings model - risk profiles, alert preferences",
        ["enhancement", "database", "priority-high"],
        """Create database/models/settings.py with:
- RiskProfile enum (conservative, moderate, aggressive)
- max_position_pct, max_daily_loss_pct, default_stop_loss_pct
- position_sizing_method (fixed_fractional, kelly, risk_parity)
- Alert preferences (email, slack, sms with contact info)
- Trading hours
- LLM preferences

**Acceptance Criteria:**
- One-to-one relationship with User
- All risk parameters have sensible defaults

**Depends on:** #1, #2""",
        None
    ),
    (
        "[DB-5] Trade model - execution history with CGT tracking",
        ["enhancement", "database", "priority-high"],
        """Create database/models/trade.py with:
- symbol, side (buy/sell), quantity, price, total_value
- order_type, status (pending, filled, cancelled)
- signal_source, signal_confidence
- CGT fields: acquisition_date, cost_basis_per_unit, cost_basis_total
- holding_period_days, cgt_discount_eligible (>12 months)
- cgt_gross_gain, cgt_gross_loss, cgt_net_gain
- tax_year (Australian FY July-June)
- fx_rate_to_aud for foreign assets

**Acceptance Criteria:**
- Full CGT calculation support
- Tax year correctly calculated (July-June)
- 50% discount eligibility tracked

**Depends on:** #1, #3""",
        None
    ),
    (
        "[DB-6] Alembic migrations setup",
        ["enhancement", "database", "priority-high"],
        """Setup Alembic for database migrations:
- Initialize Alembic configuration
- Create initial migration for all models
- Add upgrade/downgrade scripts
- Document migration workflow in README

**Acceptance Criteria:**
- Can run migrations up and down
- Initial migration creates all tables

**Depends on:** #1-5""",
        None
    ),

    # Phase 2: Data Layer
    (
        "[DATA-7] FRED API integration - interest rates, M2, GDP, CPI",
        ["enhancement", "data", "priority-high"],
        """Create spektiv/dataflows/fred.py with:
- FRED API client (fredapi package)
- Series: DFF (Fed Funds), DGS10 (10Y Treasury), M2SL (M2), GDP, CPIAUCSL
- VIX from CBOE
- Date range filtering
- Error handling and retries

**Acceptance Criteria:**
- Can fetch all specified series
- Proper date formatting
- Rate limit handling""",
        None
    ),
    (
        "[DATA-8] Multi-timeframe aggregation - weekly/monthly OHLCV",
        ["enhancement", "data", "priority-high"],
        """Create spektiv/dataflows/multi_timeframe.py with:
- Aggregate daily OHLCV to weekly
- Aggregate daily OHLCV to monthly
- Preserve volume correctly
- Handle partial periods

**Acceptance Criteria:**
- Weekly aggregation (Mon-Fri)
- Monthly aggregation
- Works with yfinance data""",
        None
    ),
    (
        "[DATA-9] Benchmark data - SPY, sector ETFs",
        ["enhancement", "data", "priority-high"],
        """Create spektiv/dataflows/benchmark.py with:
- SPY for broad market
- Sector ETFs (XLF, XLK, XLE, XLV, etc.)
- Relative strength calculation
- Correlation calculation

**Acceptance Criteria:**
- Can calculate relative strength vs SPY
- Can calculate rolling correlations""",
        None
    ),
    (
        "[DATA-10] Interface routing - add new data vendors",
        ["enhancement", "data", "priority-high"],
        """Update spektiv/dataflows/interface.py:
- Add FRED to VENDOR_METHODS
- Add multi_timeframe routing
- Add benchmark routing
- Update TOOLS_CATEGORIES

**Acceptance Criteria:**
- New vendors accessible via route_to_vendor
- Fallback chains work correctly

**Depends on:** #7-9""",
        None
    ),
    (
        "[DATA-11] Data caching layer - FRED rate limits",
        ["enhancement", "data", "priority-medium"],
        """Add caching for FRED data:
- File-based cache for FRED responses
- Cache invalidation strategy (daily for most series)
- Memory cache for frequently accessed data

**Acceptance Criteria:**
- Reduces API calls
- Cache respects rate limits

**Depends on:** #7""",
        None
    ),

    # Phase 3: New Analysts
    (
        "[AGENT-12] Momentum Analyst - multi-TF momentum, ROC, ADX",
        ["enhancement", "agents", "priority-high"],
        """Create spektiv/agents/analysts/momentum_analyst.py with:
- Multi-timeframe momentum (daily, weekly, monthly)
- Rate of Change (ROC) calculation
- ADX (Average Directional Index)
- Relative strength vs benchmark
- Volume-weighted momentum

**Acceptance Criteria:**
- Produces structured report like other analysts
- Integrates with debate workflow

**Depends on:** #8""",
        None
    ),
    (
        "[AGENT-13] Macro Analyst - FRED interpretation, regime detection",
        ["enhancement", "agents", "priority-high"],
        """Create spektiv/agents/analysts/macro_analyst.py with:
- Interpret FRED data for market regime
- Interest rate environment (rising/falling/stable)
- Inflation/deflation signals
- Risk-on/risk-off assessment
- Economic cycle positioning

**Acceptance Criteria:**
- Produces structured macro report
- Identifies current market regime

**Depends on:** #7""",
        None
    ),
    (
        "[AGENT-14] Correlation Analyst - cross-asset, sector rotation",
        ["enhancement", "agents", "priority-high"],
        """Create spektiv/agents/analysts/correlation_analyst.py with:
- Cross-asset correlation analysis
- Sector rotation signals
- Safe haven flows (gold, bonds)
- Currency correlations (if applicable)
- Divergence detection

**Acceptance Criteria:**
- Produces correlation report
- Identifies unusual correlations

**Depends on:** #9""",
        None
    ),
    (
        "[AGENT-15] Position Sizing Manager - Kelly, risk parity, ATR",
        ["enhancement", "agents", "priority-high"],
        """Create spektiv/agents/managers/position_sizing_manager.py with:
- Kelly criterion calculation
- Risk parity sizing
- Fixed fractional sizing
- ATR-based sizing
- Maximum position limits

**Acceptance Criteria:**
- Given signal and confidence, outputs position size
- Respects risk limits from settings""",
        None
    ),
    (
        "[AGENT-16] Analyst integration - add to graph/setup.py workflow",
        ["enhancement", "agents", "priority-high"],
        """Update spektiv/graph/setup.py:
- Add new analysts to analyst team
- Update debate workflow to include new insights
- Ensure position sizing manager is called

**Acceptance Criteria:**
- All new analysts contribute to analysis
- Backward compatible with existing workflow

**Depends on:** #12-15""",
        None
    ),

    # Phase 4: Memory System
    (
        "[MEM-17] Layered memory - recency, relevancy, importance scoring",
        ["enhancement", "memory", "priority-medium"],
        """Create spektiv/memory/layered_memory.py with:
- Recency scoring (exponential decay)
- Relevancy scoring (similarity to current situation)
- Importance scoring (based on P&L impact)
- Memory retrieval with composite score

**Acceptance Criteria:**
- FinMem pattern implemented
- Can retrieve top-k relevant memories

**Depends on:** #5""",
        None
    ),
    (
        "[MEM-18] Trade history memory - outcomes, agent reasoning",
        ["enhancement", "memory", "priority-medium"],
        """Create spektiv/memory/trade_history.py with:
- Store trade outcomes with full context
- Link to agent reasoning at time of trade
- Track what worked vs what didn't
- Pattern recognition for similar setups

**Acceptance Criteria:**
- Full trade context preserved
- Can query by symbol, timeframe, outcome

**Depends on:** #5, #17""",
        None
    ),
    (
        "[MEM-19] Risk profiles memory - user preferences over time",
        ["enhancement", "memory", "priority-medium"],
        """Create spektiv/memory/risk_profiles.py with:
- User risk preferences over time
- Portfolio behavior patterns
- Drawdown tolerance history
- Position sizing history

**Acceptance Criteria:**
- Tracks risk behavior evolution
- Informs position sizing

**Depends on:** #4, #17""",
        None
    ),
    (
        "[MEM-20] Memory integration - retrieval in agent prompts",
        ["enhancement", "memory", "priority-medium"],
        """Integrate memory into agents:
- Add memory retrieval to analyst prompts
- Include relevant past trades in context
- Update trader agent with memory

**Acceptance Criteria:**
- Agents reference relevant past trades
- Memory influences recommendations

**Depends on:** #17-19""",
        None
    ),

    # Phase 5: Execution Layer
    (
        "[EXEC-21] Broker base interface - abstract broker class",
        ["enhancement", "execution", "priority-high"],
        """Create execution/brokers/base.py with:
- Abstract Broker class
- Methods: connect, disconnect, submit_order, cancel_order
- Methods: get_positions, get_account, get_order_status
- Error handling patterns

**Acceptance Criteria:**
- Clear interface contract
- All brokers implement same interface""",
        None
    ),
    (
        "[EXEC-22] Broker router - route by asset class",
        ["enhancement", "execution", "priority-high"],
        """Create execution/brokers/broker_router.py with:
- Route by exchange (NYSE, NASDAQ -> Alpaca)
- Route by asset type (futures -> IBKR)
- Route by symbol suffix (.AX -> IBKR)
- Fallback handling

**Acceptance Criteria:**
- Correct routing for all asset classes
- Clear routing rules

**Depends on:** #21""",
        None
    ),
    (
        "[EXEC-23] Alpaca broker - US stocks, ETFs, crypto",
        ["enhancement", "execution", "priority-high"],
        """Create execution/brokers/alpaca_broker.py with:
- Alpaca API integration (alpaca-py)
- Paper and live modes
- US stocks, ETFs
- Crypto trading
- Order submission and tracking

**Acceptance Criteria:**
- Can place orders via Alpaca API
- Supports paper trading mode

**Depends on:** #21, #22""",
        None
    ),
    (
        "[EXEC-24] IBKR broker - futures, ASX equities",
        ["enhancement", "execution", "priority-high"],
        """Create execution/brokers/ibkr_broker.py with:
- Interactive Brokers API (ib_insync)
- Futures contracts (GC, SI, ES)
- Australian equities (ASX)
- Order submission and tracking

**Acceptance Criteria:**
- Can place orders via IBKR
- Supports futures and ASX

**Depends on:** #21, #22""",
        None
    ),
    (
        "[EXEC-25] Paper broker - simulation mode",
        ["enhancement", "execution", "priority-high"],
        """Create execution/brokers/paper_broker.py with:
- Simulated order execution
- Realistic fill simulation
- Position tracking
- P&L calculation
- No real money at risk

**Acceptance Criteria:**
- Full trading simulation
- Tracks positions and P&L

**Depends on:** #21, #22""",
        None
    ),
    (
        "[EXEC-26] Order types and manager - market, limit, stop, trailing",
        ["enhancement", "execution", "priority-high"],
        """Create execution/orders/:
- order_types.py - Order, OrderType, OrderStatus enums
- order_manager.py - Order lifecycle management
- Support: market, limit, stop, stop_limit, trailing_stop

**Acceptance Criteria:**
- All order types supported
- Order state machine correct

**Depends on:** #21""",
        None
    ),
    (
        "[EXEC-27] Risk controls - position limits, loss limits",
        ["enhancement", "execution", "priority-high"],
        """Create execution/risk_controls/:
- position_limits.py - Max position size, concentration
- loss_limits.py - Daily loss limit, drawdown limit
- Pre-trade validation

**Acceptance Criteria:**
- Orders rejected if limits exceeded
- Clear rejection messages

**Depends on:** #4""",
        None
    ),

    # Phase 6: Portfolio Management
    (
        "[PORT-28] Portfolio state - holdings, cash, mark-to-market",
        ["enhancement", "portfolio", "priority-high"],
        """Create portfolio/portfolio_state.py with:
- Current holdings
- Cash balance
- Total portfolio value (mark-to-market)
- Real-time pricing

**Acceptance Criteria:**
- Accurate portfolio valuation
- Handles multiple currencies

**Depends on:** #3, #5""",
        None
    ),
    (
        "[PORT-29] Position tracker - open/closed, cost basis, tax lots",
        ["enhancement", "portfolio", "priority-high"],
        """Create portfolio/position_tracker.py with:
- Open positions with cost basis
- Closed positions with realized P&L
- Tax lot tracking (FIFO, LIFO, specific ID)
- Average cost calculation

**Acceptance Criteria:**
- Correct cost basis tracking
- Tax lot matching works

**Depends on:** #5, #28""",
        None
    ),
    (
        "[PORT-30] Performance metrics - Sharpe, drawdown, returns",
        ["enhancement", "portfolio", "priority-high"],
        """Create portfolio/performance.py with:
- Daily, monthly, yearly returns
- Sharpe ratio
- Maximum drawdown
- Win rate, profit factor
- Benchmark comparison

**Acceptance Criteria:**
- Industry-standard calculations
- Matches known benchmarks

**Depends on:** #28, #29""",
        None
    ),
    (
        "[PORT-31] Australian CGT calculator - 50% discount, tax reports",
        ["enhancement", "portfolio", "priority-high"],
        """Create portfolio/tax_calculator.py with:
- Australian CGT calculations
- 50% discount for assets held >12 months
- Tax year reports (July-June)
- Currency conversion for foreign assets
- Capital loss tracking

**Acceptance Criteria:**
- Correct CGT calculations
- Tax year correctly determined
- Report format suitable for tax return

**Depends on:** #5, #29""",
        None
    ),

    # Phase 7: Simulation & Strategy
    (
        "[SIM-32] Scenario runner - parallel portfolio simulations",
        ["enhancement", "simulation", "priority-high"],
        """Create simulation/scenario_runner.py with:
- Run multiple portfolios in parallel
- Same market data, different strategies
- Paper trading infrastructure
- Result collection

**Acceptance Criteria:**
- Can run 5+ parallel simulations
- Results properly isolated

**Depends on:** #25, #28""",
        None
    ),
    (
        "[SIM-33] Strategy comparator - performance comparison, stats",
        ["enhancement", "simulation", "priority-high"],
        """Create simulation/strategy_comparator.py with:
- Compare performance across scenarios
- Statistical significance testing
- Risk-adjusted return comparison
- Ranking and scoring

**Acceptance Criteria:**
- Clear comparison output
- Statistical confidence levels

**Depends on:** #30, #32""",
        None
    ),
    (
        "[SIM-34] Economic conditions - regime tagging, evaluation",
        ["enhancement", "simulation", "priority-high"],
        """Create simulation/economic_conditions.py with:
- Tag scenarios by economic regime
- Bull/bear/sideways market detection
- Evaluate strategy performance by condition
- Regime-specific recommendations

**Acceptance Criteria:**
- Correct regime identification
- Performance breakdown by regime

**Depends on:** #7, #32""",
        None
    ),
    (
        "[STRAT-35] Signal to order converter",
        ["enhancement", "strategy", "priority-high"],
        """Create strategy/signal_to_order.py with:
- Convert BUY/SELL signals to orders
- Apply position sizing
- Set stop loss and take profit
- Order validation

**Acceptance Criteria:**
- Signals converted to valid orders
- Risk parameters applied

**Depends on:** #26""",
        None
    ),
    (
        "[STRAT-36] Strategy executor - end-to-end orchestration",
        ["enhancement", "strategy", "priority-high"],
        """Create strategy/strategy_executor.py with:
- End-to-end orchestration
- Signal generation -> Order -> Execution
- Error handling and retries
- Logging and monitoring

**Acceptance Criteria:**
- Full trade lifecycle managed
- Robust error handling

**Depends on:** #32-35""",
        None
    ),

    # Phase 8: Alerts
    (
        "[ALERT-37] Alert manager - orchestration and routing",
        ["enhancement", "alerts", "priority-medium"],
        """Create alerts/alert_manager.py with:
- Alert orchestration
- Route to appropriate channels
- Priority levels (info, warning, critical)
- Throttling to prevent spam

**Acceptance Criteria:**
- Alerts routed correctly
- Critical alerts always delivered

**Depends on:** #4""",
        None
    ),
    (
        "[ALERT-38] Email channel - SMTP/SendGrid",
        ["enhancement", "alerts", "priority-medium"],
        """Create alerts/channels/email_channel.py with:
- SMTP support
- SendGrid API support
- HTML email templates
- Delivery confirmation

**Acceptance Criteria:**
- Emails delivered reliably
- Professional formatting

**Depends on:** #37""",
        None
    ),
    (
        "[ALERT-39] Slack channel - webhooks",
        ["enhancement", "alerts", "priority-medium"],
        """Create alerts/channels/slack_channel.py with:
- Slack webhook integration
- Rich message formatting
- Channel routing

**Acceptance Criteria:**
- Messages appear in Slack
- Formatting correct

**Depends on:** #37""",
        None
    ),
    (
        "[ALERT-40] SMS channel - Twilio",
        ["enhancement", "alerts", "priority-medium"],
        """Create alerts/channels/sms_channel.py with:
- Twilio API integration
- SMS formatting
- Delivery status tracking

**Acceptance Criteria:**
- SMS delivered
- Critical alerts work

**Depends on:** #37""",
        None
    ),

    # Phase 9: Backtest
    (
        "[BT-41] Backtest engine - historical replay, slippage",
        ["enhancement", "backtest", "priority-medium"],
        """Create backtest/backtest_engine.py with:
- Historical data replay
- Slippage modeling
- Commission modeling
- Position sizing simulation

**Acceptance Criteria:**
- Realistic backtesting
- Configurable slippage/commission

**Depends on:** #25, #28""",
        None
    ),
    (
        "[BT-42] Results analyzer - metrics, trade analysis",
        ["enhancement", "backtest", "priority-medium"],
        """Create backtest/results_analyzer.py with:
- Performance metrics
- Trade-by-trade analysis
- Equity curve
- Drawdown analysis

**Acceptance Criteria:**
- Comprehensive analysis
- Visual outputs

**Depends on:** #30, #41""",
        None
    ),
    (
        "[BT-43] Report generator - PDF/HTML reports",
        ["enhancement", "backtest", "priority-low"],
        """Create backtest/report_generator.py with:
- PDF report generation
- HTML report generation
- Charts and graphs
- Summary statistics

**Acceptance Criteria:**
- Professional reports
- Exportable

**Depends on:** #42""",
        None
    ),

    # Phase 10: API & Docs
    (
        "[API-44] FastAPI application setup",
        ["enhancement", "api", "priority-low"],
        """Create api/app.py with:
- FastAPI application
- CORS configuration
- Error handling
- Health check endpoint

**Acceptance Criteria:**
- API starts and responds
- Health check works

**Depends on:** #1-6""",
        None
    ),
    (
        "[API-45] API routes - users, portfolios, trades, signals",
        ["enhancement", "api", "priority-low"],
        """Create api/routes/:
- users.py - User CRUD
- portfolios.py - Portfolio CRUD
- trades.py - Trade history
- signals.py - Signal retrieval

**Acceptance Criteria:**
- All CRUD operations work
- Proper error responses

**Depends on:** #44""",
        None
    ),
    (
        "[API-46] API authentication - JWT",
        ["enhancement", "api", "priority-low"],
        """Add JWT authentication:
- Login endpoint
- Token generation
- Token validation middleware
- Refresh tokens

**Acceptance Criteria:**
- Secure authentication
- Token refresh works

**Depends on:** #44, #45""",
        None
    ),
    (
        "[DOCS-47] Documentation - user guide, developer docs",
        ["documentation", "priority-low"],
        """Create documentation:
- User guide (how to use)
- Developer guide (how to extend)
- API documentation (OpenAPI)
- Architecture overview

**Acceptance Criteria:**
- Clear documentation
- Getting started guide""",
        None
    ),
]


def create_issue(title: str, labels: list, body: str) -> bool:
    """Create a single GitHub issue."""
    label_args = []
    for label in labels:
        label_args.extend(["--label", label])

    cmd = [
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--body", body,
    ] + label_args

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"Created: {title}")
        print(f"  URL: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"FAILED: {title}")
        print(f"  Error: {e.stderr}")
        return False


def main():
    print(f"Creating {len(ISSUES)} issues in {REPO}...")
    print("=" * 60)

    created = 0
    failed = 0

    for title, labels, body, _ in ISSUES:
        if create_issue(title, labels, body):
            created += 1
        else:
            failed += 1

    print("=" * 60)
    print(f"Done: {created} created, {failed} failed")


if __name__ == "__main__":
    main()
