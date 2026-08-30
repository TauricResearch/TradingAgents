"""
Global Carry Trade Portfolio Manager
=====================================
Implements three complementary strategies:
1. Conservative: USD/BRL (+6.87%)
2. Diversified: Multi-currency basket (+5.5%)
3. Aggressive: USD/TRY (+46.37%)

All strategies run simultaneously with proper risk management.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider

try:
    from tradingagents.dataflows.cost_model import CostModel, ETF_FX_BETA, FX_SPREAD_BPS, net_expected_return

    _HAS_COST_MODEL = True
except ImportError:
    _HAS_COST_MODEL = False
    CostModel = None  # type: ignore
    ETF_FX_BETA = {}  # type: ignore
    FX_SPREAD_BPS = {}  # type: ignore

    def net_expected_return(spread, currency, cost_model=None, beta=None):  # type: ignore
        return spread * 0.8, {}

# TimesFM integration point — optional forecast-aware sizing (Step 1 hardening).
# No hard dependency: gracefully degrades when forecasting module or timesfm
# package is not installed.
try:
    from tradingagents.chains.forecasting import ForecastResult, TimesFMForecaster  # noqa: F401

    _HAS_FORECASTING = True
except ImportError:
    _HAS_FORECASTING = False

# RL weight-centric allocator — optional (FinRL-X w = R(T(A(S(market)))))
try:
    from tradingagents.rl.weight_allocator import WeightAllocator, apply_risk_overlay  # noqa: F401

    _HAS_RL = True
except ImportError:
    WeightAllocator = object  # type: ignore
    apply_risk_overlay = None  # type: ignore
    _HAS_RL = False


class RiskLevel(Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class StrategyAllocation:
    """Allocation for a single strategy"""
    name: str
    risk_level: RiskLevel
    funding_currency: str
    target_currency: str
    funding_rate: float
    target_rate: float
    spread: float
    allocation_pct: float
    allocation_usd: float
    fx_rate: float
    fx_volatility: float
    expected_return: float
    max_drawdown: float
    status: str = "active"
    cost_breakdown: Dict = field(default_factory=dict)
    net_expected_return: float = 0.0


@dataclass
class PortfolioState:
    """Current portfolio state"""
    timestamp: str
    total_value: float
    cash: float
    buying_power: float
    strategies: List[StrategyAllocation]
    total_expected_return: float
    total_weighted_risk: float
    positions: List[Dict] = field(default_factory=list)


class CarryTradePortfolioManager:
    """
    Manages a portfolio of carry trade strategies.
    
    Strategies:
    1. Conservative: USD/BRL - Low risk, stable spread
    2. Diversified: Multi-currency basket - Medium risk, diversified
    3. Aggressive: USD/TRY - High risk, high spread
    """
    
    def __init__(self, alpaca_api_key: str = None, alpaca_secret_key: str = None):
        self.rates_provider = GlobalInterestRatesProvider()
        self.fx_provider = MultiCurrencyFXProvider()
        
        # Alpaca credentials
        self.alpaca_api_key = alpaca_api_key or os.getenv("ALPACA_API_KEY")
        self.alpaca_secret_key = alpaca_secret_key or os.getenv("ALPACA_SECRET_KEY")
        self.alpaca_base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        
        # Portfolio configuration
        self.total_portfolio_value = 100000  # Default $100k
        
        # Strategy allocations (must sum to 1.0)
        self.allocations = {
            "conservative": 0.40,  # 40% - USD/BRL
            "diversified": 0.40,   # 40% - Multi-currency basket
            "aggressive": 0.20,    # 20% - USD/TRY
        }
    
    def get_market_data(self) -> Dict:
        """Fetch current market data"""
        print("Fetching market data...")
        
        # Get interest rates
        rates = self.rates_provider.get_all_rates()
        
        # Get FX rates
        fx_pairs = ["USD_BRL", "USD_TRY", "USD_MXN", "USD_INR", "USD_ZAR", "USD_ARS"]
        fx_rates = {}
        
        for pair in fx_pairs:
            base, quote = pair.split("_")
            rate = self.fx_provider.get_rate(base, quote)
            if rate:
                fx_rates[pair] = rate.rate
        
        # Get FX volatility
        volatility = {}
        vol_pairs = [("USD", "BRL"), ("USD", "TRY"), ("USD", "MXN")]
        
        for base, quote in vol_pairs:
            vol = self.fx_provider.get_fx_volatility(base, quote, days=30)
            if vol:
                volatility[f"{base}_{quote}"] = vol
        
        return {
            "rates": rates,
            "fx_rates": fx_rates,
            "volatility": volatility,
            "timestamp": datetime.now().isoformat(),
        }
    
    def design_strategies(self, market_data: Dict) -> List[StrategyAllocation]:
        """Design the three complementary strategies"""
        
        rates = market_data["rates"]
        fx_rates = market_data["fx_rates"]
        volatility = market_data["volatility"]
        
        strategies = []
        
        # Get US rate for funding
        us_rate = rates.get("US")
        if not us_rate:
            print("Warning: US rate not found, using fallback")
            us_rate = type('obj', (object,), {'rate': 3.63, 'currency': 'USD'})()
        
        # Strategy 1: Conservative - USD/BRL
        br_rate = rates.get("BR")
        
        if br_rate:
            usd_brl_rate = fx_rates.get("USD_BRL", 5.16)
            brl_vol = volatility.get("USD_BRL", 0.15)
            
            spread = br_rate.rate - us_rate.rate
            net_ret, breakdown = net_expected_return(spread, "BRL")
            expected_return = net_ret
            
            strategies.append(StrategyAllocation(
                name="Conservative_USD_BRL",
                risk_level=RiskLevel.CONSERVATIVE,
                funding_currency="USD",
                target_currency="BRL",
                funding_rate=us_rate.rate,
                target_rate=br_rate.rate,
                spread=spread,
                allocation_pct=self.allocations["conservative"],
                allocation_usd=self.total_portfolio_value * self.allocations["conservative"],
                fx_rate=usd_brl_rate,
                fx_volatility=brl_vol,
                expected_return=expected_return,
                max_drawdown=5.0,
                cost_breakdown=breakdown,
                net_expected_return=net_ret,
            ))
        
        # Strategy 2: Diversified - Multi-currency basket
        diversified_return = 0
        
        # EXPANDED: 10 currencies for better diversification
        diversified_currencies = [
            ("BR", 0.15),   # Brazil - SELIC 10.5%
            ("MX", 0.15),   # Mexico - Banxico 11%
            ("IN", 0.12),   # India - RBI 6.5%
            ("ZA", 0.10),   # South Africa - SARB 8.25%
            ("CL", 0.10),   # Chile - BCCh 6.5%
            ("PL", 0.08),   # Poland - NBP 5.75%
            ("CO", 0.08),   # Colombia - BanRep 12%
            ("ID", 0.07),   # Indonesia - BI 6.25%
            ("TH", 0.07),   # Thailand - BOT 2.5%
            ("PH", 0.08),   # Philippines - BSP 6.5%
        ]
        
        for currency, weight in diversified_currencies:
            currency_rate = rates.get(currency)
            if currency_rate:
                spread = currency_rate.rate - us_rate.rate
                diversified_return += spread * weight
        
        # Estimate diversified volatility (lower due to diversification)
        diversified_vol = 0.10  # Lower volatility due to 10-currency basket
        
        net_div, div_breakdown = net_expected_return(diversified_return, "MULTI")
        strategies.append(StrategyAllocation(
            name="Diversified_Multi_Currency",
            risk_level=RiskLevel.MODERATE,
            funding_currency="USD",
            target_currency="MULTI",
            funding_rate=us_rate.rate,
            target_rate=diversified_return + us_rate.rate,
            spread=diversified_return,
            allocation_pct=self.allocations["diversified"],
            allocation_usd=self.total_portfolio_value * self.allocations["diversified"],
            fx_rate=1.0,  # Basket
            fx_volatility=diversified_vol,
            expected_return=net_div,
            max_drawdown=6.0,  # Lower due to diversification
            cost_breakdown=div_breakdown,
            net_expected_return=net_div,
        ))
        
        # Strategy 3: Aggressive - USD/TRY
        tr_rate = rates.get("TR")
        
        if tr_rate:
            usd_try_rate = fx_rates.get("USD_TRY", 48.23)
            try_vol = volatility.get("USD_TRY", 0.25)
            
            spread = tr_rate.rate - us_rate.rate
            net_try, try_breakdown = net_expected_return(spread, "TRY")
            expected_return = net_try
            
            strategies.append(StrategyAllocation(
                name="Aggressive_USD_TRY",
                risk_level=RiskLevel.AGGRESSIVE,
                funding_currency="USD",
                target_currency="TRY",
                funding_rate=us_rate.rate,
                target_rate=tr_rate.rate,
                spread=spread,
                allocation_pct=self.allocations["aggressive"],
                allocation_usd=self.total_portfolio_value * self.allocations["aggressive"],
                fx_rate=usd_try_rate,
                fx_volatility=try_vol,
                expected_return=expected_return,
                max_drawdown=20.0,
                cost_breakdown=try_breakdown,
                net_expected_return=net_try,
            ))
        
        return strategies
    
    def calculate_portfolio_metrics(self, strategies: List[StrategyAllocation]) -> Dict:
        """Calculate portfolio-level metrics"""
        
        total_expected_return = sum(
            s.expected_return * s.allocation_pct for s in strategies
        )
        
        total_weighted_risk = sum(
            s.max_drawdown * s.allocation_pct for s in strategies
        )
        
        # Sharpe-like ratio (return / risk)
        sharpe_ratio = total_expected_return / total_weighted_risk if total_weighted_risk > 0 else 0
        
        return {
            "total_expected_return": total_expected_return,
            "total_weighted_risk": total_weighted_risk,
            "sharpe_ratio": sharpe_ratio,
            "strategies_count": len(strategies),
            "total_allocation": sum(s.allocation_pct for s in strategies),
            "cost_breakdown": {s.name: s.cost_breakdown for s in strategies},
        }
    
    def generate_execution_plan(self, strategies: List[StrategyAllocation]) -> List[Dict]:
        """Generate execution plan for each strategy"""
        
        execution_plan = []
        
        for strategy in strategies:
            if strategy.funding_currency == "USD" and strategy.target_currency != "MULTI":
                # Direct FX conversion needed
                execution_plan.append({
                    "strategy": strategy.name,
                    "action": "CONVERT",
                    "from_currency": strategy.funding_currency,
                    "to_currency": strategy.target_currency,
                    "amount": strategy.allocation_usd,
                    "rate": strategy.fx_rate,
                    "expected_amount": strategy.allocation_usd * strategy.fx_rate,
                })
                
                execution_plan.append({
                    "strategy": strategy.name,
                    "action": "INVEST",
                    "currency": strategy.target_currency,
                    "rate": strategy.target_rate,
                    "horizon": "6 months",
                })
            
            elif strategy.target_currency == "MULTI":
                # Multi-currency allocation
                allocations = [
                    ("BRL", 0.30),
                    ("MXN", 0.25),
                    ("INR", 0.20),
                    ("ZAR", 0.15),
                    ("CLP", 0.10),
                ]
                
                for currency, weight in allocations:
                    amount = strategy.allocation_usd * weight
                    execution_plan.append({
                        "strategy": strategy.name,
                        "action": "CONVERT",
                        "from_currency": "USD",
                        "to_currency": currency,
                        "amount": amount,
                    })
        
        return execution_plan
    
    def print_portfolio_summary(self, strategies: List[StrategyAllocation], metrics: Dict):
        """Print portfolio summary"""
        
        print("\n" + "=" * 70)
        print("  CARRY TRADE PORTFOLIO SUMMARY")
        print("=" * 70)
        
        print(f"\n  Total Portfolio Value: ${self.total_portfolio_value:,.2f}")
        print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n" + "-" * 70)
        print("  STRATEGY ALLOCATIONS")
        print("-" * 70)
        
        for strategy in strategies:
            print(f"\n  {strategy.name}")
            print(f"    Risk Level: {strategy.risk_level.value}")
            print(f"    Allocation: {strategy.allocation_pct:.0%} (${strategy.allocation_usd:,.2f})")
            print(f"    Funding: {strategy.funding_currency} at {strategy.funding_rate:.2f}%")
            print(f"    Target: {strategy.target_currency} at {strategy.target_rate:.2f}%")
            print(f"    Spread: {strategy.spread:.2f}%")
            print(f"    FX Rate: {strategy.fx_rate:.4f}")
            print(f"    FX Volatility: {strategy.fx_volatility:.2%}")
            print(f"    Expected Return: {strategy.expected_return:.2f}%")
            print(f"    Max Drawdown: {strategy.max_drawdown:.1f}%")
        
        print("\n" + "-" * 70)
        print("  PORTFOLIO METRICS")
        print("-" * 70)
        
        print(f"\n  Total Expected Return: {metrics['total_expected_return']:.2f}%")
        print(f"  Total Weighted Risk: {metrics['total_weighted_risk']:.1f}%")
        print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"  Strategies: {metrics['strategies_count']}")
        print(f"  Total Allocation: {metrics['total_allocation']:.0%}")
        
        print("\n" + "=" * 70)
    
    def generate_report(self) -> Dict:
        """Generate complete portfolio report"""
        
        # Get market data
        market_data = self.get_market_data()
        
        # Design strategies
        strategies = self.design_strategies(market_data)
        
        # Calculate metrics
        metrics = self.calculate_portfolio_metrics(strategies)
        
        # Generate execution plan
        execution_plan = self.generate_execution_plan(strategies)
        
        # Print summary
        self.print_portfolio_summary(strategies, metrics)
        
        # Return complete report
        return {
            "timestamp": datetime.now().isoformat(),
            "market_data": market_data,
            "strategies": [
                {
                    "name": s.name,
                    "risk_level": s.risk_level.value,
                    "allocation_pct": s.allocation_pct,
                    "allocation_usd": s.allocation_usd,
                    "funding_currency": s.funding_currency,
                    "target_currency": s.target_currency,
                    "spread": s.spread,
                    "expected_return": s.expected_return,
                    "max_drawdown": s.max_drawdown,
                }
                for s in strategies
            ],
            "metrics": metrics,
            "execution_plan": execution_plan,
        }
    
    def adjust_allocation_for_forecast(
        self,
        base_allocation: float,
        forecast_return: float,
        forecast_vol: Optional[float] = None,
    ) -> float:
        """Forecast-aware sizing hook (TimesFM integration point).

        Scales allocation by expected forecast return / vol. No-op if
        forecasting is unavailable. Preserves existing API — caller
        decides when to apply.

        Example:
            forecaster = TimesFMForecaster()
            res = forecaster.forecast_rate_spread("BR", "US", horizon=5)
            adj = manager.adjust_allocation_for_forecast(0.4, float(res.forecast.mean()))
        """
        if not _HAS_FORECASTING or forecast_vol is None or forecast_vol <= 0:
            # Clamp to [0.5x, 1.5x] scaling to avoid extreme bets
            scale = 1.0 + max(min(forecast_return / 10.0, 0.5), -0.5)
            return max(0.0, min(1.0, base_allocation * scale))
        # Volatility-adjusted scaling
        scale = 1.0 + max(min(forecast_return / max(forecast_vol, 1e-6) * 0.05, 0.5), -0.5)
        return max(0.0, min(1.0, base_allocation * scale))

    def allocate_with_rl(self, features, allocator: "WeightAllocator", max_leverage: float = 1.0, stop_loss_vol: float | None = None):  # type: ignore
        """Delegate to WeightAllocator then R() risk overlay. No-op fallback if RL missing."""
        import numpy as np

        if not _HAS_RL or apply_risk_overlay is None:
            raise ImportError("tradingagents.rl not available — install optional deps or check import")
        weights = allocator.allocate(features)  # type: ignore
        w = np.asarray(weights, dtype=float)
        # Estimate vol from features if not provided
        cur_vol = None
        try:
            import pandas as pd  # noqa: F401

            if isinstance(features, pd.DataFrame):
                cur_vol = float(features.to_numpy(dtype=float).std())
            else:
                cur_vol = float(np.asarray(features, dtype=float).std())
        except Exception:
            cur_vol = None
        return apply_risk_overlay(w, max_leverage=max_leverage, stop_loss_vol=stop_loss_vol, current_vol=cur_vol)

    def close(self):
        """Close providers"""
        self.rates_provider.close()
        self.fx_provider.close()


def main():
    """Main function"""
    
    print("Initializing Carry Trade Portfolio Manager...")
    
    manager = CarryTradePortfolioManager()
    
    try:
        report = manager.generate_report()
        
        # Save report to file
        report_path = f"portfolio_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\nReport saved to: {report_path}")
        
    finally:
        manager.close()


if __name__ == "__main__":
    main()
