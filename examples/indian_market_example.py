#!/usr/bin/env python3
"""
Indian Market Analysis Example
Comprehensive example demonstrating Indian stock market analysis capabilities
"""

import os
import sys
from datetime import datetime, timedelta
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    """Main example function demonstrating Indian market analysis"""
    
    print("🇮🇳 TradingAgents - Indian Market Analysis Example")
    print("=" * 60)
    
    try:
        # Import Indian market modules
        from tradingagents.agents.utils.indian_agent_toolkit import indian_toolkit
        from tradingagents.indian_config import get_major_stocks, get_market_status
        from tradingagents.dataflows.ticker_utils import format_indian_ticker
        
        print("✅ Successfully imported Indian market modules")
        
    except ImportError as e:
        print(f"❌ Failed to import modules: {e}")
        print("Please ensure all dependencies are installed:")
        print("pip install -r requirements.txt")
        return
    
    # Example 1: Market Status Check
    print("\n" + "="*60)
    print("📊 EXAMPLE 1: Market Status Check")
    print("="*60)
    
    try:
        market_status = indian_toolkit.check_market_status()
        print(f"Market Status: {market_status['market_status']}")
        print(f"Is Open: {market_status['is_market_open']}")
        print(f"Current Time: {market_status['current_time']}")
        print(f"Trading Hours: {market_status['trading_hours']['open']} - {market_status['trading_hours']['close']} IST")
    except Exception as e:
        print(f"Error checking market status: {e}")
    
    # Example 2: Stock Analysis
    print("\n" + "="*60)
    print("📈 EXAMPLE 2: Individual Stock Analysis")
    print("="*60)
    
    # Analyze Reliance Industries
    symbol = "RELIANCE"
    exchange = "NSE"
    
    print(f"Analyzing {symbol} on {exchange}...")
    
    try:
        # Get current quote
        print(f"\n💹 Current Quote for {symbol}:")
        quote = indian_toolkit.get_indian_stock_quote(symbol, exchange)
        print(quote[:500] + "..." if len(quote) > 500 else quote)
        
        # Get fundamental analysis
        print(f"\n🏢 Fundamental Analysis for {symbol}:")
        fundamentals = indian_toolkit.analyze_fundamentals(symbol, exchange)
        if 'analysis' in fundamentals:
            analysis_text = fundamentals['analysis']
            print(analysis_text[:800] + "..." if len(analysis_text) > 800 else analysis_text)
        
        print(f"\n📊 Analysis Summary:")
        print(f"- Confidence: {fundamentals.get('confidence', 0):.1%}")
        print(f"- Risk Factors: {len(fundamentals.get('risk_factors', []))}")
        print(f"- Opportunities: {len(fundamentals.get('opportunities', []))}")
        
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
    
    # Example 3: Technical Analysis
    print("\n" + "="*60)
    print("📈 EXAMPLE 3: Technical Analysis")
    print("="*60)
    
    try:
        # Perform technical analysis
        technical = indian_toolkit.analyze_technical(symbol, exchange, lookback_days=30)
        
        print(f"Technical Analysis for {symbol}:")
        if 'technical_analysis' in technical:
            tech_text = technical['technical_analysis']
            print(tech_text[:600] + "..." if len(tech_text) > 600 else tech_text)
        
        print(f"\n📊 Technical Summary:")
        print(f"- Confidence: {technical.get('confidence', 0):.1%}")
        if 'trading_signals' in technical:
            signals = technical['trading_signals']
            print(f"- Trading Signals: {len(signals)}")
            for i, signal in enumerate(signals[:2], 1):
                if 'signal_type' in signal:
                    print(f"  {i}. {signal.get('signal_type', 'N/A')} - Confidence: {signal.get('confidence', 'N/A')}")
        
    except Exception as e:
        print(f"Error in technical analysis: {e}")
    
    # Example 4: Sector Analysis
    print("\n" + "="*60)
    print("🏭 EXAMPLE 4: Sector Analysis")
    print("="*60)
    
    try:
        # Analyze Banking sector
        sector = "banking"
        print(f"Analyzing {sector.title()} sector...")
        
        sector_analysis = indian_toolkit.get_sector_analysis(sector)
        print(sector_analysis[:600] + "..." if len(sector_analysis) > 600 else sector_analysis)
        
        # Get sector stocks
        sector_stocks = indian_toolkit.get_sector_stocks(sector)
        print(f"\n📈 Top stocks in {sector.title()} sector:")
        for i, stock in enumerate(sector_stocks[:5], 1):
            print(f"  {i}. {stock}")
        
    except Exception as e:
        print(f"Error in sector analysis: {e}")
    
    # Example 5: Portfolio Position Sizing
    print("\n" + "="*60)
    print("💰 EXAMPLE 5: Position Sizing Calculation")
    print("="*60)
    
    try:
        # Calculate position size for a trade
        entry_price = 2500.0  # INR
        stop_loss = 2400.0    # INR
        portfolio_value = 1000000.0  # 10 Lakh INR
        risk_percentage = 0.02  # 2%
        
        position_calc = indian_toolkit.calculate_position_size(
            symbol, entry_price, stop_loss, portfolio_value, risk_percentage
        )
        
        print(f"Position Sizing for {symbol}:")
        print(f"- Entry Price: ₹{entry_price:,.2f}")
        print(f"- Stop Loss: ₹{stop_loss:,.2f}")
        print(f"- Portfolio Value: ₹{portfolio_value:,.2f}")
        print(f"- Risk Tolerance: {risk_percentage*100}%")
        print(f"\n📊 Recommendation:")
        print(f"- Shares to Buy: {position_calc.get('recommended_shares', 0):,}")
        print(f"- Position Value: ₹{position_calc.get('position_value', 0):,.2f}")
        print(f"- Risk Amount: ₹{position_calc.get('risk_amount', 0):,.2f}")
        print(f"- Risk %: {position_calc.get('risk_percentage', 0):.2f}%")
        
    except Exception as e:
        print(f"Error in position sizing: {e}")
    
    # Example 6: Market Overview
    print("\n" + "="*60)
    print("🌍 EXAMPLE 6: Market Overview")
    print("="*60)
    
    try:
        # Get market overview
        market_overview = indian_toolkit.get_market_overview()
        print("Indian Market Overview:")
        print(market_overview[:800] + "..." if len(market_overview) > 800 else market_overview)
        
        # Get market conditions
        market_conditions = indian_toolkit.analyze_market_conditions()
        print(f"\n📊 Market Conditions Summary:")
        print(f"- Trading Bias: {market_conditions.get('trading_bias', 'N/A')}")
        print(f"- Confidence: {market_conditions.get('confidence', 0):.1%}")
        print(f"- Market Status: {market_conditions.get('market_status', 'N/A')}")
        
    except Exception as e:
        print(f"Error in market overview: {e}")
    
    # Example 7: Ticker Utilities
    print("\n" + "="*60)
    print("🔧 EXAMPLE 7: Ticker Utilities")
    print("="*60)
    
    try:
        # Demonstrate ticker formatting and validation
        test_symbols = ["reliance", "TCS", "HDFC Bank", "infy"]
        
        print("Ticker Processing Examples:")
        for symbol in test_symbols:
            try:
                formatted_nse = format_indian_ticker(symbol, "NSE")
                formatted_bse = format_indian_ticker(symbol, "BSE")
                is_valid = indian_toolkit.validate_ticker(formatted_nse)
                
                print(f"- {symbol:10} → NSE: {formatted_nse:12} | BSE: {formatted_bse:12} | Valid: {is_valid}")
            except Exception as e:
                print(f"- {symbol:10} → Error: {e}")
        
        # Show major stocks
        major_stocks = indian_toolkit.get_major_stocks_list()
        print(f"\n📊 Major Indian Stocks (showing first 5):")
        for i, (symbol, info) in enumerate(list(major_stocks.items())[:5], 1):
            print(f"  {i}. {symbol:10} - {info['name'][:30]:30} ({info['sector']})")
        
    except Exception as e:
        print(f"Error in ticker utilities: {e}")
    
    # Example 8: Risk Assessment
    print("\n" + "="*60)
    print("⚠️ EXAMPLE 8: Risk Assessment")
    print("="*60)
    
    try:
        # Assess risk for the stock
        risk_assessment = indian_toolkit.assess_stock_risk(symbol, exchange)
        
        print(f"Risk Assessment for {symbol}:")
        print(f"- Overall Risk Score: {risk_assessment.get('overall_risk_score', 0):.1f}/10")
        print(f"- Risk Recommendation: {risk_assessment.get('recommendation', 'N/A')}")
        
        risk_factors = risk_assessment.get('risk_factors', [])
        if risk_factors:
            print(f"\n⚠️ Key Risk Factors:")
            for i, risk in enumerate(risk_factors[:3], 1):
                print(f"  {i}. {risk}")
        
    except Exception as e:
        print(f"Error in risk assessment: {e}")
    
    # Example 9: Portfolio Analysis (Mock Data)
    print("\n" + "="*60)
    print("📊 EXAMPLE 9: Portfolio Analysis (Mock Data)")
    print("="*60)
    
    try:
        # Create mock portfolio data
        mock_portfolio = [
            {"symbol": "RELIANCE", "quantity": 100, "avg_price": 2400.0},
            {"symbol": "TCS", "quantity": 50, "avg_price": 3500.0},
            {"symbol": "HDFCBANK", "quantity": 75, "avg_price": 1600.0},
            {"symbol": "INFY", "quantity": 80, "avg_price": 1400.0}
        ]
        
        portfolio_metrics = indian_toolkit.calculate_portfolio_metrics(mock_portfolio)
        
        print("Portfolio Analysis (Mock Data):")
        print(f"- Total Investment: ₹{portfolio_metrics.get('total_investment', 0):,.2f}")
        print(f"- Current Value: ₹{portfolio_metrics.get('total_current_value', 0):,.2f}")
        print(f"- Total P&L: ₹{portfolio_metrics.get('total_pnl', 0):,.2f}")
        print(f"- Total P&L %: {portfolio_metrics.get('total_pnl_percentage', 0):.2f}%")
        
        print(f"\n📈 Individual Holdings:")
        for holding in portfolio_metrics.get('holdings', [])[:3]:
            pnl_emoji = "🟢" if holding.get('pnl', 0) >= 0 else "🔴"
            print(f"  {pnl_emoji} {holding.get('symbol', 'N/A'):10} | "
                  f"P&L: ₹{holding.get('pnl', 0):8.2f} ({holding.get('pnl_percentage', 0):6.2f}%)")
        
    except Exception as e:
        print(f"Error in portfolio analysis: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("✅ EXAMPLE COMPLETED")
    print("="*60)
    print("This example demonstrated:")
    print("1. ✅ Market status checking")
    print("2. ✅ Individual stock analysis (fundamental & technical)")
    print("3. ✅ Sector analysis")
    print("4. ✅ Position sizing calculations")
    print("5. ✅ Market overview and conditions")
    print("6. ✅ Ticker utilities and validation")
    print("7. ✅ Risk assessment")
    print("8. ✅ Portfolio analysis")
    print("\n💡 Next Steps:")
    print("- Set up API keys for live data (Alpha Vantage, etc.)")
    print("- Try the CLI: python cli/indian_cli.py --help")
    print("- Run tests: python -m pytest tests/test_indian_market.py")
    print("- Explore the graph-based trading system integration")

if __name__ == "__main__":
    main() 