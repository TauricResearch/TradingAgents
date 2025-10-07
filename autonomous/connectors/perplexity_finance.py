"""
Perplexity Finance API Connector for real-time financial analysis and research.
FIXED VERSION: Addresses all critical issues from code review.
"""

import asyncio
import os
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
from pydantic import BaseModel, Field, validator
import logging

# Import cache if available
try:
    from autonomous.core.cache import RedisCache, CacheKey
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

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
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"
    EXPERT = "expert"


@dataclass
class StockAnalysis:
    """Complete stock analysis result"""
    ticker: str
    timestamp: datetime
    analysis_type: AnalysisType
    current_price: float
    fair_value: Optional[float]
    upside_potential: Optional[float]
    pe_ratio: Optional[float]
    peg_ratio: Optional[float]
    price_to_book: Optional[float]
    debt_to_equity: Optional[float]
    roe: Optional[float]
    revenue_growth: Optional[float]
    earnings_growth: Optional[float]
    bull_case: str
    bear_case: str
    key_risks: List[str]
    catalysts: List[str]
    rating: str
    confidence_score: float
    time_horizon: str
    detailed_analysis: str
    data_sources: List[str]


@dataclass
class MarketScreenerResult:
    """Result from market screening queries"""
    query: str
    timestamp: datetime
    total_results: int
    stocks: List[Dict[str, Any]]
    screening_criteria: Dict[str, Any]
    market_context: str
    best_value: List[str]
    highest_growth: List[str]
    lowest_risk: List[str]
    detailed_explanation: str


