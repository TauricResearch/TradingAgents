"""
Indian Fundamentals Analyst Agent
Specialized agent for analyzing Indian company fundamentals with local market context
"""

from typing import Dict, Any, List
from datetime import datetime
import logging

from tradingagents.agents.utils.agent_utils import AgentUtils
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.dataflows.indian_interface import (
    get_indian_fundamentals_interface,
    get_indian_market_data_interface,
    get_indian_sector_analysis
)
from tradingagents.indian_config import get_major_stocks, get_sector_stocks

logger = logging.getLogger(__name__)

class IndianFundamentalsAnalyst:
    """
    Indian Fundamentals Analyst Agent
    
    Specializes in analyzing Indian company fundamentals with context of:
    - Indian accounting standards and financial reporting
    - SEBI regulations and compliance
    - Indian market dynamics and sectoral trends
    - Local economic factors and government policies
    """
    
    def __init__(self, agent_id: str = "indian_fundamentals_analyst"):
        self.agent_id = agent_id
        self.agent_utils = AgentUtils()
        self.state = AgentState()
        
        # Indian market specific knowledge
        self.major_stocks = get_major_stocks()
        
        # Key Indian financial metrics to focus on
        self.key_metrics = [
            "marketCap", "trailingPE", "priceToBook", "dividendYield",
            "eps", "revenue", "sector", "industry", "beta",
            "profitMargins", "operatingMargins", "returnOnEquity",
            "returnOnAssets", "debtToEquity", "currentRatio",
            "quickRatio", "freeCashFlow", "totalCash", "totalDebt"
        ]
        
        # Indian market context factors
        self.indian_context_factors = [
            "FII/DII holdings", "Promoter holding", "Pledge percentage",
            "Government ownership", "Regulatory environment", "Policy impact",
            "Currency exposure", "Export dependency", "Domestic demand",
            "Seasonal factors", "Competition landscape"
        ]
    
    def analyze_fundamentals(self, 
                           symbol: str, 
                           exchange: str = "NSE",
                           analysis_date: str = None) -> Dict[str, Any]:
        """
        Perform comprehensive fundamental analysis for Indian stock
        
        Args:
            symbol: Stock symbol
            exchange: Exchange (NSE/BSE)
            analysis_date: Date of analysis
            
        Returns:
            Dictionary with analysis results
        """
        if analysis_date is None:
            analysis_date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Get fundamental data
            fundamentals_data = get_indian_fundamentals_interface(symbol, exchange)
            
            # Get sector analysis for context
            if symbol.upper() in self.major_stocks:
                sector = self.major_stocks[symbol.upper()]["sector"]
                sector_analysis = get_indian_sector_analysis(sector, analysis_date)
            else:
                sector_analysis = "Sector analysis not available for this stock"
            
            # Generate analysis
            analysis = self._generate_fundamental_analysis(
                symbol, fundamentals_data, sector_analysis, analysis_date
            )
            
            return {
                "agent_id": self.agent_id,
                "symbol": symbol,
                "exchange": exchange,
                "analysis_date": analysis_date,
                "analysis": analysis,
                "confidence": self._calculate_confidence(fundamentals_data),
                "recommendation": self._generate_recommendation(analysis),
                "risk_factors": self._identify_risk_factors(symbol, fundamentals_data),
                "opportunities": self._identify_opportunities(symbol, fundamentals_data)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing fundamentals for {symbol}: {e}")
            return {
                "agent_id": self.agent_id,
                "symbol": symbol,
                "error": str(e),
                "analysis": f"Unable to analyze fundamentals for {symbol}: {e}"
            }
    
    def _generate_fundamental_analysis(self, 
                                     symbol: str, 
                                     fundamentals_data: str, 
                                     sector_analysis: str,
                                     analysis_date: str) -> str:
        """Generate comprehensive fundamental analysis"""
        
        prompt = f"""
        As an expert Indian equity fundamentals analyst, provide a comprehensive analysis of {symbol} based on the following data:

        FUNDAMENTAL DATA:
        {fundamentals_data}

        SECTOR CONTEXT:
        {sector_analysis}

        ANALYSIS DATE: {analysis_date}

        Please provide your analysis covering:

        1. FINANCIAL HEALTH ASSESSMENT:
        - Revenue growth trends and sustainability
        - Profitability metrics (gross, operating, net margins)
        - Return ratios (ROE, ROA, ROCE)
        - Debt levels and financial leverage
        - Cash flow generation and quality

        2. VALUATION ANALYSIS:
        - Current valuation multiples (P/E, P/B, EV/EBITDA)
        - Comparison with sector peers and historical averages
        - Dividend yield and payout sustainability
        - Price-to-earnings growth (PEG) ratio assessment

        3. INDIAN MARKET SPECIFIC FACTORS:
        - Regulatory environment and compliance status
        - Government policy impact on the business
        - FII/DII holding patterns and trends
        - Promoter holding strength and pledge status
        - Currency exposure and hedging strategies

        4. BUSINESS QUALITY ASSESSMENT:
        - Competitive positioning in Indian market
        - Management quality and corporate governance
        - Growth drivers and expansion plans
        - Market share and competitive advantages
        - ESG (Environmental, Social, Governance) factors

        5. SECTOR AND MACRO CONTEXT:
        - Industry growth prospects in India
        - Regulatory changes affecting the sector
        - Economic policy impact (GST, tax changes, etc.)
        - Infrastructure development benefits
        - Demographic trends and consumption patterns

        6. RISK ASSESSMENT:
        - Key business risks and mitigation strategies
        - Regulatory and policy risks
        - Market competition and disruption risks
        - Financial risks (debt, liquidity, currency)
        - Operational risks specific to Indian operations

        7. INVESTMENT THESIS:
        - Long-term growth potential
        - Value creation opportunities
        - Catalyst events and triggers
        - Suitable investment horizon
        - Risk-adjusted return expectations

        Provide specific, actionable insights with Indian market context. Use INR values where applicable and consider local market dynamics.
        """
        
        try:
            analysis = self.agent_utils.query_gpt_single(prompt)
            return analysis
        except Exception as e:
            logger.error(f"Error generating fundamental analysis: {e}")
            return f"Error generating analysis: {e}"
    
    def _calculate_confidence(self, fundamentals_data: str) -> float:
        """Calculate confidence level based on data quality"""
        confidence_factors = []
        
        # Check data completeness
        if "Error" not in fundamentals_data and "No data" not in fundamentals_data:
            confidence_factors.append(0.3)
        
        # Check for key metrics presence
        key_metrics_present = sum(1 for metric in self.key_metrics 
                                if metric.lower() in fundamentals_data.lower())
        confidence_factors.append(min(key_metrics_present / len(self.key_metrics), 0.4))
        
        # Check for financial statements
        if "income_statement" in fundamentals_data.lower():
            confidence_factors.append(0.2)
        if "balance_sheet" in fundamentals_data.lower():
            confidence_factors.append(0.1)
        
        return min(sum(confidence_factors), 1.0)
    
    def _generate_recommendation(self, analysis: str) -> str:
        """Generate investment recommendation based on analysis"""
        
        prompt = f"""
        Based on the following fundamental analysis of an Indian stock, provide a clear investment recommendation:

        ANALYSIS:
        {analysis}

        Provide a recommendation in the following format:
        
        RECOMMENDATION: [BUY/HOLD/SELL]
        
        TARGET PRICE: [Specific price target in INR with rationale]
        
        TIME HORIZON: [Short-term (3-6 months) / Medium-term (6-18 months) / Long-term (18+ months)]
        
        KEY RATIONALE:
        - [3-5 key points supporting the recommendation]
        
        RISK CONSIDERATIONS:
        - [2-3 main risks to the investment thesis]
        
        Keep the recommendation concise and actionable for Indian equity investors.
        """
        
        try:
            recommendation = self.agent_utils.query_gpt_single(prompt)
            return recommendation
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}")
            return f"Error generating recommendation: {e}"
    
    def _identify_risk_factors(self, symbol: str, fundamentals_data: str) -> List[str]:
        """Identify key risk factors for the stock"""
        
        prompt = f"""
        Based on the fundamental data for {symbol}, identify the top 5 risk factors for Indian investors:

        DATA:
        {fundamentals_data}

        Focus on risks specific to:
        - Indian market dynamics
        - Regulatory environment
        - Business model vulnerabilities
        - Financial risks
        - Sector-specific challenges

        Provide a list of 5 specific risk factors, each in one sentence.
        """
        
        try:
            risks_text = self.agent_utils.query_gpt_single(prompt)
            # Parse into list (simple implementation)
            risks = [risk.strip() for risk in risks_text.split('\n') if risk.strip() and not risk.strip().startswith('#')]
            return risks[:5]  # Limit to top 5
        except Exception as e:
            logger.error(f"Error identifying risks: {e}")
            return [f"Error identifying risks: {e}"]
    
    def _identify_opportunities(self, symbol: str, fundamentals_data: str) -> List[str]:
        """Identify key opportunities for the stock"""
        
        prompt = f"""
        Based on the fundamental data for {symbol}, identify the top 5 opportunities for Indian investors:

        DATA:
        {fundamentals_data}

        Focus on opportunities from:
        - Indian market growth potential
        - Policy tailwinds and government support
        - Business expansion possibilities
        - Competitive advantages
        - Sector growth drivers

        Provide a list of 5 specific opportunities, each in one sentence.
        """
        
        try:
            opportunities_text = self.agent_utils.query_gpt_single(prompt)
            # Parse into list (simple implementation)
            opportunities = [opp.strip() for opp in opportunities_text.split('\n') if opp.strip() and not opp.strip().startswith('#')]
            return opportunities[:5]  # Limit to top 5
        except Exception as e:
            logger.error(f"Error identifying opportunities: {e}")
            return [f"Error identifying opportunities: {e}"]
    
    def compare_with_peers(self, 
                          symbol: str, 
                          peer_symbols: List[str],
                          exchange: str = "NSE") -> Dict[str, Any]:
        """
        Compare stock with sector peers
        
        Args:
            symbol: Target stock symbol
            peer_symbols: List of peer stock symbols
            exchange: Exchange
            
        Returns:
            Comparative analysis
        """
        try:
            # Get fundamental data for all stocks
            all_stocks = [symbol] + peer_symbols
            fundamentals_data = {}
            
            for stock in all_stocks:
                fundamentals_data[stock] = get_indian_fundamentals_interface(stock, exchange)
            
            # Generate comparative analysis
            comparison = self._generate_peer_comparison(symbol, fundamentals_data)
            
            return {
                "agent_id": self.agent_id,
                "target_symbol": symbol,
                "peer_symbols": peer_symbols,
                "comparison": comparison,
                "analysis_date": datetime.now().strftime("%Y-%m-%d")
            }
            
        except Exception as e:
            logger.error(f"Error comparing with peers: {e}")
            return {
                "agent_id": self.agent_id,
                "error": str(e),
                "comparison": f"Unable to compare with peers: {e}"
            }
    
    def _generate_peer_comparison(self, symbol: str, fundamentals_data: Dict[str, str]) -> str:
        """Generate peer comparison analysis"""
        
        data_text = "\n\n".join([f"{stock}:\n{data}" for stock, data in fundamentals_data.items()])
        
        prompt = f"""
        Compare {symbol} with its sector peers based on the following fundamental data:

        {data_text}

        Provide a comprehensive peer comparison covering:

        1. VALUATION METRICS COMPARISON:
        - P/E ratios ranking
        - P/B ratios comparison
        - EV/EBITDA multiples
        - Dividend yields

        2. PROFITABILITY COMPARISON:
        - Gross margins
        - Operating margins
        - Net margins
        - Return on equity

        3. FINANCIAL STRENGTH COMPARISON:
        - Debt-to-equity ratios
        - Current ratios
        - Cash positions
        - Interest coverage

        4. GROWTH COMPARISON:
        - Revenue growth rates
        - Earnings growth
        - Market share trends
        - Expansion plans

        5. RELATIVE POSITIONING:
        - Strengths of {symbol} vs peers
        - Weaknesses vs peers
        - Unique value propositions
        - Investment attractiveness ranking

        Conclude with which stock offers the best risk-adjusted returns for Indian investors.
        """
        
        try:
            comparison = self.agent_utils.query_gpt_single(prompt)
            return comparison
        except Exception as e:
            logger.error(f"Error generating peer comparison: {e}")
            return f"Error generating peer comparison: {e}"

# Example usage and testing
if __name__ == "__main__":
    analyst = IndianFundamentalsAnalyst()
    
    # Test with Reliance Industries
    result = analyst.analyze_fundamentals("RELIANCE", "NSE")
    print("Analysis Result:")
    print(result)
    
    # Test peer comparison
    peer_result = analyst.compare_with_peers("RELIANCE", ["ONGC", "IOC", "BPCL"])
    print("\nPeer Comparison:")
    print(peer_result) 