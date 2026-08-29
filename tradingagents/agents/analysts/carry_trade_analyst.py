"""
Global Carry Trade Analyst Agent
---------------------------------
Analyzes interest rate differentials across countries to identify
carry trade opportunities: borrow in low-rate currencies, invest in
high-rate currencies, profit from the spread.

Considers:
- Interest rate differentials
- FX volatility and correlation
- Country risk (sovereign credit ratings)
- Liquidity constraints
- Central bank policy direction
- Historical carry trade performance
"""

from typing import Annotated, Dict, List, Optional, Tuple
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.llm import create_llm


SYSTEM_PROMPT = """You are a Global Carry Trade Analyst specializing in interest rate arbitrage across international markets.

Your expertise:
1. **Interest Rate Analysis**: Compare central bank policy rates across countries
2. **FX Risk Assessment**: Evaluate currency volatility and correlation
3. **Carry Trade Structuring**: Design optimal funding and investment strategies
4. **Risk Management**: Identify and mitigate carry trade risks

When analyzing carry trade opportunities:
1. Compare interest rates across at least 5 major economies
2. Calculate the interest rate differential (spread)
3. Assess FX volatility and potential for currency depreciation
4. Consider central bank policy direction (hiking/cutting/stable)
5. Evaluate country risk and liquidity
6. Calculate expected carry return after FX risk
7. Recommend position sizing and risk limits

Key metrics to report:
- Interest Rate Differential (IRD): Target rate - Funding rate
- FX Volatility: Annualized standard deviation of daily returns
- Sharpe Ratio: Risk-adjusted return
- Maximum Drawdown: Historical worst-case scenario
- Correlation: How correlated are the currencies?

Carry trade returns formula:
Carry Return = (Interest Differential) + (FX Appreciation/Depreciation)

Risk factors:
- Currency depreciation can wipe out interest gains
- Central bank policy changes (rate cuts reduce carry)
- Liquidity crises (can't exit positions)
- Political instability (capital controls)

Always recommend:
- Optimal funding currency (lowest effective rate)
- Optimal target currency (highest risk-adjusted rate)
- Position size (percentage of portfolio)
- Stop-loss levels
- Hedging strategy if needed"""


