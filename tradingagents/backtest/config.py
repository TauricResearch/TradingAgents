"""
Configuration management for the backtesting framework.

This module provides configuration classes and utilities for managing
backtest parameters, ensuring type safety and validation.
"""

from dataclasses import dataclass, field, asdict
from decimal import Decimal
from datetime import datetime, time
from typing import Optional, Dict, Any, List
from enum import Enum
import json
import logging

from .exceptions import InvalidConfigError, MissingConfigError


logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Supported order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class DataSource(Enum):
    """Supported data sources."""
    YFINANCE = "yfinance"
    CSV = "csv"
    ALPHA_VANTAGE = "alpha_vantage"
    LOCAL = "local"
    CUSTOM = "custom"


class SlippageModel(Enum):
    """Slippage modeling approaches."""
    FIXED = "fixed"  # Fixed percentage
    VOLUME_BASED = "volume_based"  # Based on volume
    SPREAD_BASED = "spread_based"  # Based on bid-ask spread
    CUSTOM = "custom"  # Custom function


class CommissionModel(Enum):
    """Commission modeling approaches."""
    FIXED_PER_TRADE = "fixed_per_trade"  # Fixed amount per trade
    PER_SHARE = "per_share"  # Amount per share
    PERCENTAGE = "percentage"  # Percentage of trade value
    TIERED = "tiered"  # Tiered based on volume
    CUSTOM = "custom"  # Custom function


