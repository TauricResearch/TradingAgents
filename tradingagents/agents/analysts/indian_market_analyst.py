"""
Indian Market Analyst Agent
Specialized agent for analyzing Indian market dynamics, technical patterns, and trading opportunities
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
import pandas as pd

from tradingagents.agents.utils.agent_utils import AgentUtils
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.dataflows.indian_interface import (
    get_indian_market_data_interface,
    get_indian_quote_interface,
    get_indian_market_overview,
    get_indian_technical_indicators
)
from tradingagents.indian_config import get_indian_config, is_market_open, get_market_status

logger = logging.getLogger(__name__)

class IndianMarketAnalyst:
    """
    Indian Market Analyst Agent
    
    Specializes in:
    - Indian market technical analysis
    - Market sentiment and momentum
    - Index analysis and correlation
    - Trading patterns specific to Indian markets
    - Market timing and entry/exit strategies
    """
    
    def __init__(self, agent_id: str = "indian_market_analyst"):
        self.agent_id = agent_id
        self.agent_utils = AgentUtils()
        self.state = AgentState()
        self.config = get_indian_config()
        
        # Indian market specific parameters
        self.major_indices = self.config["benchmark_indices"]["broad_market"]
        self.sectoral_indices = self.config["benchmark_indices"]["sectoral"]
        self.trading_hours = self.config["trading_hours"]
        
        # Technical indicators to analyze
        self.technical_indicators = [
            "sma_20", "sma_50", "sma_200", "ema_12", "ema_26",
            "rsi_14", "macd", "bollinger_bands", "atr", "adx",
            "stochastic", "williams_r", "cci", "mfi"
        ]
        
        # Market breadth indicators
        self.market_breadth_indicators = [
            "advance_decline_ratio", "new_highs_lows", "volume_analysis",
            "india_vix", "fii_dii_flows", "sector_rotation"
        ]
    
    def analyze_market_conditions(self, analysis_date: str = None) -> Dict[str, Any]:
        """
        Analyze overall Indian market conditions
        
        Args:
            analysis_date: Date for analysis
            
        Returns:
            Market conditions analysis
        """
        if analysis_date is None:
            analysis_date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Get market overview
            market_overview = get_indian_market_overview(analysis_date)
            
            # Get market status
            market_status = get_market_status()
            
            # Analyze major indices
            indices_analysis = self._analyze_major_indices(analysis_date)
            
            # Generate market conditions analysis
            conditions_analysis = self._generate_market_conditions_analysis(
                market_overview, indices_analysis, market_status, analysis_date
            )
            
            return {
                "agent_id": self.agent_id,
                "analysis_date": analysis_date,
                "market_status": market_status,
                "market_conditions": conditions_analysis,
                "indices_analysis": indices_analysis,
                "confidence": self._calculate_market_confidence(conditions_analysis),
                "trading_bias": self._determine_trading_bias(conditions_analysis),
                "key_levels": self._identify_key_levels(indices_analysis)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing market conditions: {e}")
            return {
                "agent_id": self.agent_id,
                "error": str(e),
                "analysis": f"Unable to analyze market conditions: {e}"
            }
    
    def analyze_stock_technical(self, 
                              symbol: str, 
                              exchange: str = "NSE",
                              analysis_date: str = None,
                              lookback_days: int = 60) -> Dict[str, Any]:
        """
        Perform technical analysis on Indian stock
        
        Args:
            symbol: Stock symbol
            exchange: Exchange (NSE/BSE)
            analysis_date: Date for analysis
            lookback_days: Days of historical data to analyze
            
        Returns:
            Technical analysis results
        """
        if analysis_date is None:
            analysis_date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Get historical data
            start_date = (datetime.strptime(analysis_date, "%Y-%m-%d") - 
                         timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            
            market_data = get_indian_market_data_interface(
                symbol, start_date, analysis_date, exchange
            )
            
            # Get current quote
            current_quote = get_indian_quote_interface(symbol, exchange)
            
            # Generate technical analysis
            technical_analysis = self._generate_technical_analysis(
                symbol, market_data, current_quote, analysis_date, lookback_days
            )
            
            # Calculate support and resistance levels
            support_resistance = self._calculate_support_resistance(market_data)
            
            return {
                "agent_id": self.agent_id,
                "symbol": symbol,
                "exchange": exchange,
                "analysis_date": analysis_date,
                "technical_analysis": technical_analysis,
                "support_resistance": support_resistance,
                "trading_signals": self._generate_trading_signals(technical_analysis),
                "risk_levels": self._calculate_risk_levels(symbol, market_data),
                "confidence": self._calculate_technical_confidence(market_data)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing stock technical for {symbol}: {e}")
            return {
                "agent_id": self.agent_id,
                "symbol": symbol,
                "error": str(e),
                "analysis": f"Unable to analyze technical for {symbol}: {e}"
            }
    
    def _analyze_major_indices(self, analysis_date: str) -> Dict[str, Any]:
        """Analyze major Indian indices"""
        indices_data = {}
        
        # Analyze Nifty 50 and Sensex
        for index in self.major_indices:
            try:
                start_date = (datetime.strptime(analysis_date, "%Y-%m-%d") - 
                             timedelta(days=30)).strftime("%Y-%m-%d")
                
                index_data = get_indian_market_data_interface(
                    index, start_date, analysis_date, "NSE"
                )
                indices_data[index] = index_data
                
            except Exception as e:
                logger.warning(f"Could not get data for index {index}: {e}")
                indices_data[index] = f"Error getting data: {e}"
        
        return indices_data
    
    def _generate_market_conditions_analysis(self, 
                                           market_overview: str,
                                           indices_analysis: Dict[str, Any],
                                           market_status: str,
                                           analysis_date: str) -> str:
        """Generate comprehensive market conditions analysis"""
        
        indices_data_text = "\n\n".join([
            f"{index}:\n{data}" for index, data in indices_analysis.items()
        ])
        
        prompt = f"""
        As an expert Indian market analyst, provide a comprehensive analysis of current market conditions:

        MARKET OVERVIEW:
        {market_overview}

        INDICES DATA:
        {indices_data_text}

        MARKET STATUS: {market_status}
        ANALYSIS DATE: {analysis_date}

        Provide your analysis covering:

        1. OVERALL MARKET SENTIMENT:
        - Current market trend (bullish/bearish/sideways)
        - Market momentum and strength
        - Volatility assessment (India VIX context)
        - Risk appetite indicators

        2. TECHNICAL MARKET STRUCTURE:
        - Key support and resistance levels for Nifty 50
        - Index correlation analysis
        - Volume patterns and participation
        - Breadth indicators (advance/decline)

        3. SECTORAL ANALYSIS:
        - Leading and lagging sectors
        - Sector rotation patterns
        - Relative strength analysis
        - Sector-specific opportunities

        4. INSTITUTIONAL ACTIVITY:
        - FII/DII flow patterns
        - Institutional buying/selling pressure
        - Impact on market direction
        - Liquidity conditions

        5. GLOBAL CONTEXT:
        - Impact of global markets on Indian indices
        - Currency (USD-INR) influence
        - Commodity price effects
        - Geopolitical factors

        6. TRADING ENVIRONMENT:
        - Market volatility assessment
        - Trading opportunities quality
        - Risk management considerations
        - Position sizing recommendations

        7. NEAR-TERM OUTLOOK:
        - Expected market direction (1-2 weeks)
        - Key events and catalysts
        - Potential market scenarios
        - Trading strategy recommendations

        Focus on actionable insights for Indian equity traders and investors.
        """
        
        try:
            analysis = self.agent_utils.query_gpt_single(prompt)
            return analysis
        except Exception as e:
            logger.error(f"Error generating market conditions analysis: {e}")
            return f"Error generating market analysis: {e}"
    
    def _generate_technical_analysis(self, 
                                   symbol: str,
                                   market_data: str,
                                   current_quote: str,
                                   analysis_date: str,
                                   lookback_days: int) -> str:
        """Generate technical analysis for individual stock"""
        
        prompt = f"""
        As an expert Indian equity technical analyst, provide comprehensive technical analysis for {symbol}:

        HISTORICAL DATA ({lookback_days} days):
        {market_data}

        CURRENT QUOTE:
        {current_quote}

        ANALYSIS DATE: {analysis_date}

        Provide detailed technical analysis covering:

        1. PRICE ACTION ANALYSIS:
        - Current trend direction and strength
        - Key price levels and patterns
        - Candlestick patterns and signals
        - Volume-price relationship

        2. MOVING AVERAGES:
        - 20, 50, 200 SMA analysis
        - EMA crossovers and signals
        - Price position relative to moving averages
        - Moving average support/resistance

        3. MOMENTUM INDICATORS:
        - RSI (14) analysis and divergences
        - MACD signal and histogram
        - Stochastic oscillator readings
        - Rate of change indicators

        4. VOLATILITY ANALYSIS:
        - Bollinger Bands position
        - Average True Range (ATR)
        - Volatility breakouts or contractions
        - Risk assessment based on volatility

        5. VOLUME ANALYSIS:
        - Volume trends and patterns
        - Volume confirmation of price moves
        - On-balance volume (OBV)
        - Volume-based support/resistance

        6. CHART PATTERNS:
        - Identify any chart patterns (triangles, flags, etc.)
        - Pattern completion levels
        - Breakout/breakdown scenarios
        - Target price projections

        7. SUPPORT AND RESISTANCE:
        - Key support levels
        - Key resistance levels
        - Fibonacci retracement levels
        - Pivot points for intraday trading

        8. TRADING SIGNALS:
        - Buy/sell signals based on technical indicators
        - Entry and exit points
        - Stop-loss recommendations
        - Target price levels

        Provide specific price levels in INR and actionable trading recommendations.
        """
        
        try:
            analysis = self.agent_utils.query_gpt_single(prompt)
            return analysis
        except Exception as e:
            logger.error(f"Error generating technical analysis: {e}")
            return f"Error generating technical analysis: {e}"
    
    def _calculate_support_resistance(self, market_data: str) -> Dict[str, List[float]]:
        """Calculate support and resistance levels"""
        # This is a simplified implementation
        # In production, would parse the CSV data and calculate actual levels
        
        try:
            # Extract price information from market data
            # For now, return placeholder levels
            return {
                "support_levels": [2400.0, 2350.0, 2300.0],  # Example levels
                "resistance_levels": [2500.0, 2550.0, 2600.0],
                "pivot_point": 2450.0,
                "fibonacci_levels": [2380.0, 2420.0, 2480.0, 2520.0]
            }
        except Exception as e:
            logger.error(f"Error calculating support/resistance: {e}")
            return {
                "support_levels": [],
                "resistance_levels": [],
                "error": str(e)
            }
    
    def _generate_trading_signals(self, technical_analysis: str) -> List[Dict[str, Any]]:
        """Generate trading signals based on technical analysis"""
        
        prompt = f"""
        Based on the following technical analysis, generate specific trading signals:

        TECHNICAL ANALYSIS:
        {technical_analysis}

        Generate up to 3 trading signals in the following format for each signal:
        
        Signal Type: [BUY/SELL/HOLD]
        Entry Price: [Specific price in INR]
        Stop Loss: [Specific price in INR]
        Target 1: [Specific price in INR]
        Target 2: [Specific price in INR]
        Risk-Reward Ratio: [X:Y]
        Time Horizon: [Intraday/Short-term/Medium-term]
        Confidence: [High/Medium/Low]
        Rationale: [Brief explanation]

        Focus on high-probability setups with clear risk management.
        """
        
        try:
            signals_text = self.agent_utils.query_gpt_single(prompt)
            
            # Parse signals (simplified implementation)
            signals = []
            signal_blocks = signals_text.split("Signal Type:")
            
            for block in signal_blocks[1:]:  # Skip first empty block
                try:
                    lines = block.strip().split('\n')
                    signal = {
                        "signal_type": lines[0].strip(),
                        "entry_price": self._extract_price(lines[1]) if len(lines) > 1 else None,
                        "stop_loss": self._extract_price(lines[2]) if len(lines) > 2 else None,
                        "target_1": self._extract_price(lines[3]) if len(lines) > 3 else None,
                        "target_2": self._extract_price(lines[4]) if len(lines) > 4 else None,
                        "time_horizon": lines[6].split(':')[1].strip() if len(lines) > 6 else "Unknown",
                        "confidence": lines[7].split(':')[1].strip() if len(lines) > 7 else "Medium"
                    }
                    signals.append(signal)
                except Exception as e:
                    logger.warning(f"Error parsing signal: {e}")
                    continue
            
            return signals[:3]  # Return max 3 signals
            
        except Exception as e:
            logger.error(f"Error generating trading signals: {e}")
            return [{"error": str(e)}]
    
    def _extract_price(self, line: str) -> Optional[float]:
        """Extract price from a line of text"""
        try:
            # Simple regex to find numbers
            import re
            matches = re.findall(r'\d+\.?\d*', line)
            return float(matches[0]) if matches else None
        except:
            return None
    
    def _calculate_risk_levels(self, symbol: str, market_data: str) -> Dict[str, float]:
        """Calculate risk levels for position sizing"""
        
        # Simplified risk calculation
        # In production, would calculate based on actual volatility
        
        return {
            "daily_atr": 50.0,  # Average True Range
            "volatility_percentile": 65.0,  # Current volatility vs historical
            "max_position_size": 0.05,  # 5% of portfolio
            "recommended_stop_loss": 0.08,  # 8% stop loss
            "risk_score": 6.5  # Out of 10
        }
    
    def _calculate_market_confidence(self, conditions_analysis: str) -> float:
        """Calculate confidence in market analysis"""
        
        # Simple confidence scoring based on analysis content
        confidence_factors = []
        
        if "bullish" in conditions_analysis.lower():
            confidence_factors.append(0.3)
        elif "bearish" in conditions_analysis.lower():
            confidence_factors.append(0.3)
        
        if "strong" in conditions_analysis.lower():
            confidence_factors.append(0.2)
        
        if "volume" in conditions_analysis.lower():
            confidence_factors.append(0.2)
        
        if "support" in conditions_analysis.lower() or "resistance" in conditions_analysis.lower():
            confidence_factors.append(0.3)
        
        return min(sum(confidence_factors), 1.0)
    
    def _calculate_technical_confidence(self, market_data: str) -> float:
        """Calculate confidence in technical analysis"""
        
        # Check data quality
        if "Error" in market_data or "No data" in market_data:
            return 0.1
        
        # Check data completeness (simplified)
        if len(market_data) > 1000:  # Reasonable amount of data
            return 0.8
        elif len(market_data) > 500:
            return 0.6
        else:
            return 0.4
    
    def _determine_trading_bias(self, conditions_analysis: str) -> str:
        """Determine overall trading bias"""
        
        analysis_lower = conditions_analysis.lower()
        
        bullish_signals = ["bullish", "uptrend", "positive", "strong", "buy"]
        bearish_signals = ["bearish", "downtrend", "negative", "weak", "sell"]
        
        bullish_count = sum(1 for signal in bullish_signals if signal in analysis_lower)
        bearish_count = sum(1 for signal in bearish_signals if signal in analysis_lower)
        
        if bullish_count > bearish_count:
            return "BULLISH"
        elif bearish_count > bullish_count:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _identify_key_levels(self, indices_analysis: Dict[str, Any]) -> Dict[str, List[float]]:
        """Identify key levels for major indices"""
        
        # Simplified key levels identification
        # In production, would parse actual price data
        
        return {
            "nifty_50": {
                "support": [24000, 23800, 23500],
                "resistance": [24500, 24800, 25000]
            },
            "bank_nifty": {
                "support": [51000, 50500, 50000],
                "resistance": [52000, 52500, 53000]
            }
        }

# Example usage and testing
if __name__ == "__main__":
    analyst = IndianMarketAnalyst()
    
    # Test market conditions analysis
    market_result = analyst.analyze_market_conditions()
    print("Market Conditions Analysis:")
    print(market_result)
    
    # Test stock technical analysis
    stock_result = analyst.analyze_stock_technical("RELIANCE", "NSE")
    print("\nStock Technical Analysis:")
    print(stock_result) 