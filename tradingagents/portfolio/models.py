"""Portfolio data models and structures."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Position:
    """Represents a single position in the portfolio."""
    ticker: str
    shares: float
    avg_cost: float
    current_price: Optional[float] = None

    @property
    def cost_basis(self) -> float:
        """Total cost basis of the position."""
        return self.shares * self.avg_cost

    @property
    def market_value(self) -> Optional[float]:
        """Current market value of the position."""
        if self.current_price is None:
            return None
        return self.shares * self.current_price

    @property
    def unrealized_gain_loss(self) -> Optional[float]:
        """Unrealized gain/loss for this position."""
        if self.market_value is None:
            return None
        return self.market_value - self.cost_basis

    @property
    def unrealized_gain_loss_pct(self) -> Optional[float]:
        """Unrealized gain/loss percentage."""
        if self.market_value is None:
            return None
        return ((self.market_value - self.cost_basis) / self.cost_basis) * 100


@dataclass
class Portfolio:
    """Represents a complete portfolio with multiple positions."""
    positions: Dict[str, Position]
    analysis_date: str
    name: str = "My Portfolio"

    @property
    def tickers(self) -> List[str]:
        """List of all tickers in the portfolio."""
        return list(self.positions.keys())

    @property
    def total_cost_basis(self) -> float:
        """Total cost basis of the portfolio."""
        return sum(pos.cost_basis for pos in self.positions.values())

    @property
    def total_market_value(self) -> Optional[float]:
        """Total market value of the portfolio."""
        values = [pos.market_value for pos in self.positions.values()]
        if None in values:
            return None
        return sum(values)

    @property
    def total_unrealized_gain_loss(self) -> Optional[float]:
        """Total unrealized gain/loss for the portfolio."""
        if self.total_market_value is None:
            return None
        return self.total_market_value - self.total_cost_basis

    @property
    def total_unrealized_gain_loss_pct(self) -> Optional[float]:
        """Total unrealized gain/loss percentage."""
        if self.total_market_value is None:
            return None
        return ((self.total_market_value - self.total_cost_basis) /
                self.total_cost_basis) * 100

    def get_position_weights(self) -> Dict[str, float]:
        """Get the weight of each position as percentage of portfolio."""
        if self.total_market_value is None:
            # Fall back to cost basis if no market values
            total = self.total_cost_basis
            return {
                ticker: (pos.cost_basis / total) * 100
                for ticker, pos in self.positions.items()
            }

        return {
            ticker: (pos.market_value / self.total_market_value) * 100
            for ticker, pos in self.positions.items()
        }

    def to_dict(self) -> Dict:
        """Convert portfolio to dictionary representation."""
        return {
            "name": self.name,
            "analysis_date": self.analysis_date,
            "total_cost_basis": self.total_cost_basis,
            "total_market_value": self.total_market_value,
            "total_unrealized_gain_loss": self.total_unrealized_gain_loss,
            "total_unrealized_gain_loss_pct": self.total_unrealized_gain_loss_pct,
            "positions": {
                ticker: {
                    "shares": pos.shares,
                    "avg_cost": pos.avg_cost,
                    "current_price": pos.current_price,
                    "cost_basis": pos.cost_basis,
                    "market_value": pos.market_value,
                    "unrealized_gain_loss": pos.unrealized_gain_loss,
                    "unrealized_gain_loss_pct": pos.unrealized_gain_loss_pct,
                }
                for ticker, pos in self.positions.items()
            },
            "position_weights": self.get_position_weights(),
        }


@dataclass
class PortfolioAnalysisResult:
    """Results from portfolio analysis."""
    portfolio: Portfolio
    individual_analyses: Dict[str, Dict]  # ticker -> analysis result
    portfolio_metrics: Dict = field(default_factory=dict)
    portfolio_recommendation: Optional[str] = None
    rebalancing_suggestions: List[Dict] = field(default_factory=list)
    risk_assessment: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert analysis result to dictionary."""
        return {
            "portfolio": self.portfolio.to_dict(),
            "individual_analyses": self.individual_analyses,
            "portfolio_metrics": self.portfolio_metrics,
            "portfolio_recommendation": self.portfolio_recommendation,
            "rebalancing_suggestions": self.rebalancing_suggestions,
            "risk_assessment": self.risk_assessment,
        }
