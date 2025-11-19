"""
Backtesting Framework for TradingAgents.

This module provides a comprehensive backtesting framework for testing
trading strategies with realistic execution simulation and performance analysis.

Main Components:
    - Backtester: Main backtesting engine
    - BacktestConfig: Configuration management
    - BaseStrategy: Base class for strategies
    - PerformanceAnalyzer: Performance metrics calculation
    - MonteCarloSimulator: Monte Carlo simulations
    - WalkForwardAnalyzer: Walk-forward analysis

Example:
    >>> from tradingagents.backtest import Backtester, BacktestConfig
    >>> from tradingagents.backtest.strategy import BuyAndHoldStrategy
    >>>
    >>> # Create configuration
    >>> config = BacktestConfig(
    ...     initial_capital=100000,
    ...     start_date='2020-01-01',
    ...     end_date='2023-12-31',
    ...     commission=0.001,
    ... )
    >>>
    >>> # Create strategy
    >>> strategy = BuyAndHoldStrategy()
    >>>
    >>> # Run backtest
    >>> backtester = Backtester(config)
    >>> results = backtester.run(strategy, tickers=['AAPL', 'MSFT'])
    >>>
    >>> # Analyze results
    >>> print(f"Total Return: {results.total_return:.2%}")
    >>> print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    >>>
    >>> # Generate report
    >>> results.generate_report('backtest_report.html')
"""

__version__ = '0.1.0'

# Core components
from .backtester import (
    Backtester,
    BacktestResults,
    Portfolio,
)

from .config import (
    BacktestConfig,
    WalkForwardConfig,
    MonteCarloConfig,
    OrderType,
    DataSource,
    SlippageModel,
    CommissionModel,
    create_default_config,
)

from .strategy import (
    BaseStrategy,
    Signal,
    Position,
    PositionSizer,
    RiskManager,
    BuyAndHoldStrategy,
    SimpleMovingAverageStrategy,
)

from .performance import (
    PerformanceAnalyzer,
    PerformanceMetrics,
)

from .data_handler import (
    HistoricalDataHandler,
)

from .execution import (
    ExecutionSimulator,
    Order,
    Fill,
    OrderSide,
    OrderStatus,
    create_market_order,
    create_limit_order,
)

from .reporting import (
    BacktestReporter,
)

from .monte_carlo import (
    MonteCarloSimulator,
    MonteCarloResults,
    create_monte_carlo_config,
)

from .walk_forward import (
    WalkForwardAnalyzer,
    WalkForwardResults,
    WalkForwardWindow,
    create_walk_forward_config,
)

from .integration import (
    TradingAgentsStrategy,
    backtest_trading_agents,
    compare_strategies,
    parallel_backtest,
    BacktestingPipeline,
)

from .exceptions import (
    BacktestError,
    DataError,
    DataNotFoundError,
    DataQualityError,
    ExecutionError,
    InsufficientCapitalError,
    StrategyError,
    ConfigurationError,
    PerformanceError,
    ReportingError,
    OptimizationError,
    MonteCarloError,
    IntegrationError,
)


__all__ = [
    # Core
    'Backtester',
    'BacktestResults',
    'Portfolio',

    # Configuration
    'BacktestConfig',
    'WalkForwardConfig',
    'MonteCarloConfig',
    'OrderType',
    'DataSource',
    'SlippageModel',
    'CommissionModel',
    'create_default_config',

    # Strategy
    'BaseStrategy',
    'Signal',
    'Position',
    'PositionSizer',
    'RiskManager',
    'BuyAndHoldStrategy',
    'SimpleMovingAverageStrategy',

    # Performance
    'PerformanceAnalyzer',
    'PerformanceMetrics',

    # Data
    'HistoricalDataHandler',

    # Execution
    'ExecutionSimulator',
    'Order',
    'Fill',
    'OrderSide',
    'OrderStatus',
    'create_market_order',
    'create_limit_order',

    # Reporting
    'BacktestReporter',

    # Monte Carlo
    'MonteCarloSimulator',
    'MonteCarloResults',
    'create_monte_carlo_config',

    # Walk-Forward
    'WalkForwardAnalyzer',
    'WalkForwardResults',
    'WalkForwardWindow',
    'create_walk_forward_config',

    # Integration
    'TradingAgentsStrategy',
    'backtest_trading_agents',
    'compare_strategies',
    'parallel_backtest',
    'BacktestingPipeline',

    # Exceptions
    'BacktestError',
    'DataError',
    'DataNotFoundError',
    'DataQualityError',
    'ExecutionError',
    'InsufficientCapitalError',
    'StrategyError',
    'ConfigurationError',
    'PerformanceError',
    'ReportingError',
    'OptimizationError',
    'MonteCarloError',
    'IntegrationError',
]


def get_version() -> str:
    """Get the version of the backtesting framework."""
    return __version__


def configure_logging(level: str = 'INFO') -> None:
    """
    Configure logging for the backtesting framework.

    Args:
        level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
    """
    import logging

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Set backtest logger level
    logger = logging.getLogger('tradingagents.backtest')
    logger.setLevel(getattr(logging, level.upper()))
