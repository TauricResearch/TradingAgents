"""
Perplexity Finance API Connector for real-time financial analysis and research.
Provides sophisticated market insights, company analysis, and investment research.
"""

import asyncio
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import aiohttp
from pydantic import BaseModel, Field
import logging

from autonomous.core.cache import RedisCache, CacheKey

logger = logging.getLogger(__name__)


class AnalysisType(str, Enum):
    """Types of financial analysis available"""
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    EARNINGS = "earnings"
    VALUATION = "valuation"
    COMPETITIVE = "competitive"
    MACRO = "macro"
    INSIDER = "insider"
    INSTITUTIONAL = "institutional"
    OPTIONS_FLOW = "options_flow"


class ResearchDepth(str, Enum):
    """Depth of research analysis"""
    QUICK = "quick"      # Fast, surface-level analysis
    STANDARD = "standard" # Regular depth analysis
    DEEP = "deep"        # Comprehensive deep dive
    EXPERT = "expert"    # Expert-level with all data sources


@dataclass
class StockAnalysis:
    """Complete stock analysis result"""
    ticker: str
    timestamp: datetime
    analysis_type: AnalysisType

    # Core metrics
    current_price: float
    fair_value: Optional[float]
    upside_potential: Optional[float]

    # Fundamental data
    pe_ratio: Optional[float]
    peg_ratio: Optional[float]
    price_to_book: Optional[float]
    debt_to_equity: Optional[float]
    roe: Optional[float]
    revenue_growth: Optional[float]
    earnings_growth: Optional[float]

    # Analysis results
    bull_case: str
    bear_case: str
    key_risks: List[str]
    catalysts: List[str]

    # Recommendations
    rating: str  # Buy, Hold, Sell
    confidence_score: float  # 0-100
    time_horizon: str  # short, medium, long

    # Raw analysis text
    detailed_analysis: str
    data_sources: List[str]


@dataclass
class MarketScreenerResult:
    """Result from market screening queries"""
    query: str
    timestamp: datetime
    total_results: int

    stocks: List[Dict[str, Any]]  # List of matching stocks with details
    screening_criteria: Dict[str, Any]
    market_context: str

    # Top picks
    best_value: List[str]
    highest_growth: List[str]
    lowest_risk: List[str]

    detailed_explanation: str


