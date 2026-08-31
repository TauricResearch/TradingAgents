"""
Global Carry Trade Strategies
-------------------------------
Prototypes for carry trade strategies across global markets.
"""

from datetime import datetime
from typing import Dict, List, Optional
from .models import ChainStrategy, ChainStep, ChainStepStatus


class GlobalCarryStrategies:
    """Collection of global carry trade strategy prototypes"""
    
    @staticmethod
    def usd_brl_carry(
        investment_amount: float = 100000,
        horizon_months: int = 6,
    ) -> ChainStrategy:
        """
        USD/BRL Carry Trade
        - Fund in USD at ~5.5% (Fed Funds)
        - Invest in BRL at ~10.5% (SELIC)
        - Spread: ~5% annualized
        """
        return ChainStrategy(
            chain_id="usd_brl_carry_001",
            name="USD_BRL_Carry",
            description="Fondeo en USD (tasa baja) e inversión en BRL (SELIC alta)",
            steps=[
                ChainStep(
                    step_id=1,
                    name="USD Funding",
                    description="Fondeo en USD al 5.5% (Federal Funds Rate)",
                    market="US",
                    provider="lumibot",
                    symbol="USD",
                    action="BORROW",
                    notional=investment_amount,
                    depends_on=[],
                ),
                ChainStep(
                    step_id=2,
                    name="USD to BRL Conversion",
                    description="Conversión de USD a BRL al tipo de cambio spot",
                    market="FOREX",
                    provider="lumibot",
                    symbol="USDBRL",
                    action="CONVERT",
                    notional=investment_amount,
                    depends_on=[1],
                ),
                ChainStep(
                    step_id=3,
                    name="BRL Investment",
                    description="Inversión en BRL al 10.5% (SELIC)",
                    market="BR",
                    provider="lumibot",
                    symbol="BRL",
                    action="INVEST",
                    notional=investment_amount,
                    depends_on=[2],
                ),
                ChainStep(
                    step_id=4,
                    name="Position Monitoring",
                    description="Monitoreo de posición y tipo de cambio",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="USDBRL",
                    action="MONITOR",
                    depends_on=[3],
                ),
                ChainStep(
                    step_id=5,
                    name="Exit and Repatriation",
                    description="Salida de posición y repatriación de fondos",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="USD",
                    action="EXIT",
                    depends_on=[4],
                ),
            ],
            trigger_event="carry_trade_opportunity",
            correlations={"usd_brl": -0.3},
            total_notional=investment_amount,
            max_drawdown=investment_amount * 0.05,
            risk_reward_ratio=2.0,
            scoring=75,
            veredicto="APPROVE",
            reasoning="High interest rate differential (5%) with manageable FX risk",
        )
    
    @staticmethod
    def jpy_try_carry(
        investment_amount: float = 100000,
        horizon_months: int = 6,
    ) -> ChainStrategy:
        """
        JPY/TRY Carry Trade
        - Fund in JPY at ~0.25% (BOJ)
        - Invest in TRY at ~50% (CBRT)
        - Spread: ~49.75% annualized (VERY HIGH RISK)
        """
        return ChainStrategy(
            chain_id="jpy_try_carry_001",
            name="JPY_TRY_Carry",
            description="Fondeo en JPY (tasa ultra-baja) e inversión en TRY (turbo carry)",
            steps=[
                ChainStep(
                    step_id=1,
                    name="JPY Funding",
                    description="Fondeo en JPY al 0.25% (Bank of Japan)",
                    market="JP",
                    provider="lumibot",
                    symbol="JPY",
                    action="BORROW",
                    notional=investment_amount,
                    depends_on=[],
                ),
                ChainStep(
                    step_id=2,
                    name="JPY to TRY Conversion",
                    description="Conversión de JPY a TRY al tipo de cambio spot",
                    market="FOREX",
                    provider="lumibot",
                    symbol="JPYTRY",
                    action="CONVERT",
                    notional=investment_amount,
                    depends_on=[1],
                ),
                ChainStep(
                    step_id=3,
                    name="TRY Investment",
                    description="Inversión en TRY al 50% (CBRT Policy Rate)",
                    market="TR",
                    provider="lumibot",
                    symbol="TRY",
                    action="INVEST",
                    notional=investment_amount,
                    depends_on=[2],
                ),
                ChainStep(
                    step_id=4,
                    name="Position Monitoring",
                    description="Monitoreo intensivo de posición (alto riesgo)",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="JPYTRY",
                    action="MONITOR",
                    depends_on=[3],
                ),
                ChainStep(
                    step_id=5,
                    name="Exit and Repatriation",
                    description="Salida de posición y repatriación de fondos",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="JPY",
                    action="EXIT",
                    depends_on=[4],
                ),
            ],
            trigger_event="carry_trade_opportunity",
            correlations={"jpy_try": -0.7},
            total_notional=investment_amount,
            max_drawdown=investment_amount * 0.20,
            risk_reward_ratio=1.5,
            scoring=45,
            veredicto="ADJUST",
            reasoning="Extremely high spread but very high FX risk. Reduce position size to 10%.",
        )
    
    @staticmethod
    def eur_inr_carry(
        investment_amount: float = 100000,
        horizon_months: int = 6,
    ) -> ChainStrategy:
        """
        EUR/INR Carry Trade
        - Fund in EUR at ~4.5% (ECB)
        - Invest in INR at ~6.5% (RBI)
        - Spread: ~2% annualized (moderate risk)
        """
        return ChainStrategy(
            chain_id="eur_inr_carry_001",
            name="EUR_INR_Carry",
            description="Fondeo en EUR e inversión en INR (carry moderado)",
            steps=[
                ChainStep(
                    step_id=1,
                    name="EUR Funding",
                    description="Fondeo en EUR al 4.5% (ECB)",
                    market="EU",
                    provider="lumibot",
                    symbol="EUR",
                    action="BORROW",
                    notional=investment_amount,
                    depends_on=[],
                ),
                ChainStep(
                    step_id=2,
                    name="EUR to INR Conversion",
                    description="Conversión de EUR a INR al tipo de cambio spot",
                    market="FOREX",
                    provider="lumibot",
                    symbol="EURINR",
                    action="CONVERT",
                    notional=investment_amount,
                    depends_on=[1],
                ),
                ChainStep(
                    step_id=3,
                    name="INR Investment",
                    description="Inversión en INR al 6.5% (RBI Repo Rate)",
                    market="IN",
                    provider="lumibot",
                    symbol="INR",
                    action="INVEST",
                    notional=investment_amount,
                    depends_on=[2],
                ),
                ChainStep(
                    step_id=4,
                    name="Exit and Repatriation",
                    description="Salida de posición y repatriación de fondos",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="EUR",
                    action="EXIT",
                    depends_on=[3],
                ),
            ],
            trigger_event="carry_trade_opportunity",
            correlations={"eur_inr": -0.2},
            total_notional=investment_amount,
            max_drawdown=investment_amount * 0.03,
            risk_reward_ratio=3.0,
            scoring=80,
            veredicto="APPROVE",
            reasoning="Moderate spread with low FX risk. Good risk-adjusted return.",
        )
    
    @staticmethod
    def multi_currency_carry_basket(
        investment_amount: float = 100000,
        horizon_months: int = 6,
    ) -> ChainStrategy:
        """
        Multi-Currency Carry Basket
        - Diversified carry across multiple currencies
        - Reduces single-currency risk
        """
        return ChainStrategy(
            chain_id="multi_carry_basket_001",
            name="Multi_Currency_Carry_Basket",
            description="Canasta diversificada de carry trades en múltiples monedas",
            steps=[
                ChainStep(
                    step_id=1,
                    name="Portfolio Allocation",
                    description="Distribución del capital entre monedas objetivo",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="USD",
                    action="ALLOCATE",
                    notional=investment_amount,
                    depends_on=[],
                ),
                ChainStep(
                    step_id=2,
                    name="Multi-Currency Execution",
                    description="Ejecución simultánea en múltiples monedas",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="MULTI",
                    action="EXECUTE",
                    notional=investment_amount,
                    depends_on=[1],
                ),
                ChainStep(
                    step_id=3,
                    name="Dynamic Rebalancing",
                    description="Rebalanceo dinámico según condiciones de mercado",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="MULTI",
                    action="REBALANCE",
                    depends_on=[2],
                ),
                ChainStep(
                    step_id=4,
                    name="Staggered Exit",
                    description="Salida escalonada para minimizar impacto de mercado",
                    market="GLOBAL",
                    provider="lumibot",
                    symbol="USD",
                    action="EXIT",
                    depends_on=[3],
                ),
            ],
            trigger_event="carry_trade_opportunity",
            correlations={
                "brl_usd": -0.3,
                "mxn_usd": -0.25,
                "inr_usd": -0.2,
                "zar_usd": -0.35,
                "clp_usd": -0.2,
            },
            total_notional=investment_amount,
            max_drawdown=investment_amount * 0.08,
            risk_reward_ratio=2.5,
            scoring=70,
            veredicto="APPROVE",
            reasoning="Diversified carry basket reduces single-currency risk",
        )
    
    @staticmethod
    def get_all_strategies() -> List[ChainStrategy]:
        """Get all available carry trade strategies"""
        return [
            GlobalCarryStrategies.usd_brl_carry(),
            GlobalCarryStrategies.jpy_try_carry(),
            GlobalCarryStrategies.eur_inr_carry(),
            GlobalCarryStrategies.multi_currency_carry_basket(),
        ]
    
    @staticmethod
    def get_strategy_by_name(name: str) -> Optional[ChainStrategy]:
        """Get strategy by name"""
        for strategy in GlobalCarryStrategies.get_all_strategies():
            if strategy.name == name:
                return strategy
        return None
