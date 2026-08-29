"""
Prototype Chain: Geopolitical Tension Multi-Market Strategy.

This is an example of a chained investment strategy that responds
to geopolitical tension events across multiple markets.
"""

from datetime import datetime

from .models import ChainStrategy, ChainStep


def create_geopolitical_tension_chain() -> ChainStrategy:
    """
    Create a prototype chain for geopolitical tension.

    TRIGGER: WorldMonitor detects tension in Middle East
    CHAIN:
        1. Buy Oil ETF (USO) - oil rises on tension
        2. Sell Airlines ETF (JETS) - fuel costs rise
        3. Buy Argentine Bonds (AL30) - import pressure drops
        4. Buy Gold ETF (GLD) - safe haven demand
    """
    chain = ChainStrategy(
        chain_id="GEO-TENSION-001",
        name="Geopolitical Tension Response",
        description=(
            "Multi-market chain triggered by geopolitical tension in Middle East. "
            "Benefits from oil price rise, airline weakness, Argentine bond stability, "
            "and safe haven demand."
        ),
        trigger_event="WorldMonitor detects tension in Middle East",
        correlations={
            "oil_transport": -0.85,
            "oil_inflation": 0.72,
            "inflation_bonds_ar": -0.68,
            "tension_gold": 0.91,
        },
        scoring=78,
        veredicto="APPROVE",
        reasoning=(
            "Historical pattern shows oil rises 15-25% on Middle East tension, "
            "airlines drop 10-15% on fuel cost fears, Argentine bonds benefit from "
            "reduced import pressure, and gold rallies as safe haven. "
            "Correlation matrix supports multi-market approach."
        ),
        steps=[
            ChainStep(
                step_id=1,
                name="Buy Oil ETF",
                description="Long oil via USO ETF to benefit from supply disruption fears",
                market="US",
                provider="lumibot",
                symbol="USO",
                action="BUY",
                notional=10000,
                order_type="market",
                trigger_condition="oil_price > 80",
                stop_loss=75,
                take_profit=95,
                max_loss=2000,
            ),
            ChainStep(
                step_id=2,
                name="Short Airlines ETF",
                description="Short JETS to benefit from rising fuel costs",
                market="US",
                provider="lumibot",
                symbol="JETS",
                action="SELL",
                notional=5000,
                order_type="market",
                trigger_condition="oil_price > 80",
                depends_on=[1],
                stop_loss=25,
                take_profit=18,
                max_loss=1000,
            ),
            ChainStep(
                step_id=3,
                name="Buy Argentine Bonds",
                description="Long AL30 bonds as import pressure decreases",
                market="AR",
                provider="byma",
                symbol="AL30",
                action="BUY",
                notional=500000,  # ARS
                order_type="market",
                trigger_condition="oil_price > 80",
                depends_on=[1],
                stop_loss=None,
                take_profit=None,
                max_loss=50000,
            ),
            ChainStep(
                step_id=4,
                name="Buy Gold ETF",
                description="Long gold via GLD as safe haven demand rises",
                market="US",
                provider="lumibot",
                symbol="GLD",
                action="BUY",
                notional=8000,
                order_type="market",
                trigger_condition="tension_level > 0.7",
                depends_on=[1],
                stop_loss=180,
                take_profit=210,
                max_loss=1500,
            ),
        ],
        total_notional=23000,  # USD equivalent
        max_drawdown=5500,
        risk_reward_ratio=2.5,
    )

    return chain


def create_crypto_correlation_chain() -> ChainStrategy:
    """
    Create a prototype chain for crypto correlation play.

    TRIGGER: BTC breaks above key resistance
    CHAIN:
        1. Buy BTC - momentum breakout
        2. Buy ETH - correlation play
        3. Sell SOL inverse - relative weakness
    """
    chain = ChainStrategy(
        chain_id="CRYPTO-CORR-001",
        name="Crypto Correlation Play",
        description=(
            "Multi-market crypto chain triggered by BTC breakout. "
            "Benefits from BTC momentum, ETH correlation, and SOL relative weakness."
        ),
        trigger_event="BTC breaks above $70,000 resistance",
        correlations={
            "btc_eth": 0.85,
            "btc_sol": 0.72,
            "eth_sol": 0.68,
        },
        scoring=72,
        veredicto="APPROVE",
        reasoning=(
            "BTC breakout above key resistance historically leads to 10-20% rally. "
            "ETH correlates strongly with BTC (0.85). SOL shows relative weakness "
            "and may underperform in risk-on environment."
        ),
        steps=[
            ChainStep(
                step_id=1,
                name="Buy BTC",
                description="Long BTC on momentum breakout",
                market="CRYPTO",
                provider="ccxt",
                symbol="BTC/USDT",
                action="BUY",
                notional=15000,
                order_type="market",
                trigger_condition="btc_price > 70000",
                stop_loss=65000,
                take_profit=85000,
                max_loss=3000,
            ),
            ChainStep(
                step_id=2,
                name="Buy ETH",
                description="Long ETH on BTC correlation",
                market="CRYPTO",
                provider="ccxt",
                symbol="ETH/USDT",
                action="BUY",
                notional=10000,
                order_type="market",
                trigger_condition="btc_price > 70000",
                depends_on=[1],
                stop_loss=3200,
                take_profit=4200,
                max_loss=2000,
            ),
            ChainStep(
                step_id=3,
                name="Short SOL",
                description="Short SOL on relative weakness",
                market="CRYPTO",
                provider="ccxt",
                symbol="SOL/USDT",
                action="SELL",
                notional=5000,
                order_type="market",
                trigger_condition="btc_price > 70000",
                depends_on=[1],
                stop_loss=200,
                take_profit=140,
                max_loss=1000,
            ),
        ],
        total_notional=30000,
        max_drawdown=6000,
        risk_reward_ratio=3.0,
    )

    return chain