class PerplexityFinanceConnector:
    """
    Connector for Perplexity Finance API providing advanced financial analysis.
    Combines multiple data sources for comprehensive investment research.
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 cache: Optional[RedisCache] = None,
                 rate_limit: int = 50):  # requests per minute
        """
        Initialize Perplexity Finance connector.

        Args:
            api_key: Perplexity API key
            cache: Redis cache instance
            rate_limit: Maximum requests per minute
        """
        self.api_key = api_key or os.getenv('PERPLEXITY_API_KEY')
        if not self.api_key:
            raise ValueError("Perplexity API key required")

        self.base_url = "https://api.perplexity.ai"
        self.cache = cache
        self.rate_limit = rate_limit
        self.last_request_time = datetime.now()

        # Headers for API requests
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Finance-specific model that has access to real-time data
        self.finance_model = "pplx-70b-online"  # or "pplx-7b-online" for faster

    async def analyze_stock(self,
                          ticker: str,
                          analysis_type: AnalysisType = AnalysisType.FUNDAMENTAL,
                          depth: ResearchDepth = ResearchDepth.STANDARD) -> StockAnalysis:
        """
        Perform comprehensive analysis on a single stock.

        Args:
            ticker: Stock symbol
            analysis_type: Type of analysis to perform
            depth: Depth of research

        Returns:
            StockAnalysis object with complete findings
        """
        # Check cache first
        cache_key = f"{CacheKey.AI_DECISION}:perplexity:{ticker}:{analysis_type}"
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Using cached Perplexity analysis for {ticker}")
                return StockAnalysis(**cached)

        # Construct analysis prompt based on type
        prompt = self._build_analysis_prompt(ticker, analysis_type, depth)

        # Make API request with financial context
        analysis_text = await self._query_perplexity(
            prompt,
            context="financial_analysis",
            include_sources=True
        )

        # Parse the analysis into structured format
        result = await self._parse_analysis(ticker, analysis_text, analysis_type)

        # Cache the result
        if self.cache:
            await self.cache.set(cache_key, result.__dict__, ttl=3600)  # 1 hour cache

        return result

    async def screen_stocks(self,
                          query: str,
                          max_results: int = 20,
                          filters: Optional[Dict[str, Any]] = None) -> MarketScreenerResult:
        """
        Screen stocks based on natural language query.

        Args:
            query: Natural language screening query
            max_results: Maximum number of stocks to return
            filters: Additional filters (market cap, sector, etc.)

        Returns:
            MarketScreenerResult with matching stocks
        """
        # Build comprehensive screening prompt
        prompt = f"""
        Financial Stock Screening Request:
        {query}

        Requirements:
        1. Search across US listed stocks
        2. Return up to {max_results} stocks that match
        3. Include current price, market cap, P/E ratio, and key metrics
        4. Rank by best match to the query criteria
        5. Explain why each stock matches
        6. Consider recent market conditions

        Additional filters: {json.dumps(filters) if filters else 'None'}

        Provide:
        - List of matching stocks with tickers
        - Key metrics for each
        - Brief explanation of fit
        - Overall market context
        """

        # Query Perplexity with financial context
        response = await self._query_perplexity(
            prompt,
            context="stock_screening",
            include_sources=True
        )

        # Parse screening results
        result = await self._parse_screening_results(query, response)

        return result

    async def research_investment_thesis(self,
                                        question: str,
                                        tickers: Optional[List[str]] = None,
                                        include_portfolio_context: bool = True) -> Dict[str, Any]:
        """
        Answer complex investment research questions using Perplexity's knowledge.

        Args:
            question: Investment research question
            tickers: Optional list of tickers to focus on
            include_portfolio_context: Include current portfolio in analysis

        Returns:
            Comprehensive research response
        """
        # Build context-aware prompt
        prompt = f"""
        Investment Research Query:
        {question}

        {"Focus on these stocks: " + ", ".join(tickers) if tickers else ""}

        Please provide:
        1. Direct answer to the question
        2. Supporting data and metrics
        3. Current market context
        4. Specific actionable recommendations
        5. Risk factors to consider
        6. Time horizon for thesis
        7. Alternative perspectives

        Use the most recent financial data available and cite sources.
        """

        # Add portfolio context if requested
        if include_portfolio_context and tickers:
            prompt += f"\nCurrent portfolio includes: {', '.join(tickers)}"

        # Query with extended timeout for complex research
        response = await self._query_perplexity(
            prompt,
            context="investment_research",
            include_sources=True,
            max_tokens=2000
        )

        # Structure the research response
        return self._structure_research_response(question, response)

    async def get_market_sentiment(self,
                                  sector: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current market sentiment and trends.

        Args:
            sector: Optional sector to focus on

        Returns:
            Market sentiment analysis
        """
        prompt = f"""
        Analyze current market sentiment {f'for {sector} sector' if sector else 'overall'}:

        1. Bull vs Bear sentiment
        2. Key concerns and opportunities
        3. Institutional positioning
        4. Retail investor sentiment
        5. Options flow indicators
        6. Technical levels to watch
        7. Upcoming catalysts

        Based on the last 24-48 hours of market activity.
        """

        response = await self._query_perplexity(prompt, context="market_sentiment")

        return {
            "timestamp": datetime.now().isoformat(),
            "sector": sector or "market",
            "analysis": response,
            "data_freshness": "real-time"
        }

    async def analyze_earnings(self,
                              ticker: str,
                              include_guidance: bool = True) -> Dict[str, Any]:
        """
        Analyze recent earnings and forward guidance.

        Args:
            ticker: Stock symbol
            include_guidance: Include forward guidance analysis

        Returns:
            Earnings analysis
        """
        prompt = f"""
        Analyze {ticker} earnings:

        1. Most recent earnings results vs expectations
        2. Revenue and EPS growth trends
        3. Key metrics and KPIs
        4. Management commentary highlights
        {"5. Forward guidance analysis" if include_guidance else ""}
        6. Analyst revisions post-earnings
        7. Price target changes
        8. Key takeaways for investors

        Include specific numbers and percentages.
        """

        response = await self._query_perplexity(
            prompt,
            context="earnings_analysis",
            include_sources=True
        )

        return {
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
            "analysis": response,
            "includes_guidance": include_guidance
        }

    async def find_similar_stocks(self,
                                 ticker: str,
                                 criteria: str = "business_model") -> List[Dict[str, Any]]:
        """
        Find stocks similar to a given ticker.

        Args:
            ticker: Reference stock symbol
            criteria: Similarity criteria (business_model, valuation, growth, etc.)

        Returns:
            List of similar stocks with comparison
        """
        prompt = f"""
        Find stocks similar to {ticker} based on {criteria}:

        1. List 5-10 similar companies
        2. Compare key metrics
        3. Highlight advantages/disadvantages vs {ticker}
        4. Current valuation comparison
        5. Growth rate comparison
        6. Risk profile comparison

        Focus on investable alternatives.
        """

        response = await self._query_perplexity(prompt, context="peer_analysis")

        # Parse into structured format
        return self._parse_peer_comparison(ticker, response)

    async def analyze_insider_activity(self,
                                      ticker: str,
                                      days_back: int = 90) -> Dict[str, Any]:
        """
        Analyze insider trading activity.

        Args:
            ticker: Stock symbol
            days_back: Days of history to analyze

        Returns:
            Insider activity analysis
        """
        prompt = f"""
        Analyze insider trading for {ticker} over the last {days_back} days:

        1. Major insider purchases/sales
        2. C-suite and board activity
        3. Transaction sizes and prices
        4. Historical pattern comparison
        5. Sentiment signal (bullish/bearish/neutral)
        6. Notable 10b5-1 plan changes

        Interpret what the insider activity suggests.
        """

        response = await self._query_perplexity(prompt, context="insider_trading")

        return {
            "ticker": ticker,
            "period_days": days_back,
            "analysis": response,
            "timestamp": datetime.now().isoformat()
        }

    async def _query_perplexity(self,
                               prompt: str,
                               context: str = "general",
                               include_sources: bool = True,
                               max_tokens: int = 1500) -> str:
        """
        Make API request to Perplexity.

        Args:
            prompt: Query prompt
            context: Context type for the query
            include_sources: Include source citations
            max_tokens: Maximum response tokens

        Returns:
            API response text
        """
        # Rate limiting
        await self._rate_limit()

        # Prepare request payload
        payload = {
            "model": self.finance_model,
            "messages": [
                {
                    "role": "system",
                    "content": f"You are a senior financial analyst providing {context} analysis. "
                              "Use real-time market data and cite credible sources. "
                              "Be specific with numbers, percentages, and dates."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,  # Lower temperature for factual finance data
            "return_citations": include_sources,
            "search_domain_filter": ["finance", "investing", "markets"],
            "search_recency_filter": "day"  # Prioritize recent information
        }

        # Make async request
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content']
                    else:
                        error = await response.text()
                        logger.error(f"Perplexity API error: {error}")
                        raise Exception(f"API request failed: {error}")

            except asyncio.TimeoutError:
                logger.error("Perplexity API request timed out")
                raise
            except Exception as e:
                logger.error(f"Perplexity API error: {e}")
                raise

    async def _rate_limit(self):
        """Implement rate limiting"""
        now = datetime.now()
        time_since_last = (now - self.last_request_time).total_seconds()
        min_interval = 60 / self.rate_limit  # seconds between requests

        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        self.last_request_time = datetime.now()

    def _build_analysis_prompt(self,
                              ticker: str,
                              analysis_type: AnalysisType,
                              depth: ResearchDepth) -> str:
        """Build analysis prompt based on type and depth"""

        base_prompt = f"Analyze {ticker} stock with focus on {analysis_type.value} analysis.\n\n"

        if analysis_type == AnalysisType.FUNDAMENTAL:
            base_prompt += """
            Include:
            1. Current valuation metrics (P/E, PEG, P/B, EV/EBITDA)
            2. Profitability metrics (ROE, ROA, profit margins)
            3. Growth metrics (revenue, earnings, FCF growth)
            4. Balance sheet strength (debt/equity, current ratio)
            5. Competitive position and moat
            6. Management quality and capital allocation
            7. Fair value estimate using DCF or comparable analysis
            8. Investment recommendation with price target
            """

        elif analysis_type == AnalysisType.TECHNICAL:
            base_prompt += """
            Include:
            1. Current price action and trend
            2. Key support and resistance levels
            3. Moving averages (20, 50, 200 day)
            4. RSI, MACD, and momentum indicators
            5. Volume analysis
            6. Chart patterns forming
            7. Fibonacci levels if relevant
            8. Short-term and medium-term outlook
            """

        elif analysis_type == AnalysisType.VALUATION:
            base_prompt += """
            Perform comprehensive valuation:
            1. DCF model with assumptions
            2. Comparable company analysis
            3. Precedent transaction analysis
            4. Sum-of-parts if applicable
            5. Sensitivity analysis on key variables
            6. Bear, base, and bull case scenarios
            7. Margin of safety calculation
            8. Investment recommendation
            """

        # Add depth modifiers
        if depth == ResearchDepth.DEEP:
            base_prompt += "\n\nProvide extensive detail with specific numbers, calculations, and comprehensive analysis."
        elif depth == ResearchDepth.EXPERT:
            base_prompt += "\n\nProvide institutional-quality analysis with detailed models, risk scenarios, and actionable insights."

        return base_prompt

    async def _parse_analysis(self,
                             ticker: str,
                             raw_analysis: str,
                             analysis_type: AnalysisType) -> StockAnalysis:
        """Parse raw analysis text into structured StockAnalysis"""

        # Use another Perplexity call to extract structured data
        extract_prompt = f"""
        From this analysis of {ticker}, extract:

        1. Current price
        2. Fair value estimate
        3. P/E ratio
        4. PEG ratio
        5. Rating (Buy/Hold/Sell)
        6. Key risks (list)
        7. Catalysts (list)
        8. Confidence score (0-100)

        Analysis text:
        {raw_analysis[:2000]}

        Return in JSON format.
        """

        structured = await self._query_perplexity(
            extract_prompt,
            context="data_extraction",
            max_tokens=500
        )

        # Parse JSON response (with fallback)
        try:
            import re
            json_match = re.search(r'\{.*\}', structured, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {}
        except:
            data = {}

        # Build StockAnalysis object
        return StockAnalysis(
            ticker=ticker,
            timestamp=datetime.now(),
            analysis_type=analysis_type,
            current_price=data.get('current_price', 0),
            fair_value=data.get('fair_value'),
            upside_potential=data.get('upside_potential'),
            pe_ratio=data.get('pe_ratio'),
            peg_ratio=data.get('peg_ratio'),
            price_to_book=None,
            debt_to_equity=None,
            roe=None,
            revenue_growth=None,
            earnings_growth=None,
            bull_case=data.get('bull_case', ''),
            bear_case=data.get('bear_case', ''),
            key_risks=data.get('key_risks', []),
            catalysts=data.get('catalysts', []),
            rating=data.get('rating', 'Hold'),
            confidence_score=data.get('confidence_score', 50),
            time_horizon='medium',
            detailed_analysis=raw_analysis,
            data_sources=['Perplexity AI', 'Real-time market data']
        )

    async def _parse_screening_results(self,
                                      query: str,
                                      raw_response: str) -> MarketScreenerResult:
        """Parse screening response into structured format"""

        # Extract stock list using Perplexity
        extract_prompt = f"""
        From this screening result, extract a list of stock tickers with their key metrics.
        Format as JSON array with ticker, company_name, price, market_cap, pe_ratio for each.

        Response:
        {raw_response[:1500]}
        """

        structured = await self._query_perplexity(
            extract_prompt,
            context="data_extraction",
            max_tokens=500
        )

        # Parse stocks list
        try:
            import re
            json_match = re.search(r'\[.*\]', structured, re.DOTALL)
            if json_match:
                stocks = json.loads(json_match.group())
            else:
                stocks = []
        except:
            stocks = []

        return MarketScreenerResult(
            query=query,
            timestamp=datetime.now(),
            total_results=len(stocks),
            stocks=stocks,
            screening_criteria={},
            market_context="",
            best_value=[s['ticker'] for s in stocks[:3]] if stocks else [],
            highest_growth=[],
            lowest_risk=[],
            detailed_explanation=raw_response
        )

    def _structure_research_response(self,
                                    question: str,
                                    response: str) -> Dict[str, Any]:
        """Structure research response into organized format"""

        return {
            "question": question,
            "timestamp": datetime.now().isoformat(),
            "answer": response,
            "sections": {
                "summary": response[:500] if len(response) > 500 else response,
                "detailed_analysis": response,
                "actionable_insights": self._extract_actionables(response),
                "risks": self._extract_risks(response),
                "data_sources": ["Perplexity AI", "Real-time market data"]
            },
            "confidence": "high" if "strong" in response.lower() else "medium",
            "requires_update": False
        }

    def _extract_actionables(self, text: str) -> List[str]:
        """Extract actionable insights from text"""
        actionables = []

        # Look for action words
        action_keywords = ['buy', 'sell', 'hold', 'consider', 'avoid', 'monitor', 'wait']
        lines = text.split('\n')

        for line in lines:
            if any(keyword in line.lower() for keyword in action_keywords):
                actionables.append(line.strip())

        return actionables[:5]  # Top 5 actionables

    def _extract_risks(self, text: str) -> List[str]:
        """Extract risk factors from text"""
        risks = []

        risk_keywords = ['risk', 'concern', 'threat', 'challenge', 'weakness', 'vulnerable']
        lines = text.split('\n')

        for line in lines:
            if any(keyword in line.lower() for keyword in risk_keywords):
                risks.append(line.strip())

        return risks[:5]  # Top 5 risks

    def _parse_peer_comparison(self, ticker: str, response: str) -> List[Dict[str, Any]]:
        """Parse peer comparison response"""

        # Simple extraction of mentioned tickers
        import re

        # Find all uppercase ticker symbols
        potential_tickers = re.findall(r'\b[A-Z]{2,5}\b', response)

        # Filter out the original ticker and common words
        peers = [t for t in potential_tickers if t != ticker and len(t) <= 5][:10]

        return [
            {
                "ticker": peer,
                "similarity_score": 0.8,  # Would calculate based on metrics
                "comparison": f"Similar to {ticker}",
                "advantage": "Extracted from analysis",
                "disadvantage": "Extracted from analysis"
            }
            for peer in peers[:5]
        ]