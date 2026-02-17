"""
Indian Market CLI Interface
Command-line interface for Indian stock market analysis and trading
"""

import click
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from tradingagents.agents.utils.indian_agent_toolkit import indian_toolkit
    from tradingagents.indian_config import get_major_stocks, get_sector_stocks, INDIAN_SECTORS
    from tradingagents.dataflows.ticker_utils import format_indian_ticker, validate_indian_ticker
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)

@click.group()
@click.version_option(version='1.0.0')
def indian_cli():
    """Indian Stock Market Analysis CLI
    
    A comprehensive command-line interface for analyzing Indian stocks,
    market conditions, and generating trading insights.
    """
    pass

@indian_cli.group()
def market():
    """Market analysis commands"""
    pass

@indian_cli.group()
def stock():
    """Individual stock analysis commands"""
    pass

@indian_cli.group()
def portfolio():
    """Portfolio management commands"""
    pass

@indian_cli.group()
def sector():
    """Sector analysis commands"""
    pass

@indian_cli.group()
def utils():
    """Utility commands"""
    pass

# Market Commands
@market.command()
@click.option('--date', default=None, help='Analysis date (YYYY-MM-DD), defaults to today')
@click.option('--output', type=click.Choice(['json', 'text']), default='text', help='Output format')
def overview(date, output):
    """Get Indian market overview"""
    try:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        click.echo(f"📊 Getting Indian market overview for {date}...")
        
        # Get market overview
        market_overview = indian_toolkit.get_market_overview(date)
        
        # Get market conditions analysis
        market_conditions = indian_toolkit.analyze_market_conditions()
        
        if output == 'json':
            result = {
                "date": date,
                "market_overview": market_overview,
                "market_conditions": market_conditions
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("\n" + "="*80)
            click.echo(f"🇮🇳 INDIAN MARKET OVERVIEW - {date}")
            click.echo("="*80)
            click.echo(market_overview)
            click.echo("\n" + "="*80)
            click.echo("📈 MARKET CONDITIONS ANALYSIS")
            click.echo("="*80)
            click.echo(market_conditions.get('market_conditions', 'Analysis not available'))
            
            # Display key metrics
            if 'trading_bias' in market_conditions:
                click.echo(f"\n🎯 Trading Bias: {market_conditions['trading_bias']}")
            if 'confidence' in market_conditions:
                click.echo(f"📊 Confidence Level: {market_conditions['confidence']:.1%}")
            
    except Exception as e:
        click.echo(f"❌ Error getting market overview: {e}", err=True)
        sys.exit(1)

@market.command()
@click.option('--output', type=click.Choice(['json', 'text']), default='text', help='Output format')
def status():
    """Check current market status"""
    try:
        status_info = indian_toolkit.check_market_status()
        
        if output == 'json':
            click.echo(json.dumps(status_info, indent=2))
        else:
            click.echo("\n" + "="*50)
            click.echo("🇮🇳 INDIAN MARKET STATUS")
            click.echo("="*50)
            
            market_status = status_info['market_status']
            is_open = status_info['is_market_open']
            
            status_emoji = "🟢" if is_open else "🔴"
            click.echo(f"{status_emoji} Market Status: {market_status.upper()}")
            click.echo(f"⏰ Current Time: {status_info['current_time']}")
            
            trading_hours = status_info['trading_hours']
            click.echo(f"🕘 Trading Hours: {trading_hours['open']} - {trading_hours['close']} IST")
            
            if not is_open:
                if market_status == 'pre_market':
                    click.echo("💡 Market opens in a few minutes. Prepare your watchlist!")
                elif market_status == 'closed':
                    click.echo("💡 Market is closed. Good time for analysis and planning!")
                elif market_status == 'closed_weekend':
                    click.echo("💡 Weekend - Markets closed. Time for research!")
            
    except Exception as e:
        click.echo(f"❌ Error checking market status: {e}", err=True)
        sys.exit(1)

# Stock Commands
@stock.command()
@click.argument('symbol')
@click.option('--exchange', default='NSE', type=click.Choice(['NSE', 'BSE']), help='Exchange')
@click.option('--days', default=30, help='Number of days of data')
@click.option('--output', type=click.Choice(['json', 'text']), default='text', help='Output format')
def analyze(symbol, exchange, days, output):
    """Comprehensive stock analysis"""
    try:
        symbol = symbol.upper()
        click.echo(f"🔍 Analyzing {symbol} on {exchange}...")
        
        # Get comprehensive analysis
        analysis = indian_toolkit.analyze_fundamentals(symbol, exchange)
        technical = indian_toolkit.analyze_technical(symbol, exchange, days)
        risk_assessment = indian_toolkit.assess_stock_risk(symbol, exchange)
        
        if output == 'json':
            result = {
                "symbol": symbol,
                "exchange": exchange,
                "fundamental_analysis": analysis,
                "technical_analysis": technical,
                "risk_assessment": risk_assessment
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("\n" + "="*80)
            click.echo(f"📊 COMPREHENSIVE ANALYSIS: {symbol}.{exchange}")
            click.echo("="*80)
            
            # Fundamental Analysis
            click.echo("\n🏢 FUNDAMENTAL ANALYSIS")
            click.echo("-" * 50)
            if 'analysis' in analysis:
                click.echo(analysis['analysis'])
            
            if 'recommendation' in analysis:
                click.echo(f"\n💡 Investment Recommendation:")
                click.echo(analysis['recommendation'])
            
            # Technical Analysis
            click.echo(f"\n📈 TECHNICAL ANALYSIS ({days} days)")
            click.echo("-" * 50)
            if 'technical_analysis' in technical:
                click.echo(technical['technical_analysis'])
            
            # Risk Assessment
            click.echo("\n⚠️ RISK ASSESSMENT")
            click.echo("-" * 50)
            if 'overall_risk_score' in risk_assessment:
                risk_score = risk_assessment['overall_risk_score']
                click.echo(f"Risk Score: {risk_score:.1f}/10")
                click.echo(f"Risk Level: {risk_assessment.get('recommendation', 'N/A')}")
            
            # Key Metrics Summary
            click.echo("\n📋 SUMMARY")
            click.echo("-" * 50)
            click.echo(f"Symbol: {symbol}.{exchange}")
            click.echo(f"Analysis Date: {analysis.get('analysis_date', 'N/A')}")
            click.echo(f"Fundamental Confidence: {analysis.get('confidence', 0):.1%}")
            click.echo(f"Technical Confidence: {technical.get('confidence', 0):.1%}")
            
    except Exception as e:
        click.echo(f"❌ Error analyzing {symbol}: {e}", err=True)
        sys.exit(1)

@stock.command()
@click.argument('symbol')
@click.option('--exchange', default='NSE', type=click.Choice(['NSE', 'BSE']), help='Exchange')
@click.option('--output', type=click.Choice(['json', 'text']), default='text', help='Output format')
def quote(symbol, exchange, output):
    """Get real-time stock quote"""
    try:
        symbol = symbol.upper()
        click.echo(f"💹 Getting quote for {symbol} on {exchange}...")
        
        quote_data = indian_toolkit.get_indian_stock_quote(symbol, exchange)
        
        if output == 'json':
            result = {
                "symbol": symbol,
                "exchange": exchange,
                "quote": quote_data
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("\n" + "="*50)
            click.echo(f"💹 REAL-TIME QUOTE: {symbol}.{exchange}")
            click.echo("="*50)
            click.echo(quote_data)
            
    except Exception as e:
        click.echo(f"❌ Error getting quote for {symbol}: {e}", err=True)
        sys.exit(1)

@stock.command()
@click.argument('symbol')
@click.option('--days', default=30, help='Number of days of historical data')
@click.option('--exchange', default='NSE', type=click.Choice(['NSE', 'BSE']), help='Exchange')
@click.option('--output', type=click.Choice(['json', 'text', 'csv']), default='text', help='Output format')
def data(symbol, days, exchange, output):
    """Get historical stock data"""
    try:
        symbol = symbol.upper()
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        click.echo(f"📊 Getting {days} days of data for {symbol} on {exchange}...")
        
        stock_data = indian_toolkit.get_indian_stock_data(symbol, start_date, end_date, exchange)
        
        if output == 'json':
            result = {
                "symbol": symbol,
                "exchange": exchange,
                "start_date": start_date,
                "end_date": end_date,
                "data": stock_data
            }
            click.echo(json.dumps(result, indent=2))
        elif output == 'csv':
            click.echo(stock_data)
        else:
            click.echo("\n" + "="*60)
            click.echo(f"📊 HISTORICAL DATA: {symbol}.{exchange}")
            click.echo(f"Period: {start_date} to {end_date}")
            click.echo("="*60)
            click.echo(stock_data)
            
    except Exception as e:
        click.echo(f"❌ Error getting data for {symbol}: {e}", err=True)
        sys.exit(1)

# Sector Commands
@sector.command()
@click.argument('sector_name')
@click.option('--date', default=None, help='Analysis date (YYYY-MM-DD)')
@click.option('--output', type=click.Choice(['json', 'text']), default='text', help='Output format')
def analyze(sector_name, date, output):
    """Analyze specific sector"""
    try:
        sector_name = sector_name.lower()
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        click.echo(f"🏭 Analyzing {sector_name.title()} sector...")
        
        sector_analysis = indian_toolkit.get_sector_analysis(sector_name, date)
        sector_stocks = indian_toolkit.get_sector_stocks(sector_name)
        
        if output == 'json':
            result = {
                "sector": sector_name,
                "analysis_date": date,
                "analysis": sector_analysis,
                "stocks": sector_stocks
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo("\n" + "="*60)
            click.echo(f"🏭 SECTOR ANALYSIS: {sector_name.upper()}")
            click.echo("="*60)
            click.echo(sector_analysis)
            
            if sector_stocks:
                click.echo(f"\n📈 KEY STOCKS IN {sector_name.upper()} SECTOR:")
                click.echo("-" * 40)
                for i, stock in enumerate(sector_stocks[:10], 1):
                    click.echo(f"{i:2d}. {stock}")
                if len(sector_stocks) > 10:
                    click.echo(f"    ... and {len(sector_stocks) - 10} more")
            
    except Exception as e:
        click.echo(f"❌ Error analyzing sector {sector_name}: {e}", err=True)
        sys.exit(1)

@sector.command()
def list():
    """List available sectors"""
    try:
        click.echo("\n🏭 AVAILABLE SECTORS FOR ANALYSIS")
        click.echo("="*50)
        
        for i, sector in enumerate(INDIAN_SECTORS.keys(), 1):
            stock_count = len(INDIAN_SECTORS[sector])
            click.echo(f"{i:2d}. {sector.title():<15} ({stock_count} stocks)")
        
        click.echo(f"\n💡 Use 'sector analyze <sector_name>' to analyze a specific sector")
        
    except Exception as e:
        click.echo(f"❌ Error listing sectors: {e}", err=True)
        sys.exit(1)

# Portfolio Commands
@portfolio.command()
@click.option('--file', type=click.Path(exists=True), help='Portfolio JSON file')
@click.option('--output', type=click.Choice(['json', 'text']), default='text', help='Output format')
def analyze(file, output):
    """Analyze portfolio performance"""
    try:
        if not file:
            click.echo("❌ Please provide a portfolio file with --file option", err=True)
            sys.exit(1)
        
        click.echo(f"📊 Analyzing portfolio from {file}...")
        
        # Load portfolio data
        with open(file, 'r') as f:
            portfolio_data = json.load(f)
        
        holdings = portfolio_data.get('holdings', [])
        
        # Calculate portfolio metrics
        metrics = indian_toolkit.calculate_portfolio_metrics(holdings)
        
        if output == 'json':
            click.echo(json.dumps(metrics, indent=2))
        else:
            click.echo("\n" + "="*60)
            click.echo("📊 PORTFOLIO ANALYSIS")
            click.echo("="*60)
            
            click.echo(f"Total Investment: ₹{metrics['total_investment']:,.2f}")
            click.echo(f"Current Value: ₹{metrics['total_current_value']:,.2f}")
            click.echo(f"Total P&L: ₹{metrics['total_pnl']:,.2f}")
            click.echo(f"Total P&L %: {metrics['total_pnl_percentage']:.2f}%")
            
            click.echo(f"\n📈 INDIVIDUAL HOLDINGS:")
            click.echo("-" * 60)
            for holding in metrics['holdings']:
                pnl_emoji = "🟢" if holding['pnl'] >= 0 else "🔴"
                click.echo(f"{pnl_emoji} {holding['symbol']:<10} | "
                          f"Qty: {holding['quantity']:>6} | "
                          f"P&L: ₹{holding['pnl']:>8.2f} ({holding['pnl_percentage']:>6.2f}%)")
            
    except Exception as e:
        click.echo(f"❌ Error analyzing portfolio: {e}", err=True)
        sys.exit(1)

@portfolio.command()
@click.argument('symbol')
@click.argument('entry_price', type=float)
@click.argument('stop_loss', type=float)
@click.argument('portfolio_value', type=float)
@click.option('--risk', default=2.0, help='Risk percentage (default: 2%)')
@click.option('--exchange', default='NSE', type=click.Choice(['NSE', 'BSE']), help='Exchange')
def position_size(symbol, entry_price, stop_loss, portfolio_value, risk, exchange):
    """Calculate optimal position size"""
    try:
        symbol = symbol.upper()
        risk_decimal = risk / 100
        
        click.echo(f"📊 Calculating position size for {symbol}...")
        
        position_calc = indian_toolkit.calculate_position_size(
            symbol, entry_price, stop_loss, portfolio_value, risk_decimal
        )
        
        if 'error' in position_calc:
            click.echo(f"❌ Error: {position_calc['error']}", err=True)
            sys.exit(1)
        
        click.echo("\n" + "="*60)
        click.echo(f"📊 POSITION SIZE CALCULATION: {symbol}.{exchange}")
        click.echo("="*60)
        click.echo(f"Entry Price: ₹{entry_price:,.2f}")
        click.echo(f"Stop Loss: ₹{stop_loss:,.2f}")
        click.echo(f"Portfolio Value: ₹{portfolio_value:,.2f}")
        click.echo(f"Risk Tolerance: {risk}%")
        
        click.echo(f"\n📈 RECOMMENDATION:")
        click.echo(f"Recommended Shares: {position_calc['recommended_shares']:,}")
        click.echo(f"Position Value: ₹{position_calc['position_value']:,.2f}")
        click.echo(f"Risk Amount: ₹{position_calc['risk_amount']:,.2f}")
        click.echo(f"Position %: {position_calc['position_percentage']:.2f}%")
        click.echo(f"Risk %: {position_calc['risk_percentage']:.2f}%")
        click.echo(f"Risk-Reward: {position_calc['risk_reward_ratio']}")
        
    except Exception as e:
        click.echo(f"❌ Error calculating position size: {e}", err=True)
        sys.exit(1)

# Utility Commands
@utils.command()
@click.argument('symbol')
@click.option('--exchange', default='NSE', type=click.Choice(['NSE', 'BSE']), help='Exchange')
def validate(symbol, exchange):
    """Validate ticker symbol"""
    try:
        formatted_ticker = format_indian_ticker(symbol, exchange)
        is_valid = validate_indian_ticker(formatted_ticker)
        
        click.echo(f"\n🔍 TICKER VALIDATION")
        click.echo("="*30)
        click.echo(f"Input: {symbol}")
        click.echo(f"Formatted: {formatted_ticker}")
        click.echo(f"Valid: {'✅ Yes' if is_valid else '❌ No'}")
        
    except Exception as e:
        click.echo(f"❌ Error validating ticker: {e}", err=True)
        sys.exit(1)

@utils.command()
def stocks():
    """List major Indian stocks"""
    try:
        major_stocks = get_major_stocks()
        
        click.echo("\n🏢 MAJOR INDIAN STOCKS")
        click.echo("="*60)
        
        for symbol, info in major_stocks.items():
            click.echo(f"{symbol:<12} | {info['name']:<30} | {info['sector']:<15}")
        
        click.echo(f"\n📊 Total: {len(major_stocks)} stocks")
        
    except Exception as e:
        click.echo(f"❌ Error listing stocks: {e}", err=True)
        sys.exit(1)

@utils.command()
def config():
    """Show Indian market configuration"""
    try:
        from tradingagents.indian_config import get_indian_config
        
        config = get_indian_config()
        
        click.echo("\n⚙️ INDIAN MARKET CONFIGURATION")
        click.echo("="*50)
        click.echo(f"Market Region: {config['market_region']}")
        click.echo(f"Currency: {config['currency']}")
        click.echo(f"Timezone: {config['timezone']}")
        click.echo(f"Primary Exchange: {config['exchanges']['primary']}")
        click.echo(f"Trading Hours: {config['trading_hours']['open']} - {config['trading_hours']['close']}")
        click.echo(f"Settlement: {config['market_parameters']['settlement']}")
        
    except Exception as e:
        click.echo(f"❌ Error showing config: {e}", err=True)
        sys.exit(1)

# Main CLI entry point
if __name__ == '__main__':
    indian_cli() 