def create_carry_trade_analyst(
    model_name: str = None,
    provider: str = None,
):
    """Create a carry trade analyst agent"""
    
    model_name = model_name or DEFAULT_CONFIG.get("model_name", "gpt-4o-mini")
    provider = provider or DEFAULT_CONFIG.get("provider", "openai")
    
    llm = create_llm(model_name=model_name, provider=provider)
    
    @tool
    def analyze_carry_trade(
        interest_rates: Annotated[str, "JSON with interest rates by country"],
        fx_rates: Annotated[str, "JSON with FX rates"],
        country_risks: Annotated[str, "JSON with country risk ratings"],
        portfolio_size: Annotated[float, "Portfolio size in USD"],
    ) -> str:
        """
        Analyze carry trade opportunities across global markets.
        
        Args:
            interest_rates: JSON string with format: {"US": 5.5, "EU": 4.5, "JP": 0.25, ...}
            fx_rates: JSON string with format: {"USD_EUR": 0.85, "USD_JPY": 145.0, ...}
            country_risks: JSON string with format: {"US": "AAA", "EU": "AA+", ...}
            portfolio_size: Total portfolio size in USD for position sizing
        
        Returns:
            Carry trade analysis with recommendations
        """
        prompt = f"""
        Analyze carry trade opportunities with the following data:
        
        Interest Rates (annual %):
        {interest_rates}
        
        FX Rates:
        {fx_rates}
        
        Country Risk Ratings:
        {country_risks}
        
        Portfolio Size: ${portfolio_size:,.0f} USD
        
        Provide:
        1. Top 3 carry trade opportunities ranked by risk-adjusted return
        2. For each opportunity:
           - Funding currency and rate
           - Target currency and rate
           - Interest rate differential
           - FX volatility assessment
           - Expected carry return
           - Risk score (1-10)
           - Recommended position size
        3. Overall portfolio recommendation
        4. Risk warnings and hedging suggestions
        """
        
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        
        response = llm.invoke(messages)
        return response.content
    
    @tool
    def assess_fx_risk(
        funding_currency: Annotated[str, "Currency to borrow in"],
        target_currency: Annotated[str, "Currency to invest in"],
        historical_volatility: Annotated[float, "Annualized FX volatility"],
        correlation_with_market: Annotated[float, "Correlation with global markets"],
    ) -> str:
        """
        Assess FX risk for a carry trade position.
        
        Args:
            funding_currency: Currency code (e.g., "USD", "JPY")
            target_currency: Currency code (e.g., "BRL", "MXN")
            historical_volatility: Annualized volatility of the FX pair
            correlation_with_market: Correlation with global equity market
        
        Returns:
            FX risk assessment with mitigation strategies
        """
        prompt = f"""
        Assess FX risk for carry trade:
        
        Funding Currency: {funding_currency}
        Target Currency: {target_currency}
        Historical Volatility: {historical_volatility:.2%}
        Market Correlation: {correlation_with_market:.2f}
        
        Provide:
        1. Risk level (Low/Medium/High/Critical)
        2. Probability of FX depreciation exceeding interest gain
        3. Maximum expected loss (worst case)
        4. Recommended stop-loss level
        5. Hedging strategy options:
           - Natural hedge (revenue in target currency)
           - Options hedge (put options on target currency)
           - Cross-currency swap
        6. Position sizing recommendation based on risk
        """
        
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        
        response = llm.invoke(messages)
        return response.content
    
    @tool
    def design_carry_strategy(
        funding_currency: Annotated[str, "Currency to fund in"],
        target_currency: Annotated[str, "Currency to invest in"],
        investment_horizon: Annotated[int, "Investment horizon in months"],
        risk_tolerance: Annotated[str, "Risk tolerance: conservative, moderate, aggressive"],
    ) -> str:
        """
        Design a complete carry trade strategy.
        
        Args:
            funding_currency: Currency to borrow in
            target_currency: Currency to invest in
            investment_horizon: How long to hold the position (months)
            risk_tolerance: Risk tolerance level
        
        Returns:
            Detailed carry trade strategy
        """
        prompt = f"""
        Design a carry trade strategy:
        
        Funding Currency: {funding_currency}
        Target Currency: {target_currency}
        Investment Horizon: {investment_horizon} months
        Risk Tolerance: {risk_tolerance}
        
        Provide:
        1. Strategy overview
        2. Entry criteria and timing
        3. Position sizing methodology
        4. Funding structure (leverage, margin requirements)
        5. Investment vehicle selection:
           - Money market funds
           - Government bonds
           - Bank deposits
           - ETFs
        6. Exit strategy:
           - Profit target
           - Stop-loss level
           - Time-based exit
        7. Hedging approach
        8. Monitoring and rebalancing plan
        9. Tax considerations
        10. Expected return range (base case, bull case, bear case)
        """
        
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        
        response = llm.invoke(messages)
        return response.content
    
    def analyst_node(state: AgentState) -> Dict:
        """Carry trade analyst node for the graph"""
        
        # Get interest rates from data provider
        interest_rates = state.get("global_interest_rates", {})
        fx_rates = state.get("fx_rates", {})
        country_risks = state.get("country_risks", {})
        portfolio_size = state.get("portfolio_size", 100000)  # Default $100k
        
        # Format data for analysis
        import json
        
        interest_rates_str = json.dumps(interest_rates, indent=2)
        fx_rates_str = json.dumps(fx_rates, indent=2)
        country_risks_str = json.dumps(country_risks, indent=2)
        
        # Run carry trade analysis
        analysis = analyze_carry_trade.invoke({
            "interest_rates": interest_rates_str,
            "fx_rates": fx_rates_str,
            "country_risks": country_risks_str,
            "portfolio_size": portfolio_size,
        })
        
        return {
            "messages": state.get("messages", []) + [
                HumanMessage(content=f"Carry Trade Analysis:\n\n{analysis}")
            ],
            "carry_trade_report": {
                "analysis": analysis,
                "interest_rates": interest_rates,
                "fx_rates": fx_rates,
                "country_risks": country_risks,
                "portfolio_size": portfolio_size,
                "timestamp": state.get("current_date", ""),
            },
        }
    
    return {
        "tools": [analyze_carry_trade, assess_fx_risk, design_carry_strategy],
        "node": analyst_node,
        "name": "carry_trade_analyst",
    }
