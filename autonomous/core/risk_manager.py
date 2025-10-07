"""
Risk Manager
============

Comprehensive risk management with enforcement of position limits,
loss limits, and portfolio risk metrics.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, date
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass, field
import numpy as np
from collections import defaultdict

from pydantic import BaseModel, Field, validator

from .database import (
    DatabaseManager, Position, Order, Trade,
    OrderStatus, PerformanceMetric
)

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level classification"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskViolationType(str, Enum):
    """Types of risk violations"""
    POSITION_SIZE = "position_size"
    DAILY_LOSS = "daily_loss"
    CONCENTRATION = "concentration"
    CORRELATION = "correlation"
    VOLATILITY = "volatility"
    MARGIN = "margin"
    PATTERN_DAY_TRADER = "pattern_day_trader"


@dataclass
class RiskMetrics:
    """Portfolio risk metrics"""
    total_exposure: Decimal = Decimal('0')
    max_position_size: Decimal = Decimal('0')
    concentration_risk: Decimal = Decimal('0')
    portfolio_beta: float = 0.0
    portfolio_volatility: float = 0.0
    value_at_risk_95: Decimal = Decimal('0')
    value_at_risk_99: Decimal = Decimal('0')
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: Decimal = Decimal('0')
    current_drawdown: Decimal = Decimal('0')
    daily_pnl: Decimal = Decimal('0')
    realized_pnl: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    margin_used: Decimal = Decimal('0')
    margin_available: Decimal = Decimal('0')
    correlation_risk: float = 0.0
    sector_concentration: Dict[str, float] = field(default_factory=dict)


@dataclass
class RiskLimits:
    """Risk limits configuration"""
    max_position_size: Decimal = Decimal('0.20')  # 20% per position
    max_daily_loss: Decimal = Decimal('0.05')  # 5% daily loss
    max_total_exposure: Decimal = Decimal('1.0')  # 100% exposure
    max_concentration: Decimal = Decimal('0.30')  # 30% in single stock
    max_sector_exposure: Decimal = Decimal('0.40')  # 40% per sector
    max_correlation: float = 0.70  # Max correlation between positions
    max_volatility: float = 0.30  # 30% annualized volatility
    min_sharpe_ratio: float = 0.5  # Minimum Sharpe ratio
    max_drawdown: Decimal = Decimal('0.15')  # 15% max drawdown
    max_orders_per_day: int = 50
    max_trades_per_symbol_per_day: int = 4  # PDT rule
    min_position_hold_time: int = 60  # Seconds
    required_stop_loss: bool = True
    max_leverage: Decimal = Decimal('2.0')  # 2x leverage


class RiskCheckResult(BaseModel):
    """Result of risk check"""
    approved: bool
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    violations: List[RiskViolationType] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    position_impact: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)


class RiskManager:
    """
    Comprehensive risk management system
    """

    def __init__(self,
                 db_manager: DatabaseManager,
                 limits: Optional[RiskLimits] = None,
                 enable_enforcement: bool = True):
        """
        Initialize risk manager

        Args:
            db_manager: Database manager
            limits: Risk limits configuration
            enable_enforcement: Whether to enforce limits
        """
        self.db = db_manager
        self.limits = limits or RiskLimits()
        self.enable_enforcement = enable_enforcement

        # Cache for performance
        self._position_cache: Dict[str, Position] = {}
        self._metrics_cache: Optional[RiskMetrics] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 60  # Seconds

        # Track daily metrics
        self._daily_trades: List[Trade] = []
        self._daily_orders: List[Order] = []
        self._starting_portfolio_value: Optional[Decimal] = None

        # Sector mapping (simplified)
        self.sector_map = {
            'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology',
            'NVDA': 'Technology', 'AVGO': 'Technology', 'TSM': 'Technology',
            'MU': 'Technology', 'META': 'Technology',
            'JPM': 'Financial', 'BAC': 'Financial', 'GS': 'Financial',
            'XOM': 'Energy', 'CVX': 'Energy',
            'JNJ': 'Healthcare', 'PFE': 'Healthcare',
            # Add more mappings as needed
        }

    async def check_order(self,
                         ticker: str,
                         side: str,
                         quantity: int,
                         price: float,
                         stop_loss: Optional[float] = None) -> RiskCheckResult:
        """
        Check if an order passes risk management rules

        Args:
            ticker: Stock symbol
            side: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Order price
            stop_loss: Stop loss price

        Returns:
            Risk check result
        """
        violations = []
        reasons = []
        recommendations = []

        # Get current metrics
        metrics = await self.calculate_risk_metrics()

        # Calculate order value
        order_value = Decimal(str(price * quantity))

        # Get portfolio value
        portfolio_value = await self._get_portfolio_value()

        if portfolio_value <= 0:
            return RiskCheckResult(
                approved=False,
                risk_score=100,
                risk_level=RiskLevel.CRITICAL,
                reasons=["Invalid portfolio value"]
            )

        # === Check 1: Position Size ===
        position_pct = order_value / portfolio_value

        if position_pct > self.limits.max_position_size:
            violations.append(RiskViolationType.POSITION_SIZE)
            reasons.append(
                f"Position size {position_pct:.1%} exceeds limit "
                f"{self.limits.max_position_size:.1%}"
            )
            recommendations.append(
                f"Reduce quantity to {int(quantity * float(self.limits.max_position_size / position_pct))}"
            )

        # === Check 2: Daily Loss Limit ===
        if metrics.daily_pnl < 0:
            daily_loss_pct = abs(metrics.daily_pnl / portfolio_value)
            if daily_loss_pct >= self.limits.max_daily_loss:
                violations.append(RiskViolationType.DAILY_LOSS)
                reasons.append(
                    f"Daily loss {daily_loss_pct:.1%} at limit "
                    f"{self.limits.max_daily_loss:.1%}"
                )
                recommendations.append("Stop trading for the day")

        # === Check 3: Concentration Risk ===
        existing_position = await self._get_position(ticker)
        if existing_position and side == 'BUY':
            new_position_value = (existing_position.market_value +
                                 order_value)
            concentration = new_position_value / portfolio_value

            if concentration > self.limits.max_concentration:
                violations.append(RiskViolationType.CONCENTRATION)
                reasons.append(
                    f"Concentration {concentration:.1%} exceeds limit "
                    f"{self.limits.max_concentration:.1%}"
                )
                recommendations.append(f"Diversify into other stocks")

        # === Check 4: Sector Concentration ===
        sector = self.sector_map.get(ticker, 'Other')
        sector_exposure = metrics.sector_concentration.get(sector, 0)

        if side == 'BUY':
            new_sector_exposure = sector_exposure + float(position_pct)
            if new_sector_exposure > float(self.limits.max_sector_exposure):
                violations.append(RiskViolationType.CONCENTRATION)
                reasons.append(
                    f"Sector exposure {new_sector_exposure:.1%} exceeds limit "
                    f"{self.limits.max_sector_exposure:.1%}"
                )
                recommendations.append("Diversify into other sectors")

        # === Check 5: Stop Loss Required ===
        if self.limits.required_stop_loss and side == 'BUY':
            if not stop_loss:
                reasons.append("Stop loss required for buy orders")
                recommendations.append(
                    f"Add stop loss at {price * 0.97:.2f} (-3%)"
                )

        # === Check 6: Pattern Day Trader Rule ===
        day_trades_count = await self._count_day_trades(ticker)
        if day_trades_count >= self.limits.max_trades_per_symbol_per_day:
            violations.append(RiskViolationType.PATTERN_DAY_TRADER)
            reasons.append(
                f"PDT rule: {day_trades_count} trades today in {ticker}"
            )

        # === Check 7: Volatility ===
        if metrics.portfolio_volatility > self.limits.max_volatility:
            violations.append(RiskViolationType.VOLATILITY)
            reasons.append(
                f"Portfolio volatility {metrics.portfolio_volatility:.1%} "
                f"exceeds limit {self.limits.max_volatility:.1%}"
            )
            recommendations.append("Reduce position sizes or add hedges")

        # === Check 8: Margin ===
        if metrics.margin_available < order_value:
            violations.append(RiskViolationType.MARGIN)
            reasons.append(
                f"Insufficient margin: need ${order_value:,.2f}, "
                f"have ${metrics.margin_available:,.2f}"
            )

        # === Check 9: Correlation ===
        if side == 'BUY':
            correlation_risk = await self._check_correlation(ticker)
            if correlation_risk > self.limits.max_correlation:
                violations.append(RiskViolationType.CORRELATION)
                reasons.append(
                    f"High correlation {correlation_risk:.2f} with existing positions"
                )
                recommendations.append("Diversify into uncorrelated assets")

        # === Check 10: Max Drawdown ===
        if metrics.current_drawdown > self.limits.max_drawdown:
            violations.append(RiskViolationType.VOLATILITY)
            reasons.append(
                f"In drawdown {metrics.current_drawdown:.1%}, "
                f"limit {self.limits.max_drawdown:.1%}"
            )
            recommendations.append("Reduce risk until recovery")

        # Calculate risk score
        risk_score = self._calculate_risk_score(
            violations, metrics, position_pct
        )

        # Determine risk level
        if risk_score >= 80:
            risk_level = RiskLevel.CRITICAL
        elif risk_score >= 60:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 40:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        # Determine approval
        approved = True
        if self.enable_enforcement:
            # Critical violations always reject
            critical_violations = [
                RiskViolationType.DAILY_LOSS,
                RiskViolationType.MARGIN,
                RiskViolationType.PATTERN_DAY_TRADER
            ]
            if any(v in critical_violations for v in violations):
                approved = False

            # High risk requires override
            if risk_level == RiskLevel.CRITICAL:
                approved = False

        return RiskCheckResult(
            approved=approved,
            risk_score=risk_score,
            risk_level=risk_level,
            violations=violations,
            reasons=reasons,
            position_impact={
                'new_position_size': float(position_pct),
                'new_total_exposure': float(metrics.total_exposure + position_pct),
                'expected_volatility_change': self._estimate_volatility_impact(
                    ticker, position_pct
                )
            },
            recommendations=recommendations
        )

    async def calculate_risk_metrics(self, force_refresh: bool = False) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics

        Args:
            force_refresh: Force cache refresh

        Returns:
            Risk metrics
        """
        # Check cache
        if not force_refresh and self._metrics_cache:
            if (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl:
                return self._metrics_cache

        metrics = RiskMetrics()

        # Get positions
        positions = await self._get_all_positions()
        portfolio_value = await self._get_portfolio_value()

        if not positions or portfolio_value <= 0:
            return metrics

        # Calculate exposure metrics
        total_position_value = Decimal('0')
        max_position_value = Decimal('0')
        sector_values = defaultdict(Decimal)

        for position in positions:
            position_value = position.market_value
            total_position_value += position_value

            # Track max position
            if position_value > max_position_value:
                max_position_value = position_value

            # Track sector exposure
            sector = self.sector_map.get(position.ticker, 'Other')
            sector_values[sector] += position_value

        # Basic metrics
        metrics.total_exposure = total_position_value / portfolio_value
        metrics.max_position_size = max_position_value / portfolio_value
        metrics.concentration_risk = max_position_value / total_position_value

        # Sector concentration
        for sector, value in sector_values.items():
            metrics.sector_concentration[sector] = float(value / portfolio_value)

        # P&L metrics
        metrics.daily_pnl = await self._calculate_daily_pnl()
        metrics.realized_pnl = await self._calculate_realized_pnl()
        metrics.unrealized_pnl = sum(p.unrealized_pnl for p in positions)

        # Risk metrics (simplified)
        returns = await self._get_historical_returns()
        if returns:
            metrics.portfolio_volatility = np.std(returns) * np.sqrt(252)  # Annualized
            metrics.sharpe_ratio = self._calculate_sharpe_ratio(returns)
            metrics.value_at_risk_95 = self._calculate_var(returns, 0.95)
            metrics.value_at_risk_99 = self._calculate_var(returns, 0.99)
            metrics.max_drawdown = self._calculate_max_drawdown(returns)

        # Correlation risk
        metrics.correlation_risk = await self._calculate_correlation_risk()

        # Margin (simplified)
        metrics.margin_used = total_position_value * Decimal('0.5')  # 50% margin
        metrics.margin_available = portfolio_value * Decimal('2') - metrics.margin_used

        # Cache results
        self._metrics_cache = metrics
        self._cache_timestamp = datetime.now()

        return metrics

    async def apply_risk_adjustment(self,
                                   ticker: str,
                                   base_size: float,
                                   confidence: float) -> float:
        """
        Apply risk-based position sizing

        Args:
            ticker: Stock symbol
            base_size: Base position size (% of portfolio)
            confidence: Signal confidence (0-100)

        Returns:
            Risk-adjusted position size
        """
        metrics = await self.calculate_risk_metrics()

        # Start with base size
        adjusted_size = base_size

        # Adjust for confidence
        confidence_multiplier = 0.5 + (confidence / 100) * 0.5  # 0.5x to 1.0x
        adjusted_size *= confidence_multiplier

        # Adjust for portfolio volatility
        if metrics.portfolio_volatility > 0.20:  # High volatility
            adjusted_size *= 0.7
        elif metrics.portfolio_volatility < 0.10:  # Low volatility
            adjusted_size *= 1.2

        # Adjust for drawdown
        if metrics.current_drawdown > Decimal('0.10'):  # In drawdown
            adjusted_size *= 0.5

        # Adjust for concentration
        if ticker in [p.ticker for p in await self._get_all_positions()]:
            adjusted_size *= 0.8  # Reduce if already have position

        # Kelly Criterion (simplified)
        win_rate = 0.55  # Assumed win rate
        avg_win_loss = 1.5  # Assumed win/loss ratio
        kelly_fraction = (win_rate * avg_win_loss - (1 - win_rate)) / avg_win_loss
        kelly_size = min(kelly_fraction, 0.25)  # Cap at 25%

        # Blend base and Kelly
        adjusted_size = (adjusted_size * 0.7) + (kelly_size * 0.3)

        # Ensure within limits
        adjusted_size = max(
            float(self.limits.max_position_size * Decimal('0.25')),  # Min 25% of limit
            min(adjusted_size, float(self.limits.max_position_size))
        )

        return adjusted_size

    async def check_portfolio_health(self) -> Dict[str, Any]:
        """
        Comprehensive portfolio health check

        Returns:
            Health report dictionary
        """
        metrics = await self.calculate_risk_metrics()
        health_issues = []
        health_score = 100

        # Check each metric
        if metrics.total_exposure > Decimal('0.95'):
            health_issues.append("Over-exposed (>95% invested)")
            health_score -= 10

        if metrics.concentration_risk > Decimal('0.40'):
            health_issues.append("High concentration risk (>40% in one position)")
            health_score -= 15

        if metrics.portfolio_volatility > 0.30:
            health_issues.append(f"High volatility ({metrics.portfolio_volatility:.1%})")
            health_score -= 10

        if metrics.sharpe_ratio < 0.5:
            health_issues.append(f"Low Sharpe ratio ({metrics.sharpe_ratio:.2f})")
            health_score -= 10

        if metrics.current_drawdown > Decimal('0.10'):
            health_issues.append(f"In drawdown ({metrics.current_drawdown:.1%})")
            health_score -= 20

        if metrics.daily_pnl < Decimal('-1000'):
            health_issues.append(f"Large daily loss (${metrics.daily_pnl:,.2f})")
            health_score -= 15

        # Determine health status
        if health_score >= 80:
            status = "HEALTHY"
        elif health_score >= 60:
            status = "CAUTION"
        elif health_score >= 40:
            status = "WARNING"
        else:
            status = "CRITICAL"

        return {
            'status': status,
            'score': health_score,
            'issues': health_issues,
            'metrics': {
                'exposure': float(metrics.total_exposure),
                'volatility': metrics.portfolio_volatility,
                'sharpe': metrics.sharpe_ratio,
                'var_95': float(metrics.value_at_risk_95),
                'daily_pnl': float(metrics.daily_pnl),
                'drawdown': float(metrics.current_drawdown)
            },
            'recommendations': self._generate_recommendations(metrics, health_issues)
        }

    # === Helper Methods ===

    async def _get_all_positions(self) -> List[Position]:
        """Get all active positions"""
        return self.db.get_active_positions()

    async def _get_position(self, ticker: str) -> Optional[Position]:
        """Get specific position"""
        with self.db.get_session() as session:
            return session.query(Position).filter_by(ticker=ticker).first()

    async def _get_portfolio_value(self) -> Decimal:
        """Get total portfolio value"""
        positions = await self._get_all_positions()
        return sum(p.market_value for p in positions)

    async def _calculate_daily_pnl(self) -> Decimal:
        """Calculate today's P&L"""
        with self.db.get_session() as session:
            today_trades = session.query(Trade).filter(
                Trade.executed_at >= date.today()
            ).all()

            daily_pnl = sum(t.pnl or 0 for t in today_trades)

            # Add unrealized P&L changes
            positions = await self._get_all_positions()
            for position in positions:
                # Simplified - would compare to morning snapshot
                daily_pnl += position.unrealized_pnl * Decimal('0.1')  # Estimate

            return daily_pnl

    async def _calculate_realized_pnl(self) -> Decimal:
        """Calculate realized P&L"""
        with self.db.get_session() as session:
            all_trades = session.query(Trade).all()
            return sum(t.pnl or 0 for t in all_trades)

    async def _count_day_trades(self, ticker: str) -> int:
        """Count day trades for PDT rule"""
        with self.db.get_session() as session:
            today_orders = session.query(Order).filter(
                Order.ticker == ticker,
                Order.created_at >= date.today()
            ).all()
            return len(today_orders)

    async def _check_correlation(self, ticker: str) -> float:
        """Check correlation with existing positions"""
        # Simplified correlation check
        # In production, would calculate actual correlation matrix
        positions = await self._get_all_positions()

        if not positions:
            return 0.0

        # High correlation for same sector
        sector = self.sector_map.get(ticker, 'Other')
        same_sector_positions = [
            p for p in positions
            if self.sector_map.get(p.ticker, 'Other') == sector
        ]

        if same_sector_positions:
            return 0.8  # High correlation assumed for same sector

        return 0.3  # Low correlation for different sectors

    async def _get_historical_returns(self, days: int = 30) -> List[float]:
        """Get historical portfolio returns"""
        with self.db.get_session() as session:
            snapshots = session.query(PerformanceMetric).filter(
                PerformanceMetric.date >= datetime.now() - timedelta(days=days)
            ).order_by(PerformanceMetric.date).all()

            if len(snapshots) < 2:
                return []

            returns = []
            for i in range(1, len(snapshots)):
                if snapshots[i-1].total_pnl and snapshots[i].total_pnl:
                    daily_return = float(
                        (snapshots[i].total_pnl - snapshots[i-1].total_pnl) /
                        abs(snapshots[i-1].total_pnl)
                    )
                    returns.append(daily_return)

            return returns

    def _calculate_risk_score(self,
                             violations: List[RiskViolationType],
                             metrics: RiskMetrics,
                             position_size: Decimal) -> float:
        """Calculate risk score (0-100)"""
        score = 0

        # Violation weights
        violation_weights = {
            RiskViolationType.DAILY_LOSS: 30,
            RiskViolationType.MARGIN: 25,
            RiskViolationType.POSITION_SIZE: 20,
            RiskViolationType.CONCENTRATION: 15,
            RiskViolationType.PATTERN_DAY_TRADER: 20,
            RiskViolationType.VOLATILITY: 10,
            RiskViolationType.CORRELATION: 10
        }

        for violation in violations:
            score += violation_weights.get(violation, 5)

        # Add metric-based scoring
        if metrics.portfolio_volatility > 0.25:
            score += 10
        if metrics.current_drawdown > Decimal('0.10'):
            score += 15
        if float(position_size) > 0.15:
            score += 10

        return min(score, 100)

    def _calculate_sharpe_ratio(self, returns: List[float],
                               risk_free_rate: float = 0.03) -> float:
        """Calculate Sharpe ratio"""
        if not returns:
            return 0.0

        mean_return = np.mean(returns) * 252  # Annualized
        std_return = np.std(returns) * np.sqrt(252)

        if std_return == 0:
            return 0.0

        return (mean_return - risk_free_rate) / std_return

    def _calculate_var(self, returns: List[float],
                      confidence: float) -> Decimal:
        """Calculate Value at Risk"""
        if not returns:
            return Decimal('0')

        percentile = (1 - confidence) * 100
        var = np.percentile(returns, percentile)
        return Decimal(str(abs(var)))

    def _calculate_max_drawdown(self, returns: List[float]) -> Decimal:
        """Calculate maximum drawdown"""
        if not returns:
            return Decimal('0')

        cumulative = np.cumprod(1 + np.array(returns))
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        return Decimal(str(abs(min(drawdown))))

    async def _calculate_correlation_risk(self) -> float:
        """Calculate overall portfolio correlation risk"""
        # Simplified - would use actual correlation matrix
        positions = await self._get_all_positions()

        if len(positions) < 2:
            return 0.0

        # Check sector concentration
        sectors = [self.sector_map.get(p.ticker, 'Other') for p in positions]
        unique_sectors = len(set(sectors))

        if unique_sectors == 1:
            return 0.9  # All in same sector
        elif unique_sectors == 2:
            return 0.6
        else:
            return 0.3

    def _estimate_volatility_impact(self, ticker: str,
                                   position_size: Decimal) -> float:
        """Estimate impact on portfolio volatility"""
        # Simplified estimate
        # Individual stock volatility assumed at 30%
        stock_vol = 0.30
        impact = float(position_size) * stock_vol * 0.5  # Rough estimate
        return impact

    def _generate_recommendations(self, metrics: RiskMetrics,
                                 issues: List[str]) -> List[str]:
        """Generate risk management recommendations"""
        recommendations = []

        if metrics.concentration_risk > Decimal('0.30'):
            recommendations.append("Diversify portfolio - reduce largest position")

        if metrics.portfolio_volatility > 0.25:
            recommendations.append("Consider hedging with options or inverse ETFs")

        if metrics.current_drawdown > Decimal('0.10'):
            recommendations.append("Reduce position sizes until recovery")

        if metrics.sharpe_ratio < 0.5:
            recommendations.append("Review strategy - risk-adjusted returns are low")

        if "Over-exposed" in str(issues):
            recommendations.append("Keep some cash reserve for opportunities")

        return recommendations


# Example usage
async def main():
    """Example of using the risk manager"""
    from .database import DatabaseManager

    # Initialize
    db = DatabaseManager("postgresql://trader:password@localhost/trading_db")
    risk_manager = RiskManager(db)

    # Check an order
    result = await risk_manager.check_order(
        ticker="AAPL",
        side="BUY",
        quantity=1000,
        price=150.00,
        stop_loss=145.00
    )

    print(f"Approved: {result.approved}")
    print(f"Risk Score: {result.risk_score}")
    print(f"Risk Level: {result.risk_level}")
    print(f"Violations: {result.violations}")
    print(f"Reasons: {result.reasons}")
    print(f"Recommendations: {result.recommendations}")

    # Check portfolio health
    health = await risk_manager.check_portfolio_health()
    print(f"\nPortfolio Health: {health['status']}")
    print(f"Health Score: {health['score']}")
    print(f"Issues: {health['issues']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import asyncio
    asyncio.run(main())