class PerplexityFinanceConnector:
    """
    Fixed connector for Perplexity Finance API providing advanced financial analysis.
    """

    # List of valid Perplexity models (as of Jan 2024)
    VALID_MODELS = [
        "pplx-7b-online",      # Fast online model
        "pplx-70b-online",     # Large online model (may require pro)
        "pplx-7b-chat",        # Fast chat model
        "pplx-70b-chat",       # Large chat model
        "sonar-small-online",  # New Sonar models
        "sonar-medium-online",
        "sonar-small-chat",
        "sonar-medium-chat"
    ]

    def __init__(self,
                 api_key: Optional[str] = None,
                 cache: Optional[RedisCache] = None,
                 rate_limit: int = 50,
                 model: Optional[str] = None):
        """
        Initialize Perplexity Finance connector.

        Args:
            api_key: Perplexity API key
            cache: Redis cache instance
            rate_limit: Maximum requests per minute
            model: Specific model to use (defaults to auto-selection)
        """
        self.api_key = api_key or os.getenv('PERPLEXITY_API_KEY')
        if not self.api_key:
            raise ValueError("Perplexity API key required. Set PERPLEXITY_API_KEY environment variable.")

        self.base_url = "https://api.perplexity.ai"
        self.cache = cache if cache and CACHE_AVAILABLE else None
        self.rate_limit = rate_limit
        self.last_request_time = datetime.now(timezone.utc)

        # Headers for API requests
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Select appropriate model
        if model and model in self.VALID_MODELS:
            self.finance_model = model
        else:
            # Default to most reliable model
            self.finance_model = "sonar-small-online"  # Fast and reliable
            logger.info(f"Using default model: {self.finance_model}")

        # Track rate limiting
        self.request_count = 0
        self.rate_limit_reset = datetime.now(timezone.utc)

    async def analyze_stock(self,
                          ticker: str,
                          analysis_type: AnalysisType = AnalysisType.FUNDAMENTAL,
                          depth: ResearchDepth = ResearchDepth.STANDARD) -> StockAnalysis:
        """
        Perform comprehensive analysis on a single stock.
        """
        # Validate ticker
        if not ticker or not ticker.replace('-', '').replace('.', '').isalnum():
            raise ValueError(f"Invalid ticker symbol: {ticker}")

        # Check cache first
        cache_key = f"{CacheKey.AI_DECISION if CACHE_AVAILABLE else 'ai'}:perplexity:{ticker}:{analysis_type.value}"
        if self.cache:
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    logger.info(f"Using cached Perplexity analysis for {ticker}")
                    # Reconstruct StockAnalysis from dict
                    cached['timestamp'] = datetime.fromisoformat(cached['timestamp'])
                    cached['analysis_type'] = AnalysisType(cached['analysis_type'])
                    return StockAnalysis(**cached)
            except Exception as e:
                logger.warning(f"Cache retrieval error: {e}")

        # Construct analysis prompt
        prompt = self._build_analysis_prompt(ticker, analysis_type, depth)

        try:
            # Make API request with financial context
            analysis_text = await self._query_perplexity(
                prompt,
                context="financial_analysis",
                include_sources=True
            )

            # Parse into structured format (simplified - avoid double API call)
            result = self._parse_analysis_locally(ticker, analysis_text, analysis_type)

            # Cache the result
            if self.cache:
                try:
                    cache_data = asdict(result)
                    cache_data['timestamp'] = cache_data['timestamp'].isoformat()
                    cache_data['analysis_type'] = cache_data['analysis_type'].value
                    await self.cache.set(cache_key, cache_data, ttl=3600)  # 1 hour cache
                except Exception as e:
                    logger.warning(f"Cache storage error: {e}")

            return result

        except Exception as e:
            logger.error(f"Stock analysis failed for {ticker}: {e}")
            # Return minimal result on error
            return StockAnalysis(
                ticker=ticker,
                timestamp=datetime.now(timezone.utc),
                analysis_type=analysis_type,
                current_price=0,
                fair_value=None,
                upside_potential=None,
                pe_ratio=None,
                peg_ratio=None,
                price_to_book=None,
                debt_to_equity=None,
                roe=None,
                revenue_growth=None,
                earnings_growth=None,
                bull_case="Analysis unavailable",
                bear_case="Analysis unavailable",
                key_risks=["Analysis failed"],
                catalysts=[],
                rating="Hold",
                confidence_score=0,
                time_horizon="medium",
                detailed_analysis=str(e),
                data_sources=["Error"]
            )

    async def screen_stocks(self,
                          query: str,
                          max_results: int = 20,
                          filters: Optional[Dict[str, Any]] = None) -> MarketScreenerResult:
        """
        Screen stocks based on natural language query.
        """
        if not query:
            raise ValueError("Query cannot be empty")

        # Sanitize query to prevent injection
        query = query[:500]  # Limit length
        query = re.sub(r'[^\w\s\-.,?!$%]', '', query)  # Remove special chars

        prompt = f"""
        Financial Stock Screening Request:
        {query}

        Requirements:
        1. Search across US listed stocks
        2. Return up to {min(max_results, 50)} stocks
        3. Include current price, market cap, P/E ratio
        4. Rank by relevance
        5. Consider recent market conditions

        Filters: {json.dumps(filters) if filters else 'None'}

        Format response with clear ticker symbols and metrics.
        """

        try:
            response = await self._query_perplexity(
                prompt,
                context="stock_screening",
                include_sources=True
            )

            result = self._parse_screening_locally(query, response)
            return result

        except Exception as e:
            logger.error(f"Stock screening failed: {e}")
            return MarketScreenerResult(
                query=query,
                timestamp=datetime.now(timezone.utc),
                total_results=0,
                stocks=[],
                screening_criteria=filters or {},
                market_context="Screening failed",
                best_value=[],
                highest_growth=[],
                lowest_risk=[],
                detailed_explanation=str(e)
            )

    async def _query_perplexity(self,
                               prompt: str,
                               context: str = "general",
                               include_sources: bool = True,
                               max_tokens: int = 1500) -> str:
        """
        Make API request to Perplexity with proper error handling.
        """
        # Rate limiting
        await self._rate_limit()

        # Sanitize prompt
        prompt = prompt[:4000]  # Perplexity has token limits

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
            "temperature": 0.2,
            "return_citations": include_sources,
            "search_domain_filter": ["finance", "investing", "markets"],
            "search_recency_filter": "day"
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:

                    # Handle rate limiting
                    if response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', 60))
                        logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                        await asyncio.sleep(retry_after)
                        return await self._query_perplexity(prompt, context, include_sources, max_tokens)

                    if response.status == 200:
                        data = await response.json()

                        # Validate response structure
                        if not data.get('choices'):
                            raise ValueError("Empty response from Perplexity API")

                        if len(data['choices']) == 0:
                            raise ValueError("No choices in Perplexity response")

                        choice = data['choices'][0]
                        if 'message' not in choice or 'content' not in choice['message']:
                            raise ValueError("Malformed response structure from Perplexity")

                        content = choice['message']['content']
                        if not content:
                            raise ValueError("Empty content in Perplexity response")

                        return content

                    else:
                        # Sanitize error before logging (remove potential API key)
                        error = await response.text()
                        error = re.sub(r'Bearer [^\s]+', 'Bearer ***', error)
                        logger.error(f"Perplexity API error (status {response.status}): {error[:200]}")
                        raise Exception(f"API request failed with status {response.status}")

            except asyncio.TimeoutError:
                logger.error("Perplexity API request timed out")
                raise
            except Exception as e:
                # Sanitize error message
                error_msg = str(e)
                error_msg = re.sub(r'Bearer [^\s]+', 'Bearer ***', error_msg)
                logger.error(f"Perplexity API error: {error_msg}")
                raise

    async def _rate_limit(self):
        """Implement proper rate limiting with tracking"""
        now = datetime.now(timezone.utc)

        # Reset counter every minute
        if (now - self.rate_limit_reset).total_seconds() > 60:
            self.request_count = 0
            self.rate_limit_reset = now

        # Check if we've hit the limit
        if self.request_count >= self.rate_limit:
            sleep_time = 60 - (now - self.rate_limit_reset).total_seconds()
            if sleep_time > 0:
                logger.info(f"Rate limit reached. Sleeping {sleep_time:.1f} seconds...")
                await asyncio.sleep(sleep_time)
                self.request_count = 0
                self.rate_limit_reset = datetime.now(timezone.utc)

        # Minimum time between requests
        time_since_last = (now - self.last_request_time).total_seconds()
        min_interval = 60 / self.rate_limit  # seconds between requests

        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        self.last_request_time = datetime.now(timezone.utc)
        self.request_count += 1

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
            4. Balance sheet strength
            5. Competitive position
            6. Fair value estimate
            7. Investment recommendation
            """
        elif analysis_type == AnalysisType.TECHNICAL:
            base_prompt += """
            Include:
            1. Current price action and trend
            2. Support and resistance levels
            3. Moving averages
            4. RSI, MACD indicators
            5. Volume analysis
            6. Chart patterns
            7. Short-term outlook
            """
        elif analysis_type == AnalysisType.VALUATION:
            base_prompt += """
            Perform valuation:
            1. DCF analysis
            2. Comparable company analysis
            3. Sensitivity analysis
            4. Fair value range
            5. Investment recommendation
            """

        if depth == ResearchDepth.DEEP:
            base_prompt += "\nProvide extensive detail with specific numbers."
        elif depth == ResearchDepth.EXPERT:
            base_prompt += "\nProvide institutional-quality analysis."

        return base_prompt

    def _parse_analysis_locally(self,
                               ticker: str,
                               raw_analysis: str,
                               analysis_type: AnalysisType) -> StockAnalysis:
        """Parse raw analysis text locally without additional API call"""

        # Extract metrics using regex patterns
        def extract_number(pattern: str, text: str, default: float = 0) -> float:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1).replace(',', '').replace('$', ''))
                except:
                    pass
            return default

        current_price = extract_number(r'current.*?price.*?\$?([\d,.]+)', raw_analysis)
        fair_value = extract_number(r'fair.*?value.*?\$?([\d,.]+)', raw_analysis)
        pe_ratio = extract_number(r'p/e.*?ratio.*?([\d,.]+)', raw_analysis)

        # Calculate upside if we have both prices
        upside_potential = None
        if current_price > 0 and fair_value > 0:
            upside_potential = ((fair_value - current_price) / current_price) * 100

        # Extract rating
        rating = "Hold"
        if re.search(r'\b(strong\s+)?buy\b', raw_analysis, re.IGNORECASE):
            rating = "Buy"
        elif re.search(r'\b(strong\s+)?sell\b', raw_analysis, re.IGNORECASE):
            rating = "Sell"

        # Extract risks and catalysts
        risks = []
        risk_section = re.search(r'risk[s]?:?(.*?)(?:catalyst|opportunit|\n\n)',
                                 raw_analysis, re.IGNORECASE | re.DOTALL)
        if risk_section:
            risks = [r.strip() for r in risk_section.group(1).split('\n')
                    if r.strip() and len(r.strip()) > 10][:5]

        # Build analysis object
        return StockAnalysis(
            ticker=ticker,
            timestamp=datetime.now(timezone.utc),
            analysis_type=analysis_type,
            current_price=current_price,
            fair_value=fair_value if fair_value > 0 else None,
            upside_potential=upside_potential,
            pe_ratio=pe_ratio if pe_ratio > 0 else None,
            peg_ratio=None,
            price_to_book=None,
            debt_to_equity=None,
            roe=None,
            revenue_growth=None,
            earnings_growth=None,
            bull_case=raw_analysis[:500],
            bear_case="See full analysis",
            key_risks=risks if risks else ["See full analysis"],
            catalysts=[],
            rating=rating,
            confidence_score=70,  # Default moderate confidence
            time_horizon="medium",
            detailed_analysis=raw_analysis,
            data_sources=["Perplexity AI", "Real-time market data"]
        )

    def _parse_screening_locally(self, query: str, raw_response: str) -> MarketScreenerResult:
        """Parse screening response locally"""

        # Extract stock symbols using regex
        ticker_pattern = r'\b([A-Z]{1,5})\b(?:\s*[\:\-\|]|\s+at\s+\$)'
        tickers = re.findall(ticker_pattern, raw_response)

        # Remove common words that look like tickers
        exclude = {'THE', 'AND', 'FOR', 'NYSE', 'NASDAQ', 'IPO', 'CEO', 'CFO', 'Q1', 'Q2', 'Q3', 'Q4'}
        tickers = [t for t in tickers if t not in exclude][:20]

        # Build basic stock info
        stocks = []
        for ticker in tickers[:10]:  # Limit to 10
            # Try to find price near ticker mention
            price_pattern = rf'{ticker}.*?\$?([\d,.]+)'
            price_match = re.search(price_pattern, raw_response)
            price = float(price_match.group(1).replace(',', '')) if price_match else 0

            stocks.append({
                'ticker': ticker,
                'company_name': '',
                'price': price,
                'pe_ratio': None,
                'market_cap': None
            })

        return MarketScreenerResult(
            query=query,
            timestamp=datetime.now(timezone.utc),
            total_results=len(stocks),
            stocks=stocks,
            screening_criteria={},
            market_context=raw_response[:200],
            best_value=[s['ticker'] for s in stocks[:3]],
            highest_growth=[],
            lowest_risk=[],
            detailed_explanation=raw_response
        )

    # Additional helper methods remain the same but with proper error handling
    async def get_market_sentiment(self, sector: Optional[str] = None) -> Dict[str, Any]:
        """Get current market sentiment with error handling"""
        try:
            prompt = f"""
            Analyze current market sentiment {f'for {sector} sector' if sector else 'overall'}:
            1. Bull vs Bear sentiment
            2. Key concerns
            3. Opportunities
            4. Technical levels
            """

            response = await self._query_perplexity(prompt, context="market_sentiment")

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sector": sector or "market",
                "analysis": response,
                "data_freshness": "real-time"
            }
        except Exception as e:
            logger.error(f"Market sentiment analysis failed: {e}")
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sector": sector or "market",
                "analysis": "Analysis unavailable",
                "error": str(e)
            }