"""
Global Carry Trade Strategies
-------------------------------
Prototypes for carry trade strategies across global markets.
"""

from datetime import datetime
from typing import Dict, List, Optional
from .models import ChainStrategy, ChainStep, StrategyType, RiskLevel, ExecutionMode


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
            name="USD_BRL_Carry",
            description="Fondeo en USD (tasa baja) e inversión en BRL (SELIC alta)",
            strategy_type=StrategyType.CARRY_TRADE,
            risk_level=RiskLevel.HIGH,
            estimated_return=f"{horizon_months * 5 / 12:.1f}%",
            estimated_duration=f"{horizon_months} months",
            tags=["carry_trade", "emerging_market", "brazil"],
            steps=[
                ChainStep(
                    step_id="funding",
                    name="USD Funding",
                    description="Fondeo en USD al 5.5% (Federal Funds Rate)",
                    action="borrow",
                    parameters={
                        "currency": "USD",
                        "rate": 5.5,
                        "amount": investment_amount,
                        "horizon_months": horizon_months,
                        "instrument": "USD money market",
                    },
                    depends_on=[],
                ),
                ChainStep(
                    step_id="fx_conversion",
                    name="USD to BRL Conversion",
                    description="Conversión de USD a BRL al tipo de cambio spot",
                    action="convert_fx",
                    parameters={
                        "from_currency": "USD",
                        "to_currency": "BRL",
                        "amount": investment_amount,
                    },
                    depends_on=["funding"],
                ),
                ChainStep(
                    step_id="investment",
                    name="BRL Investment",
                    description="Inversión en BRL al 10.5% (SELIC)",
                    action="invest",
                    parameters={
                        "currency": "BRL",
                        "rate": 10.5,
                        "amount": investment_amount,
                        "horizon_months": horizon_months,
                        "instrument": "Brazilian government bonds (Tesouro Selic)",
                    },
                    depends_on=["fx_conversion"],
                ),
                ChainStep(
                    step_id="monitoring",
                    name="Position Monitoring",
                    description="Monitoreo de posición y tipo de cambio",
                    action="monitor",
                    parameters={
                        "check_interval": "daily",
                        "stop_loss_fx": -0.05,
                        "take_profit_spread": 0.02,
                    },
                    depends_on=["investment"],
                ),
                ChainStep(
                    step_id="exit",
                    name="Exit and Repatriation",
                    description="Salida de posición y repatriación de fondos",
                    action="exit",
                    parameters={
                        "convert_back": True,
                        "settle_funding": True,
                    },
                    depends_on=["monitoring"],
                ),
            ],
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
            name="JPY_TRY_Carry",
            description="Fondeo en JPY (tasa ultra-baja) e inversión en TRY (turbo carry)",
            strategy_type=StrategyType.CARRY_TRADE,
            risk_level=RiskLevel.CRITICAL,
            estimated_return=f"{horizon_months * 49.75 / 12:.1f}%",
            estimated_duration=f"{horizon_months} months",
            tags=["carry_trade", "exotic", "turkey", "high_risk"],
            steps=[
                ChainStep(
                    step_id="funding",
                    name="JPY Funding",
                    description="Fondeo en JPY al 0.25% (Bank of Japan)",
                    action="borrow",
                    parameters={
                        "currency": "JPY",
                        "rate": 0.25,
                        "amount": investment_amount,
                        "horizon_months": horizon_months,
                        "instrument": "JPY money market",
                    },
                    depends_on=[],
                ),
                ChainStep(
                    step_id="fx_conversion",
                    name="JPY to TRY Conversion",
                    description="Conversión de JPY a TRY al tipo de cambio spot",
                    action="convert_fx",
                    parameters={
                        "from_currency": "JPY",
                        "to_currency": "TRY",
                        "amount": investment_amount,
                    },
                    depends_on=["funding"],
                ),
                ChainStep(
                    step_id="investment",
                    name="TRY Investment",
                    description="Inversión en TRY al 50% (CBRT Policy Rate)",
                    action="invest",
                    parameters={
                        "currency": "TRY",
                        "rate": 50.0,
                        "amount": investment_amount,
                        "horizon_months": horizon_months,
                        "instrument": "Turkish government bonds (Devlet Tahvili)",
                    },
                    depends_on=["fx_conversion"],
                ),
                ChainStep(
                    step_id="monitoring",
                    name="Position Monitoring",
                    description="Monitoreo intensivo de posición (alto riesgo)",
                    action="monitor",
                    parameters={
                        "check_interval": "hourly",
                        "stop_loss_fx": -0.10,
                        "take_profit_spread": 0.05,
                        "alert_threshold": "any",
                    },
                    depends_on=["investment"],
                ),
                ChainStep(
                    step_id="exit",
                    name="Exit and Repatriation",
                    description="Salida de posición y repatriación de fondos",
                    action="exit",
                    parameters={
                        "convert_back": True,
                        "settle_funding": True,
                        "urgency": "high",
                    },
                    depends_on=["monitoring"],
                ),
            ],
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
            name="EUR_INR_Carry",
            description="Fondeo en EUR e inversión en INR (carry moderado)",
            strategy_type=StrategyType.CARRY_TRADE,
            risk_level=RiskLevel.MEDIUM,
            estimated_return=f"{horizon_months * 2 / 12:.1f}%",
            estimated_duration=f"{horizon_months} months",
            tags=["carry_trade", "emerging_market", "india"],
            steps=[
                ChainStep(
                    step_id="funding",
                    name="EUR Funding",
                    description="Fondeo en EUR al 4.5% (ECB)",
                    action="borrow",
                    parameters={
                        "currency": "EUR",
                        "rate": 4.5,
                        "amount": investment_amount,
                        "horizon_months": horizon_months,
                        "instrument": "EUR money market",
                    },
                    depends_on=[],
                ),
                ChainStep(
                    step_id="fx_conversion",
                    name="EUR to INR Conversion",
                    description="Conversión de EUR a INR al tipo de cambio spot",
                    action="convert_fx",
                    parameters={
                        "from_currency": "EUR",
                        "to_currency": "INR",
                        "amount": investment_amount,
                    },
                    depends_on=["funding"],
                ),
                ChainStep(
                    step_id="investment",
                    name="INR Investment",
                    description="Inversión en INR al 6.5% (RBI Repo Rate)",
                    action="invest",
                    parameters={
                        "currency": "INR",
                        "rate": 6.5,
                        "amount": investment_amount,
                        "horizon_months": horizon_months,
                        "instrument": "Indian government bonds (G-Sec)",
                    },
                    depends_on=["fx_conversion"],
                ),
                ChainStep(
                    step_id="exit",
                    name="Exit and Repatriation",
                    description="Salida de posición y repatriación de fondos",
                    action="exit",
                    parameters={
                        "convert_back": True,
                        "settle_funding": True,
                    },
                    depends_on=["investment"],
                ),
            ],
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
            name="Multi_Currency_Carry_Basket",
            description="Canasta diversificada de carry trades en múltiples monedas",
            strategy_type=StrategyType.CARRY_TRADE,
            risk_level=RiskLevel.MEDIUM,
            estimated_return=f"{horizon_months * 3.5 / 12:.1f}%",
            estimated_duration=f"{horizon_months} months",
            tags=["carry_trade", "diversified", "portfolio"],
            steps=[
                ChainStep(
                    step_id="allocation",
                    name="Portfolio Allocation",
                    description="Distribución del capital entre monedas objetivo",
                    action="allocate",
                    parameters={
                        "allocations": {
                            "BRL": 0.30,  # 30% - Brasil
                            "MXN": 0.25,  # 25% - México
                            "INR": 0.20,  # 20% - India
                            "ZAR": 0.15,  # 15% - Sudáfrica
                            "CLP": 0.10,  # 10% - Chile
                        },
                        "funding_currency": "USD",
                        "total_amount": investment_amount,
                    },
                    depends_on=[],
                ),
                ChainStep(
                    step_id="execution",
                    name="Multi-Currency Execution",
                    description="Ejecución simultánea en múltiples monedas",
                    action="execute",
                    parameters={
                        "execution_type": "parallel",
                        "slippage_tolerance": 0.001,
                    },
                    depends_on=["allocation"],
                ),
                ChainStep(
                    step_id="rebalancing",
                    name="Dynamic Rebalancing",
                    description="Rebalanceo dinámico según condiciones de mercado",
                    action="rebalance",
                    parameters={
                        "frequency": "weekly",
                        "trigger": "volatility_spike",
                        "rebalance_threshold": 0.05,
                    },
                    depends_on=["execution"],
                ),
                ChainStep(
                    step_id="exit",
                    name="Staggered Exit",
                    description="Salida escalonada para minimizar impacto de mercado",
                    action="exit",
                    parameters={
                        "exit_type": "staggered",
                        "exit_window_days": 5,
                    },
                    depends_on=["rebalancing"],
                ),
            ],
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
    def get_strategy_by_risk(risk_level: RiskLevel) -> List[ChainStrategy]:
        """Get strategies filtered by risk level"""
        return [
            s for s in GlobalCarryStrategies.get_all_strategies()
            if s.risk_level == risk_level
        ]