@dataclass
class BacktestConfig:
    """
    Configuration for backtesting.

    Attributes:
        initial_capital: Starting capital for the backtest
        start_date: Start date for the backtest (YYYY-MM-DD)
        end_date: End date for the backtest (YYYY-MM-DD)
        commission: Commission rate (as decimal, e.g., 0.001 for 0.1%)
        slippage: Slippage rate (as decimal, e.g., 0.0005 for 0.05%)
        benchmark: Benchmark ticker for comparison (e.g., 'SPY')
        data_source: Source for historical data
        commission_model: Commission calculation model
        slippage_model: Slippage calculation model
        max_position_size: Maximum position size as fraction of portfolio (None = unlimited)
        max_leverage: Maximum leverage allowed (1.0 = no leverage)
        allow_short: Whether to allow short positions
        margin_requirement: Margin requirement for positions (as decimal)
        risk_free_rate: Annual risk-free rate for metrics (as decimal)
        trading_hours: Trading hours enforcement (None = 24/7)
        market_impact: Whether to model market impact
        partial_fills: Whether to allow partial fills
        time_zone: Time zone for timestamps
        cache_data: Whether to cache historical data
        cache_dir: Directory for data cache
        log_level: Logging level
        progress_bar: Whether to show progress bar
        random_seed: Random seed for reproducibility
    """

    # Core parameters
    initial_capital: Decimal
    start_date: str
    end_date: str

    # Costs
    commission: Decimal = Decimal("0.0")
    slippage: Decimal = Decimal("0.0")
    commission_model: CommissionModel = CommissionModel.PERCENTAGE
    slippage_model: SlippageModel = SlippageModel.FIXED

    # Benchmark
    benchmark: Optional[str] = None

    # Data
    data_source: DataSource = DataSource.YFINANCE
    cache_data: bool = True
    cache_dir: Optional[str] = None

    # Risk controls
    max_position_size: Optional[Decimal] = None
    max_leverage: Decimal = Decimal("1.0")
    allow_short: bool = False
    margin_requirement: Decimal = Decimal("0.5")

    # Performance metrics
    risk_free_rate: Decimal = Decimal("0.02")  # 2% annual

    # Execution
    trading_hours: Optional[Dict[str, Any]] = None
    market_impact: bool = False
    partial_fills: bool = False

    # System
    time_zone: str = "America/New_York"
    log_level: str = "INFO"
    progress_bar: bool = True
    random_seed: Optional[int] = None

    # Custom parameters
    custom_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()

    def _validate(self):
        """Validate configuration parameters."""
        # Validate capital
        if self.initial_capital <= 0:
            raise InvalidConfigError("Initial capital must be positive")

        # Validate dates
        try:
            start = datetime.strptime(self.start_date, "%Y-%m-%d")
            end = datetime.strptime(self.end_date, "%Y-%m-%d")
        except ValueError as e:
            raise InvalidConfigError(f"Invalid date format: {e}")

        if start >= end:
            raise InvalidConfigError("Start date must be before end date")

        # Validate rates
        if self.commission < 0:
            raise InvalidConfigError("Commission cannot be negative")

        if self.slippage < 0:
            raise InvalidConfigError("Slippage cannot be negative")

        if self.risk_free_rate < 0:
            raise InvalidConfigError("Risk-free rate cannot be negative")

        # Validate leverage and margin
        if self.max_leverage < Decimal("1.0"):
            raise InvalidConfigError("Max leverage must be >= 1.0")

        if not (Decimal("0.0") < self.margin_requirement <= Decimal("1.0")):
            raise InvalidConfigError("Margin requirement must be between 0 and 1")

        # Validate position size
        if self.max_position_size is not None:
            if not (Decimal("0.0") < self.max_position_size <= Decimal("1.0")):
                raise InvalidConfigError("Max position size must be between 0 and 1")

        # Convert enum strings if necessary
        if isinstance(self.commission_model, str):
            self.commission_model = CommissionModel(self.commission_model)

        if isinstance(self.slippage_model, str):
            self.slippage_model = SlippageModel(self.slippage_model)

        if isinstance(self.data_source, str):
            self.data_source = DataSource(self.data_source)

        logger.info(f"Backtest config validated: {self.start_date} to {self.end_date}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        result = asdict(self)
        # Convert Decimal to float for JSON serialization
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = float(value)
            elif isinstance(value, Enum):
                result[key] = value.value
        return result

    def to_json(self, filepath: Optional[str] = None) -> str:
        """
        Serialize configuration to JSON.

        Args:
            filepath: Optional file path to save JSON

        Returns:
            JSON string representation
        """
        json_str = json.dumps(self.to_dict(), indent=2)

        if filepath:
            with open(filepath, 'w') as f:
                f.write(json_str)
            logger.info(f"Config saved to {filepath}")

        return json_str

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'BacktestConfig':
        """
        Create configuration from dictionary.

        Args:
            config_dict: Dictionary of configuration parameters

        Returns:
            BacktestConfig instance
        """
        # Convert numeric values to Decimal
        decimal_fields = [
            'initial_capital', 'commission', 'slippage',
            'max_position_size', 'max_leverage', 'margin_requirement',
            'risk_free_rate'
        ]

        for field_name in decimal_fields:
            if field_name in config_dict and config_dict[field_name] is not None:
                config_dict[field_name] = Decimal(str(config_dict[field_name]))

        # Convert enum values
        enum_fields = {
            'commission_model': CommissionModel,
            'slippage_model': SlippageModel,
            'data_source': DataSource,
        }

        for field_name, enum_class in enum_fields.items():
            if field_name in config_dict and config_dict[field_name] is not None:
                if isinstance(config_dict[field_name], str):
                    config_dict[field_name] = enum_class(config_dict[field_name])

        return cls(**config_dict)

    @classmethod
    def from_json(cls, filepath: str) -> 'BacktestConfig':
        """
        Load configuration from JSON file.

        Args:
            filepath: Path to JSON configuration file

        Returns:
            BacktestConfig instance
        """
        with open(filepath, 'r') as f:
            config_dict = json.load(f)

        return cls.from_dict(config_dict)


@dataclass
class WalkForwardConfig:
    """
    Configuration for walk-forward analysis.

    Attributes:
        in_sample_months: Number of months for in-sample (training) period
        out_sample_months: Number of months for out-of-sample (testing) period
        step_months: Number of months to step forward (default: out_sample_months)
        optimization_metric: Metric to optimize ('sharpe', 'return', 'sortino', etc.)
        min_periods: Minimum number of periods required
        anchored: Whether to use anchored walk-forward (growing window)
    """
    in_sample_months: int
    out_sample_months: int
    step_months: Optional[int] = None
    optimization_metric: str = "sharpe"
    min_periods: int = 20
    anchored: bool = False

    def __post_init__(self):
        """Validate configuration."""
        if self.step_months is None:
            self.step_months = self.out_sample_months

        if self.in_sample_months <= 0:
            raise InvalidConfigError("In-sample months must be positive")

        if self.out_sample_months <= 0:
            raise InvalidConfigError("Out-of-sample months must be positive")

        if self.step_months <= 0:
            raise InvalidConfigError("Step months must be positive")

        if self.min_periods <= 0:
            raise InvalidConfigError("Min periods must be positive")


@dataclass
class MonteCarloConfig:
    """
    Configuration for Monte Carlo simulation.

    Attributes:
        n_simulations: Number of simulations to run
        method: Simulation method ('resample_trades', 'resample_returns', 'parametric')
        confidence_levels: Confidence levels for intervals (e.g., [0.90, 0.95, 0.99])
        random_seed: Random seed for reproducibility
        preserve_order: Whether to preserve trade order in resampling
    """
    n_simulations: int = 10000
    method: str = "resample_trades"
    confidence_levels: List[float] = field(default_factory=lambda: [0.90, 0.95, 0.99])
    random_seed: Optional[int] = None
    preserve_order: bool = False

    def __post_init__(self):
        """Validate configuration."""
        if self.n_simulations <= 0:
            raise InvalidConfigError("Number of simulations must be positive")

        if self.method not in ['resample_trades', 'resample_returns', 'parametric']:
            raise InvalidConfigError(f"Invalid Monte Carlo method: {self.method}")

        for level in self.confidence_levels:
            if not (0 < level < 1):
                raise InvalidConfigError(f"Invalid confidence level: {level}")


def create_default_config(
    initial_capital: float = 100000.0,
    start_date: str = "2020-01-01",
    end_date: str = "2023-12-31",
    **kwargs
) -> BacktestConfig:
    """
    Create a default backtest configuration with sensible defaults.

    Args:
        initial_capital: Starting capital
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        **kwargs: Additional configuration parameters

    Returns:
        BacktestConfig instance
    """
    config_dict = {
        'initial_capital': Decimal(str(initial_capital)),
        'start_date': start_date,
        'end_date': end_date,
        'commission': Decimal("0.001"),  # 0.1%
        'slippage': Decimal("0.0005"),  # 0.05%
        'benchmark': 'SPY',
        **kwargs
    }

    return BacktestConfig.from_dict(config_dict)
