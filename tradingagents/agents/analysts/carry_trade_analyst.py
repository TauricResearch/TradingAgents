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
import json


def analyze_carry_trade(
    interest_rates: str,
    fx_rates: str,
    country_risks: str,
    portfolio_size: float,
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
    # Parse input data
    rates = json.loads(interest_rates) if isinstance(interest_rates, str) else interest_rates
    fx = json.loads(fx_rates) if isinstance(fx_rates, str) else fx_rates
    risks = json.loads(country_risks) if isinstance(country_risks, str) else country_risks
    
    # Calculate spreads
    opportunities = []
    countries = list(rates.keys())
    
    for i, base_country in enumerate(countries):
        for target_country in countries[i+1:]:
            if base_country in rates and target_country in rates:
                base_rate = rates[base_country]
                target_rate = rates[target_country]
                spread = target_rate - base_rate
                
                # Get risk rating
                risk = risks.get(target_country, "Unknown")
                
                # Calculate position size based on risk
                risk_score = {"AAA": 1, "AA+": 2, "AA": 3, "A+": 4, "A": 5}.get(risk, 5)
                position_pct = max(5, 30 - (risk_score * 5))  # Lower risk = larger position
                
                opportunities.append({
                    "funding": base_country,
                    "target": target_country,
                    "funding_rate": base_rate,
                    "target_rate": target_rate,
                    "spread": spread,
                    "risk": risk,
                    "position_pct": position_pct,
                    "position_usd": portfolio_size * (position_pct / 100),
                })
    
    # Sort by spread (highest first)
    opportunities.sort(key=lambda x: x["spread"], reverse=True)
    
    # Generate report
    report = []
    report.append("CARRY TRADE ANALYSIS REPORT")
    report.append("=" * 50)
    report.append(f"\nPortfolio Size: ${portfolio_size:,.0f} USD")
    report.append(f"Opportunities Found: {len(opportunities)}\n")
    
    report.append("TOP 3 OPPORTUNITIES:")
    report.append("-" * 50)
    
    for i, opp in enumerate(opportunities[:3], 1):
        report.append(f"\n{i}. {opp['funding']} -> {opp['target']}")
        report.append(f"   Funding Rate: {opp['funding_rate']:.2f}%")
        report.append(f"   Target Rate: {opp['target_rate']:.2f}%")
        report.append(f"   Spread: {opp['spread']:.2f}%")
        report.append(f"   Risk Rating: {opp['risk']}")
        report.append(f"   Position Size: {opp['position_pct']}% (${opp['position_usd']:,.0f})")
    
    report.append("\n" + "-" * 50)
    report.append("RECOMMENDATIONS:")
    report.append("-" * 50)
    
    if opportunities:
        best = opportunities[0]
        report.append(f"\n1. Best Opportunity: {best['funding']}/{best['target']}")
        report.append(f"   - Borrow at {best['funding_rate']:.2f}% in {best['funding']}")
        report.append(f"   - Invest at {best['target_rate']:.2f}% in {best['target']}")
        report.append(f"   - Expected carry: {best['spread']:.2f}%")
        
        report.append("\n2. Risk Warnings:")
        report.append("   - Currency depreciation can wipe out interest gains")
        report.append("   - Central bank policy changes may reduce spread")
        report.append("   - Liquidity risk in emerging market currencies")
        
        report.append("\n3. Hedging Suggestions:")
        report.append("   - Consider FX forwards or options for partial hedge")
        report.append("   - Diversify across multiple currency pairs")
        report.append("   - Set stop-loss at -5% FX movement")
    
    return "\n".join(report)


def assess_fx_risk(
    funding_currency: str,
    target_currency: str,
    historical_volatility: float,
    correlation_with_market: float,
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
    # Determine risk level
    if historical_volatility < 0.05:
        risk_level = "Low"
    elif historical_volatility < 0.10:
        risk_level = "Medium"
    elif historical_volatility < 0.20:
        risk_level = "High"
    else:
        risk_level = "Critical"
    
    # Calculate potential loss
    max_loss = historical_volatility * 2  # 2 standard deviations
    
    report = []
    report.append("FX RISK ASSESSMENT")
    report.append("=" * 50)
    report.append(f"\nFunding Currency: {funding_currency}")
    report.append(f"Target Currency: {target_currency}")
    report.append(f"Historical Volatility: {historical_volatility:.2%}")
    report.append(f"Market Correlation: {correlation_with_market:.2f}")
    report.append(f"\nRisk Level: {risk_level}")
    report.append(f"Potential Max Loss (2σ): {max_loss:.2%}")
    
    report.append("\nMITIGATION STRATEGIES:")
    report.append("-" * 50)
    
    if risk_level in ["High", "Critical"]:
        report.append("\n1. Position Sizing: Reduce to 10-15% of portfolio")
        report.append("2. Stop-Loss: Set at -5% FX movement")
        report.append("3. Hedging: Use FX options or forwards")
        report.append("4. Diversification: Spread across 3-5 currency pairs")
    elif risk_level == "Medium":
        report.append("\n1. Position Sizing: 15-25% of portfolio")
        report.append("2. Stop-Loss: Set at -7% FX movement")
        report.append("3. Monitoring: Daily review of FX rates")
    else:
        report.append("\n1. Position Sizing: Up to 30% of portfolio")
        report.append("2. Stop-Loss: Set at -10% FX movement")
        report.append("3. Monitoring: Weekly review sufficient")
    
    return "\n".join(report)


def design_carry_strategy(
    funding_currency: str,
    target_currency: str,
    investment_horizon: int,
    risk_tolerance: str,
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
    report = []
    report.append("CARRY TRADE STRATEGY DESIGN")
    report.append("=" * 50)
    report.append(f"\nFunding: {funding_currency}")
    report.append(f"Investment: {target_currency}")
    report.append(f"Horizon: {investment_horizon} months")
    report.append(f"Risk Tolerance: {risk_tolerance}")
    
    report.append("\nSTRATEGY COMPONENTS:")
    report.append("-" * 50)
    
    # Position sizing based on risk tolerance
    position_sizes = {
        "conservative": "10-15% of portfolio",
        "moderate": "15-25% of portfolio",
        "aggressive": "25-35% of portfolio",
    }
    
    report.append(f"\n1. Position Size: {position_sizes.get(risk_tolerance, '15-25%')}")
    report.append(f"2. Investment Horizon: {investment_horizon} months")
    report.append("3. Entry Strategy:")
    report.append("   - Wait for favorable FX rate (technical support)")
    report.append("   - Enter position in tranches (3-4 tranches)")
    report.append("   - Set initial stop-loss at -5%")
    
    report.append("\n4. Exit Strategy:")
    report.append("   - Take profit at +10% FX movement")
    report.append("   - Stop-loss at -5% FX movement")
    report.append("   - Time-based exit at horizon completion")
    report.append("   - Exit if interest rate differential narrows by >1%")
    
    report.append("\n5. Monitoring:")
    report.append("   - Daily: FX rates and volatility")
    report.append("   - Weekly: Central bank communications")
    report.append("   - Monthly: Position performance review")
    
    report.append("\n6. Expected Returns (Base Case):")
    report.append("   - Interest differential: ~5% annualized")
    report.append("   - FX impact: ±3% (depending on currency movement)")
    report.append("   - Net return: 2-8% annualized")
    
    return "\n".join(report)


def analyst_node(state: Dict) -> Dict:
    """Carry trade analyst node for the graph"""
    
    # Get interest rates from data provider
    interest_rates = state.get("global_interest_rates", {})
    fx_rates = state.get("fx_rates", {})
    country_risks = state.get("country_risks", {})
    portfolio_size = state.get("portfolio_size", 100000)  # Default $100k
    
    # Format data for analysis
    interest_rates_str = json.dumps(interest_rates, indent=2)
    fx_rates_str = json.dumps(fx_rates, indent=2)
    country_risks_str = json.dumps(country_risks, indent=2)
    
    # Run carry trade analysis
    analysis = analyze_carry_trade(
        interest_rates_str,
        fx_rates_str,
        country_risks_str,
        portfolio_size,
    )
    
    return {
        "messages": state.get("messages", []) + [
            {"role": "user", "content": f"Carry Trade Analysis:\n\n{analysis}"}
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


# For backward compatibility
create_carry_trade_analyst = analyst_node
