"""
Indian Agent Toolkit
Comprehensive toolkit for Indian market trading agents with specialized tools and functions
"""

from typing import Annotated, Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

from tradingagents.dataflows.indian_interface import (
    get_indian_market_data_interface,
    get_indian_fundamentals_interface,
    get_indian_quote_interface,
    get_indian_news_interface,
    get_indian_sentiment_interface,
    get_indian_sector_analysis,
    get_indian_market_overview,
    get_indian_technical_indicators
)
from tradingagents.dataflows.ticker_utils import (
    format_indian_ticker,
    validate_indian_ticker,
    get_plain_symbol,
    process_ticker_list
)
from tradingagents.indian_config import (
    get_indian_config,
    get_major_stocks,
    get_sector_stocks,
    is_market_open,
    get_market_status
)
from tradingagents.agents.analysts.indian_fundamentals_analyst import IndianFundamentalsAnalyst
from tradingagents.agents.analysts.indian_market_analyst import IndianMarketAnalyst

logger = logging.getLogger(__name__)

class IndianAgentToolkit:
    """
    Comprehensive toolkit for Indian market trading agents
    
    Provides specialized tools for:
    - Indian market data retrieval
    - Fundamental and technical analysis
    - News and sentiment analysis
    - Risk management and position sizing
    - Market timing and execution
    """
    
    def __init__(self):
        self.config = get_indian_config()
        self.major_stocks = get_major_stocks()
        
        # Initialize specialized analysts
        self.fundamentals_analyst = IndianFundamentalsAnalyst()
        self.market_analyst = IndianMarketAnalyst()
        
        # Market parameters
        self.trading_hours = self.config["trading_hours"]
        self.risk_parameters = self.config["risk_parameters"]
        self.market_parameters = self.config["market_parameters"]
    
    # Market Data Tools
    def get_indian_stock_data(self,
                            symbol: Annotated[str, "Indian stock symbol (e.g., RELIANCE, TCS)"],
                            start_date: Annotated[str, "Start date (YYYY-MM-DD)"],
                            end_date: Annotated[str, "End date (YYYY-MM-DD)"],
                            exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> str:
        """Get historical stock data for Indian equity"""
        return get_indian_market_data_interface(symbol, start_date, end_date, exchange)
    
    def get_indian_stock_quote(self,
                             symbol: Annotated[str, "Indian stock symbol"],
                             exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> str:
        """Get real-time quote for Indian stock"""
        return get_indian_quote_interface(symbol, exchange)
    
    def get_indian_fundamentals(self,
                              symbol: Annotated[str, "Indian stock symbol"],
                              exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> str:
        """Get fundamental data for Indian company"""
        return get_indian_fundamentals_interface(symbol, exchange)
    
    def get_indian_news(self,
                       symbol: Annotated[str, "Indian stock symbol"],
                       days_back: Annotated[int, "Days to look back"] = 7) -> str:
        """Get Indian company news from local sources"""
        curr_date = datetime.now().strftime("%Y-%m-%d")
        return get_indian_news_interface(symbol, curr_date, days_back)
    
    def get_indian_sentiment(self,
                           symbol: Annotated[str, "Indian stock symbol"],
                           days_back: Annotated[int, "Days to look back"] = 7) -> str:
        """Get Indian social media sentiment"""
        curr_date = datetime.now().strftime("%Y-%m-%d")
        return get_indian_sentiment_interface(symbol, curr_date, days_back)
    
    def get_sector_analysis(self,
                          sector: Annotated[str, "Sector name (banking, it, pharma, etc.)"],
                          analysis_date: Annotated[str, "Analysis date (YYYY-MM-DD)"] = None) -> str:
        """Get Indian sector analysis"""
        if analysis_date is None:
            analysis_date = datetime.now().strftime("%Y-%m-%d")
        return get_indian_sector_analysis(sector, analysis_date)
    
    def get_market_overview(self,
                          analysis_date: Annotated[str, "Analysis date (YYYY-MM-DD)"] = None) -> str:
        """Get Indian market overview"""
        if analysis_date is None:
            analysis_date = datetime.now().strftime("%Y-%m-%d")
        return get_indian_market_overview(analysis_date)
    
    # Analysis Tools
    def analyze_fundamentals(self,
                           symbol: Annotated[str, "Indian stock symbol"],
                           exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> Dict[str, Any]:
        """Perform comprehensive fundamental analysis"""
        return self.fundamentals_analyst.analyze_fundamentals(symbol, exchange)
    
    def analyze_technical(self,
                        symbol: Annotated[str, "Indian stock symbol"],
                        exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE",
                        lookback_days: Annotated[int, "Days of data to analyze"] = 60) -> Dict[str, Any]:
        """Perform technical analysis"""
        return self.market_analyst.analyze_stock_technical(symbol, exchange, lookback_days=lookback_days)
    
    def analyze_market_conditions(self) -> Dict[str, Any]:
        """Analyze overall market conditions"""
        return self.market_analyst.analyze_market_conditions()
    
    def compare_with_peers(self,
                         symbol: Annotated[str, "Target stock symbol"],
                         peer_symbols: Annotated[List[str], "List of peer symbols"],
                         exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> Dict[str, Any]:
        """Compare stock with sector peers"""
        return self.fundamentals_analyst.compare_with_peers(symbol, peer_symbols, exchange)
    
    # Risk Management Tools
    def calculate_position_size(self,
                              symbol: Annotated[str, "Stock symbol"],
                              entry_price: Annotated[float, "Entry price in INR"],
                              stop_loss: Annotated[float, "Stop loss price in INR"],
                              portfolio_value: Annotated[float, "Total portfolio value in INR"],
                              risk_percentage: Annotated[float, "Risk percentage (0.01 = 1%)"] = 0.02) -> Dict[str, Any]:
        """Calculate position size based on risk management rules"""
        try:
            # Calculate risk per share
            risk_per_share = abs(entry_price - stop_loss)
            
            # Calculate maximum risk amount
            max_risk_amount = portfolio_value * risk_percentage
            
            # Calculate position size
            position_size = int(max_risk_amount / risk_per_share)
            
            # Apply Indian market constraints
            max_position_value = portfolio_value * self.risk_parameters["max_position_size"]
            max_shares_by_value = int(max_position_value / entry_price)
            
            # Take the minimum of both constraints
            final_position_size = min(position_size, max_shares_by_value)
            
            # Calculate actual risk and position value
            actual_risk = final_position_size * risk_per_share
            position_value = final_position_size * entry_price
            
            return {
                "symbol": symbol,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "recommended_shares": final_position_size,
                "position_value": position_value,
                "risk_amount": actual_risk,
                "risk_percentage": (actual_risk / portfolio_value) * 100,
                "position_percentage": (position_value / portfolio_value) * 100,
                "risk_reward_ratio": f"1:{abs((entry_price - stop_loss) / risk_per_share):.2f}"
            }
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return {"error": str(e)}
    
    def assess_stock_risk(self,
                        symbol: Annotated[str, "Stock symbol"],
                        exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> Dict[str, Any]:
        """Assess risk factors for a stock"""
        try:
            # Get fundamental analysis for risk assessment
            fund_analysis = self.fundamentals_analyst.analyze_fundamentals(symbol, exchange)
            
            # Get technical analysis for volatility assessment
            tech_analysis = self.market_analyst.analyze_stock_technical(symbol, exchange)
            
            # Calculate risk score
            risk_score = self._calculate_risk_score(fund_analysis, tech_analysis)
            
            return {
                "symbol": symbol,
                "exchange": exchange,
                "overall_risk_score": risk_score,
                "risk_factors": fund_analysis.get("risk_factors", []),
                "technical_risk": tech_analysis.get("risk_levels", {}),
                "recommendation": self._get_risk_recommendation(risk_score)
            }
            
        except Exception as e:
            logger.error(f"Error assessing stock risk: {e}")
            return {"error": str(e)}
    
    # Market Timing Tools
    def check_market_status(self) -> Dict[str, Any]:
        """Check current Indian market status"""
        return {
            "market_status": get_market_status(),
            "is_market_open": is_market_open(),
            "trading_hours": self.trading_hours,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
        }
    
    def get_optimal_entry_time(self,
                             symbol: Annotated[str, "Stock symbol"],
                             strategy: Annotated[str, "Trading strategy (intraday/swing/long_term)"] = "intraday") -> Dict[str, Any]:
        """Suggest optimal entry timing based on Indian market patterns"""
        try:
            market_status = get_market_status()
            current_time = datetime.now()
            
            recommendations = []
            
            if strategy == "intraday":
                if market_status == "pre_open":
                    recommendations.append("Wait for market opening and first 15 minutes of price discovery")
                elif market_status == "open":
                    hour = current_time.hour
                    if 9 <= hour <= 10:
                        recommendations.append("Good time for momentum trades - high volatility period")
                    elif 10 <= hour <= 14:
                        recommendations.append("Suitable for trend following strategies")
                    elif 14 <= hour <= 15:
                        recommendations.append("Closing hour - be cautious of volatility")
                    else:
                        recommendations.append("Market closed - prepare for next session")
                
            elif strategy == "swing":
                recommendations.append("Consider entering on weekly support levels")
                recommendations.append("Monitor for breakout patterns on daily charts")
                
            elif strategy == "long_term":
                recommendations.append("Focus on fundamental value rather than timing")
                recommendations.append("Consider systematic investment approach")
            
            return {
                "symbol": symbol,
                "strategy": strategy,
                "market_status": market_status,
                "recommendations": recommendations,
                "current_time": current_time.strftime("%Y-%m-%d %H:%M:%S IST")
            }
            
        except Exception as e:
            logger.error(f"Error getting optimal entry time: {e}")
            return {"error": str(e)}
    
    # Utility Tools
    def format_ticker(self,
                     symbol: Annotated[str, "Stock symbol"],
                     exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> str:
        """Format ticker for Indian exchanges"""
        return format_indian_ticker(symbol, exchange)
    
    def validate_ticker(self,
                       ticker: Annotated[str, "Ticker to validate"]) -> bool:
        """Validate Indian ticker format"""
        return validate_indian_ticker(ticker)
    
    def get_sector_stocks(self,
                        sector: Annotated[str, "Sector name"]) -> List[str]:
        """Get list of stocks in a sector"""
        return get_sector_stocks(sector)
    
    def get_major_stocks_list(self) -> Dict[str, Dict[str, str]]:
        """Get list of major Indian stocks"""
        return self.major_stocks
    
    def process_multiple_tickers(self,
                               symbols: Annotated[List[str], "List of stock symbols"],
                               exchange: Annotated[str, "Exchange (NSE/BSE)"] = "NSE") -> List[Dict[str, Any]]:
        """Process multiple ticker symbols"""
        return process_ticker_list(symbols, exchange)
    
    # Portfolio Tools
    def calculate_portfolio_metrics(self,
                                  holdings: Annotated[List[Dict[str, Any]], "List of holdings with symbol, quantity, avg_price"],
                                  current_date: Annotated[str, "Current date (YYYY-MM-DD)"] = None) -> Dict[str, Any]:
        """Calculate portfolio metrics for Indian stocks"""
        if current_date is None:
            current_date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            total_investment = 0
            total_current_value = 0
            portfolio_details = []
            
            for holding in holdings:
                symbol = holding["symbol"]
                quantity = holding["quantity"]
                avg_price = holding["avg_price"]
                
                # Get current price
                quote = get_indian_quote_interface(symbol)
                # In production, would parse actual price from quote
                current_price = avg_price * 1.05  # Placeholder - 5% gain
                
                investment = quantity * avg_price
                current_value = quantity * current_price
                pnl = current_value - investment
                pnl_percentage = (pnl / investment) * 100
                
                total_investment += investment
                total_current_value += current_value
                
                portfolio_details.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "investment": investment,
                    "current_value": current_value,
                    "pnl": pnl,
                    "pnl_percentage": pnl_percentage
                })
            
            total_pnl = total_current_value - total_investment
            total_pnl_percentage = (total_pnl / total_investment) * 100
            
            return {
                "total_investment": total_investment,
                "total_current_value": total_current_value,
                "total_pnl": total_pnl,
                "total_pnl_percentage": total_pnl_percentage,
                "holdings": portfolio_details,
                "analysis_date": current_date
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
            return {"error": str(e)}
    
    # Helper Methods
    def _calculate_risk_score(self, fund_analysis: Dict[str, Any], tech_analysis: Dict[str, Any]) -> float:
        """Calculate overall risk score (0-10, higher is riskier)"""
        risk_factors = []
        
        # Fundamental risk factors
        if fund_analysis.get("confidence", 0) < 0.5:
            risk_factors.append(2.0)  # Low confidence adds risk
        
        # Technical risk factors
        tech_confidence = tech_analysis.get("confidence", 0)
        if tech_confidence < 0.5:
            risk_factors.append(1.5)
        
        # Market risk (simplified)
        risk_factors.append(5.0)  # Base market risk
        
        return min(sum(risk_factors), 10.0)
    
    def _get_risk_recommendation(self, risk_score: float) -> str:
        """Get risk recommendation based on score"""
        if risk_score <= 3:
            return "LOW RISK - Suitable for conservative investors"
        elif risk_score <= 6:
            return "MEDIUM RISK - Suitable for moderate risk tolerance"
        elif risk_score <= 8:
            return "HIGH RISK - Suitable for aggressive investors only"
        else:
            return "VERY HIGH RISK - Speculative investment, exercise extreme caution"

# Create global toolkit instance
indian_toolkit = IndianAgentToolkit()

# Export functions for agent use
def get_indian_stock_data(symbol: str, start_date: str, end_date: str, exchange: str = "NSE") -> str:
    """Get Indian stock data"""
    return indian_toolkit.get_indian_stock_data(symbol, start_date, end_date, exchange)

def get_indian_stock_quote(symbol: str, exchange: str = "NSE") -> str:
    """Get Indian stock quote"""
    return indian_toolkit.get_indian_stock_quote(symbol, exchange)

def get_indian_fundamentals(symbol: str, exchange: str = "NSE") -> str:
    """Get Indian fundamentals"""
    return indian_toolkit.get_indian_fundamentals(symbol, exchange)

def analyze_indian_stock(symbol: str, exchange: str = "NSE") -> Dict[str, Any]:
    """Comprehensive Indian stock analysis"""
    return {
        "fundamental_analysis": indian_toolkit.analyze_fundamentals(symbol, exchange),
        "technical_analysis": indian_toolkit.analyze_technical(symbol, exchange),
        "risk_assessment": indian_toolkit.assess_stock_risk(symbol, exchange)
    }

def calculate_position_size(symbol: str, entry_price: float, stop_loss: float, 
                          portfolio_value: float, risk_percentage: float = 0.02) -> Dict[str, Any]:
    """Calculate position size for Indian stock"""
    return indian_toolkit.calculate_position_size(symbol, entry_price, stop_loss, 
                                                portfolio_value, risk_percentage)

def get_market_status() -> Dict[str, Any]:
    """Get Indian market status"""
    return indian_toolkit.check_market_status()

# Export toolkit class
__all__ = [
    'IndianAgentToolkit',
    'indian_toolkit',
    'get_indian_stock_data',
    'get_indian_stock_quote', 
    'get_indian_fundamentals',
    'analyze_indian_stock',
    'calculate_position_size',
    'get_market_status'
] 