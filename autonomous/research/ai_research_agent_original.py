"""
AI Research Agent - Conversational interface for complex investment research.
Combines multiple data sources to answer sophisticated investment questions.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import logging
from decimal import Decimal

from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain.agents.output_parsers import OpenAIFunctionsAgentOutputParser
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from pydantic import BaseModel, Field

# Import our connectors and modules
from autonomous.connectors.perplexity_finance import (
    PerplexityFinanceConnector,
    AnalysisType,
    ResearchDepth
)
from autonomous.core.database import DatabaseManager
from autonomous.core.cache import RedisCache
from autonomous.data_aggregator import DataAggregator
from autonomous.signal_processor import SignalProcessor
from autonomous.core.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class ResearchQuery(BaseModel):
    """Structure for research queries"""
    question: str = Field(..., description="The investment research question")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")
    depth: str = Field(default="standard", description="Depth of analysis: quick, standard, deep")
    include_portfolio: bool = Field(default=True, description="Consider current portfolio")
    time_horizon: Optional[str] = Field(default=None, description="Investment time horizon")


class ResearchResponse(BaseModel):
    """Structure for research responses"""
    query: str
    answer: str
    confidence: float
    data_points: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    risks: List[str]
    sources: List[str]
    timestamp: datetime
    follow_up_questions: List[str]


@dataclass
class ScreeningCriteria:
    """Criteria for stock screening"""
    min_market_cap: Optional[float] = None
    max_market_cap: Optional[float] = None
    min_pe: Optional[float] = None
    max_pe: Optional[float] = None
    min_revenue_growth: Optional[float] = None
    min_roe: Optional[float] = None
    sectors: Optional[List[str]] = None
    exclude_sectors: Optional[List[str]] = None
    min_dividend_yield: Optional[float] = None
    max_debt_to_equity: Optional[float] = None
    min_profit_margin: Optional[float] = None


class ResearchMode(str, Enum):
    """Different research modes"""
    QUICK_ANSWER = "quick"          # Fast response with cached data
    COMPREHENSIVE = "comprehensive"  # Full analysis with all sources
    REAL_TIME = "real_time"         # Priority on latest data
    HISTORICAL = "historical"       # Focus on historical patterns
    COMPARATIVE = "comparative"     # Compare multiple options


class AIResearchAgent:
    """
    Advanced AI Research Agent that can answer complex investment questions
    by orchestrating multiple data sources and analysis tools.
    """

    def __init__(self,
                 openai_api_key: str,
                 perplexity_connector: Optional[PerplexityFinanceConnector] = None,
                 db_manager: Optional[DatabaseManager] = None,
                 cache: Optional[RedisCache] = None):
        """
        Initialize the AI Research Agent.

        Args:
            openai_api_key: OpenAI API key for LLM
            perplexity_connector: Perplexity Finance connector
            db_manager: Database manager
            cache: Redis cache
        """
        self.llm = ChatOpenAI(
            temperature=0.3,
            model="gpt-4o-mini",
            openai_api_key=openai_api_key
        )

        self.perplexity = perplexity_connector or PerplexityFinanceConnector()
        self.db = db_manager
        self.cache = cache
        self.data_aggregator = DataAggregator()
        self.signal_processor = SignalProcessor()
        self.risk_manager = RiskManager()

        # Setup conversation memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        # Create research tools
        self.tools = self._create_research_tools()

        # Setup the agent
        self.agent = self._setup_agent()

    def _create_research_tools(self) -> List[Tool]:
        """Create tools for the research agent"""

        tools = [
            Tool(
                name="analyze_stock_fundamental",
                func=self._tool_analyze_fundamental,
                description="Analyze fundamental data for a specific stock. Input: ticker symbol"
            ),
            Tool(
                name="screen_undervalued_stocks",
                func=self._tool_screen_undervalued,
                description="Find undervalued stocks based on criteria. Input: JSON criteria"
            ),
            Tool(
                name="compare_stocks",
                func=self._tool_compare_stocks,
                description="Compare multiple stocks. Input: comma-separated tickers"
            ),
            Tool(
                name="analyze_sector",
                func=self._tool_analyze_sector,
                description="Analyze a specific sector. Input: sector name"
            ),
            Tool(
                name="get_market_sentiment",
                func=self._tool_get_sentiment,
                description="Get current market sentiment. Input: 'overall' or sector name"
            ),
            Tool(
                name="analyze_portfolio_gaps",
                func=self._tool_analyze_portfolio_gaps,
                description="Identify gaps in current portfolio. Input: 'analyze'"
            ),
            Tool(
                name="find_growth_stocks",
                func=self._tool_find_growth,
                description="Find high-growth stocks. Input: JSON with criteria"
            ),
            Tool(
                name="analyze_risk_reward",
                func=self._tool_analyze_risk_reward,
                description="Analyze risk-reward for a stock. Input: ticker symbol"
            ),
            Tool(
                name="get_earnings_calendar",
                func=self._tool_get_earnings,
                description="Get upcoming earnings. Input: number of days ahead"
            ),
            Tool(
                name="analyze_insider_trading",
                func=self._tool_analyze_insider,
                description="Analyze insider trading activity. Input: ticker symbol"
            ),
            Tool(
                name="technical_analysis",
                func=self._tool_technical_analysis,
                description="Perform technical analysis. Input: ticker symbol"
            ),
            Tool(
                name="find_dividend_stocks",
                func=self._tool_find_dividends,
                description="Find high-quality dividend stocks. Input: minimum yield"
            ),
            Tool(
                name="analyze_congressional_trades",
                func=self._tool_congressional_trades,
                description="Analyze congressional trading activity. Input: days back"
            ),
            Tool(
                name="portfolio_optimization",
                func=self._tool_optimize_portfolio,
                description="Suggest portfolio optimizations. Input: risk tolerance (low/medium/high)"
            ),
            Tool(
                name="macroeconomic_analysis",
                func=self._tool_macro_analysis,
                description="Analyze macroeconomic factors. Input: 'current'"
            )
        ]

        return tools

    async def research(self,
                      query: ResearchQuery,
                      mode: ResearchMode = ResearchMode.COMPREHENSIVE) -> ResearchResponse:
        """
        Execute a research query and return comprehensive response.

        Args:
            query: Research query object
            mode: Research mode determining depth and speed

        Returns:
            ResearchResponse with answer and supporting data
        """
        logger.info(f"Processing research query: {query.question[:100]}...")

        # Check cache for recent similar queries
        if self.cache and mode == ResearchMode.QUICK_ANSWER:
            cache_key = f"research:{hash(query.question)}"
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info("Returning cached research response")
                return ResearchResponse(**cached)

        # Prepare context
        context = await self._prepare_context(query)

        # Execute agent with query
        try:
            result = await self.agent.ainvoke({
                "input": query.question,
                "context": json.dumps(context),
                "mode": mode.value
            })

            # Parse and structure response
            response = await self._structure_response(query.question, result, context)

            # Cache if appropriate
            if self.cache and mode != ResearchMode.REAL_TIME:
                await self.cache.set(
                    f"research:{hash(query.question)}",
                    response.dict(),
                    ttl=1800  # 30 minutes
                )

            return response

        except Exception as e:
            logger.error(f"Research error: {e}")
            return ResearchResponse(
                query=query.question,
                answer=f"Unable to complete research: {str(e)}",
                confidence=0.0,
                data_points=[],
                recommendations=[],
                risks=["Research process encountered an error"],
                sources=[],
                timestamp=datetime.now(),
                follow_up_questions=[]
            )

    async def screen_stocks(self,
                          natural_language_query: str,
                          criteria: Optional[ScreeningCriteria] = None) -> List[Dict[str, Any]]:
        """
        Screen stocks based on natural language query and criteria.

        Args:
            natural_language_query: Natural language screening request
            criteria: Optional structured screening criteria

        Returns:
            List of stocks matching criteria with analysis
        """
        # Use Perplexity for natural language screening
        screening_result = await self.perplexity.screen_stocks(
            natural_language_query,
            max_results=20,
            filters=criteria.__dict__ if criteria else None
        )

        # Enhance with our own analysis
        enhanced_results = []
        for stock in screening_result.stocks[:10]:  # Top 10
            ticker = stock.get('ticker')
            if ticker:
                # Get additional metrics
                analysis = await self.perplexity.analyze_stock(
                    ticker,
                    AnalysisType.VALUATION,
                    ResearchDepth.QUICK
                )

                # Get AI signal
                signal = await self.signal_processor.process_signal(ticker)

                enhanced_results.append({
                    "ticker": ticker,
                    "company": stock.get('company_name', ''),
                    "current_price": stock.get('price', 0),
                    "market_cap": stock.get('market_cap', 0),
                    "pe_ratio": analysis.pe_ratio,
                    "fair_value": analysis.fair_value,
                    "upside_potential": analysis.upside_potential,
                    "ai_signal": signal.signal if signal else "HOLD",
                    "ai_confidence": signal.confidence if signal else 0,
                    "match_reason": stock.get('match_reason', ''),
                    "risk_level": self._calculate_risk_level(analysis)
                })

        return enhanced_results

    async def answer_question(self, question: str) -> str:
        """
        Simple interface to answer investment questions.

        Args:
            question: Natural language question

        Returns:
            Text answer
        """
        query = ResearchQuery(
            question=question,
            depth="standard",
            include_portfolio=True
        )

        response = await self.research(query, mode=ResearchMode.COMPREHENSIVE)
        return response.answer

    async def find_opportunities(self,
                                investment_amount: float,
                                risk_tolerance: str = "medium",
                                time_horizon: str = "medium") -> Dict[str, Any]:
        """
        Find investment opportunities based on parameters.

        Args:
            investment_amount: Amount to invest
            risk_tolerance: low, medium, high
            time_horizon: short, medium, long

        Returns:
            Investment opportunities with allocation suggestions
        """
        # Build research query
        query = f"""
        Find the best investment opportunities for:
        - Investment amount: ${investment_amount:,.0f}
        - Risk tolerance: {risk_tolerance}
        - Time horizon: {time_horizon}

        Consider:
        1. Undervalued stocks with strong fundamentals
        2. Growth stocks with momentum
        3. Dividend stocks for income
        4. Sector diversification
        5. Current market conditions

        Provide specific stock recommendations with allocation percentages.
        """

        research_query = ResearchQuery(
            question=query,
            depth="deep",
            context={
                "investment_amount": investment_amount,
                "risk_tolerance": risk_tolerance,
                "time_horizon": time_horizon
            }
        )

        response = await self.research(research_query, mode=ResearchMode.COMPREHENSIVE)

        # Structure opportunities
        opportunities = {
            "investment_amount": investment_amount,
            "risk_profile": risk_tolerance,
            "time_horizon": time_horizon,
            "market_conditions": await self._get_market_conditions(),
            "recommendations": response.recommendations,
            "allocation_strategy": self._create_allocation_strategy(
                response.recommendations,
                investment_amount,
                risk_tolerance
            ),
            "expected_returns": self._estimate_returns(
                response.recommendations,
                time_horizon
            ),
            "key_risks": response.risks,
            "execution_plan": self._create_execution_plan(response.recommendations)
        }

        return opportunities

    # Tool implementation methods
    async def _tool_analyze_fundamental(self, ticker: str) -> str:
        """Tool: Analyze fundamental data"""
        analysis = await self.perplexity.analyze_stock(
            ticker,
            AnalysisType.FUNDAMENTAL,
            ResearchDepth.STANDARD
        )

        return f"""
        Fundamental Analysis for {ticker}:
        - Current Price: ${analysis.current_price}
        - Fair Value: ${analysis.fair_value}
        - Upside Potential: {analysis.upside_potential}%
        - P/E Ratio: {analysis.pe_ratio}
        - Rating: {analysis.rating}
        - Confidence: {analysis.confidence_score}%

        Bull Case: {analysis.bull_case}
        Bear Case: {analysis.bear_case}
        Key Risks: {', '.join(analysis.key_risks[:3])}
        """

    async def _tool_screen_undervalued(self, criteria_json: str) -> str:
        """Tool: Screen for undervalued stocks"""
        try:
            criteria = json.loads(criteria_json) if criteria_json else {}
        except:
            criteria = {}

        query = "Find undervalued stocks with strong fundamentals"
        if criteria:
            query += f" with criteria: {criteria}"

        result = await self.perplexity.screen_stocks(query, max_results=10)

        stocks_summary = []
        for stock in result.stocks[:5]:
            stocks_summary.append(
                f"- {stock.get('ticker')}: "
                f"${stock.get('price', 'N/A')}, "
                f"P/E: {stock.get('pe_ratio', 'N/A')}"
            )

        return f"""
        Undervalued Stocks Found:
        {chr(10).join(stocks_summary)}

        Screening Criteria: {query}
        Total Results: {result.total_results}
        """

    async def _tool_compare_stocks(self, tickers: str) -> str:
        """Tool: Compare multiple stocks"""
        ticker_list = [t.strip() for t in tickers.split(',')]

        comparisons = []
        for ticker in ticker_list[:3]:  # Limit to 3 for brevity
            analysis = await self.perplexity.analyze_stock(
                ticker,
                AnalysisType.VALUATION,
                ResearchDepth.QUICK
            )
            comparisons.append({
                "ticker": ticker,
                "price": analysis.current_price,
                "fair_value": analysis.fair_value,
                "pe_ratio": analysis.pe_ratio,
                "rating": analysis.rating
            })

        comparison_text = []
        for comp in comparisons:
            comparison_text.append(
                f"{comp['ticker']}: "
                f"Price ${comp['price']}, "
                f"Fair Value ${comp['fair_value']}, "
                f"P/E {comp['pe_ratio']}, "
                f"Rating: {comp['rating']}"
            )

        return f"""
        Stock Comparison:
        {chr(10).join(comparison_text)}
        """

    async def _tool_analyze_sector(self, sector: str) -> str:
        """Tool: Analyze sector performance"""
        sentiment = await self.perplexity.get_market_sentiment(sector)

        return f"""
        Sector Analysis for {sector}:
        {sentiment['analysis'][:500]}
        """

    async def _tool_get_sentiment(self, target: str) -> str:
        """Tool: Get market sentiment"""
        sector = None if target == 'overall' else target
        sentiment = await self.perplexity.get_market_sentiment(sector)

        return f"""
        Market Sentiment ({target}):
        {sentiment['analysis'][:500]}
        """

    async def _tool_analyze_portfolio_gaps(self, command: str) -> str:
        """Tool: Analyze portfolio gaps"""
        if not self.db:
            return "Portfolio analysis unavailable - no database connection"

        # Get current positions
        positions = await self.db.get_active_positions()

        # Analyze sector distribution
        sectors = {}
        for pos in positions:
            sector = await self._get_stock_sector(pos.ticker)
            sectors[sector] = sectors.get(sector, 0) + pos.market_value

        gaps = []
        if 'Technology' not in sectors:
            gaps.append("No technology exposure")
        if 'Healthcare' not in sectors:
            gaps.append("No healthcare exposure")
        if 'Consumer' not in sectors:
            gaps.append("No consumer exposure")

        return f"""
        Portfolio Analysis:
        Current Sectors: {', '.join(sectors.keys())}
        Identified Gaps: {', '.join(gaps) if gaps else 'Well-diversified'}
        Recommendation: Consider adding exposure to missing sectors
        """

    async def _tool_find_growth(self, criteria_json: str) -> str:
        """Tool: Find growth stocks"""
        query = "Find high-growth stocks with strong revenue and earnings growth"
        result = await self.perplexity.screen_stocks(query, max_results=10)

        stocks = []
        for stock in result.stocks[:5]:
            stocks.append(f"- {stock.get('ticker')}: {stock.get('company_name', 'N/A')}")

        return f"""
        High-Growth Stocks:
        {chr(10).join(stocks)}
        """

    async def _tool_analyze_risk_reward(self, ticker: str) -> str:
        """Tool: Analyze risk-reward profile"""
        analysis = await self.perplexity.analyze_stock(
            ticker,
            AnalysisType.FUNDAMENTAL,
            ResearchDepth.STANDARD
        )

        risk_level = self._calculate_risk_level(analysis)
        reward_potential = analysis.upside_potential or 0

        return f"""
        Risk-Reward Analysis for {ticker}:
        - Risk Level: {risk_level}
        - Reward Potential: {reward_potential}%
        - Risk/Reward Ratio: {abs(reward_potential/10):.2f}
        - Key Risks: {', '.join(analysis.key_risks[:3])}
        - Catalysts: {', '.join(analysis.catalysts[:3])}
        """

    async def _tool_get_earnings(self, days_ahead: str) -> str:
        """Tool: Get earnings calendar"""
        try:
            days = int(days_ahead)
        except:
            days = 7

        # This would normally query earnings calendar API
        return f"""
        Upcoming Earnings (Next {days} days):
        - Check market calendars for detailed earnings dates
        - Major companies reporting soon
        """

    async def _tool_analyze_insider(self, ticker: str) -> str:
        """Tool: Analyze insider trading"""
        insider_data = await self.perplexity.analyze_insider_activity(ticker, days_back=90)

        return f"""
        Insider Trading Analysis for {ticker}:
        {insider_data['analysis'][:500]}
        """

    async def _tool_technical_analysis(self, ticker: str) -> str:
        """Tool: Technical analysis"""
        analysis = await self.perplexity.analyze_stock(
            ticker,
            AnalysisType.TECHNICAL,
            ResearchDepth.STANDARD
        )

        return f"""
        Technical Analysis for {ticker}:
        - Current Price: ${analysis.current_price}
        - Rating: {analysis.rating}
        - Time Horizon: {analysis.time_horizon}

        {analysis.detailed_analysis[:300]}
        """

    async def _tool_find_dividends(self, min_yield: str) -> str:
        """Tool: Find dividend stocks"""
        try:
            yield_threshold = float(min_yield)
        except:
            yield_threshold = 3.0

        query = f"Find dividend stocks with yield above {yield_threshold}% and stable payouts"
        result = await self.perplexity.screen_stocks(query, max_results=10)

        stocks = []
        for stock in result.stocks[:5]:
            stocks.append(f"- {stock.get('ticker')}: {stock.get('company_name', 'N/A')}")

        return f"""
        Dividend Stocks (>{yield_threshold}% yield):
        {chr(10).join(stocks)}
        """

    async def _tool_congressional_trades(self, days_back: str) -> str:
        """Tool: Analyze congressional trades"""
        try:
            days = int(days_back)
        except:
            days = 30

        trades = await self.data_aggregator.fetch_congressional_trades(
            tickers=[],  # All tickers
            days_back=days
        )

        summary = []
        for trade in trades[:5]:
            summary.append(
                f"- {trade['politician']}: "
                f"{trade['action']} {trade['ticker']} "
                f"(${trade.get('amount', 'N/A')})"
            )

        return f"""
        Recent Congressional Trades ({days} days):
        {chr(10).join(summary) if summary else 'No significant trades'}
        """

    async def _tool_optimize_portfolio(self, risk_tolerance: str) -> str:
        """Tool: Portfolio optimization suggestions"""
        if not self.db:
            return "Portfolio optimization unavailable"

        positions = await self.db.get_active_positions()

        suggestions = []
        if risk_tolerance == "low":
            suggestions.append("Increase allocation to dividend stocks and bonds")
            suggestions.append("Reduce exposure to high-volatility growth stocks")
        elif risk_tolerance == "high":
            suggestions.append("Consider adding more growth stocks")
            suggestions.append("Look at emerging markets exposure")

        return f"""
        Portfolio Optimization ({risk_tolerance} risk):
        Current Positions: {len(positions)}
        Suggestions:
        {chr(10).join(f'- {s}' for s in suggestions)}
        """

    async def _tool_macro_analysis(self, timeframe: str) -> str:
        """Tool: Macroeconomic analysis"""
        analysis = await self.perplexity.get_market_sentiment()

        return f"""
        Macroeconomic Analysis:
        {analysis['analysis'][:500]}
        """

    # Helper methods
    async def _prepare_context(self, query: ResearchQuery) -> Dict[str, Any]:
        """Prepare context for research query"""
        context = {
            "timestamp": datetime.now().isoformat(),
            "depth": query.depth
        }

        # Add portfolio context if requested
        if query.include_portfolio and self.db:
            positions = await self.db.get_active_positions()
            context["portfolio"] = [
                {"ticker": p.ticker, "shares": p.quantity, "value": p.market_value}
                for p in positions
            ]

        # Add market context
        market_sentiment = await self.perplexity.get_market_sentiment()
        context["market_conditions"] = market_sentiment['analysis'][:200]

        # Add any user-provided context
        if query.context:
            context.update(query.context)

        return context

    async def _structure_response(self,
                                 question: str,
                                 agent_result: Dict,
                                 context: Dict) -> ResearchResponse:
        """Structure agent response into ResearchResponse object"""

        # Extract answer
        answer = agent_result.get('output', '')

        # Generate follow-up questions
        follow_ups = self._generate_follow_up_questions(question, answer)

        # Extract recommendations and risks
        recommendations = self._extract_recommendations(answer)
        risks = self._extract_risks(answer)

        return ResearchResponse(
            query=question,
            answer=answer,
            confidence=0.85,  # Would calculate based on data quality
            data_points=[],
            recommendations=recommendations,
            risks=risks,
            sources=["Perplexity AI", "Market Data", "Portfolio Analysis"],
            timestamp=datetime.now(),
            follow_up_questions=follow_ups
        )

    def _calculate_risk_level(self, analysis) -> str:
        """Calculate risk level from analysis"""
        if not analysis.pe_ratio:
            return "Unknown"

        if analysis.pe_ratio > 30:
            return "High"
        elif analysis.pe_ratio > 20:
            return "Medium"
        else:
            return "Low"

    async def _get_stock_sector(self, ticker: str) -> str:
        """Get sector for a stock"""
        # This would query a sector database/API
        # Simplified for example
        tech_stocks = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META']
        if ticker in tech_stocks:
            return "Technology"
        return "Other"

    async def _get_market_conditions(self) -> Dict[str, Any]:
        """Get current market conditions"""
        sentiment = await self.perplexity.get_market_sentiment()

        return {
            "sentiment": "Bullish" if "bull" in sentiment['analysis'].lower() else "Bearish",
            "volatility": "Moderate",  # Would calculate from VIX
            "trend": "Upward",  # Would determine from market data
            "key_factors": sentiment['analysis'][:200]
        }

    def _create_allocation_strategy(self,
                                   recommendations: List[Dict],
                                   amount: float,
                                   risk_tolerance: str) -> Dict[str, float]:
        """Create allocation strategy"""
        strategy = {}

        # Simple allocation based on risk tolerance
        if risk_tolerance == "low":
            # Conservative allocation
            allocation_pcts = [0.3, 0.25, 0.20, 0.15, 0.10]
        elif risk_tolerance == "high":
            # Aggressive allocation
            allocation_pcts = [0.35, 0.30, 0.20, 0.15]
        else:
            # Balanced allocation
            allocation_pcts = [0.25, 0.25, 0.20, 0.15, 0.15]

        for i, rec in enumerate(recommendations[:len(allocation_pcts)]):
            if 'ticker' in rec:
                strategy[rec['ticker']] = amount * allocation_pcts[i]

        return strategy

    def _estimate_returns(self,
                         recommendations: List[Dict],
                         time_horizon: str) -> Dict[str, float]:
        """Estimate potential returns"""
        # Simple estimation based on time horizon
        if time_horizon == "short":
            return {"expected": 5.0, "best_case": 15.0, "worst_case": -10.0}
        elif time_horizon == "long":
            return {"expected": 12.0, "best_case": 25.0, "worst_case": -5.0}
        else:
            return {"expected": 8.0, "best_case": 20.0, "worst_case": -8.0}

    def _create_execution_plan(self, recommendations: List[Dict]) -> List[str]:
        """Create execution plan for recommendations"""
        plan = []

        for i, rec in enumerate(recommendations[:5], 1):
            if 'ticker' in rec:
                plan.append(
                    f"{i}. Research {rec['ticker']} further"
                )
                plan.append(
                    f"   - Set limit order at recommended price"
                )
                plan.append(
                    f"   - Monitor for entry point"
                )

        return plan

    def _extract_recommendations(self, text: str) -> List[Dict[str, Any]]:
        """Extract recommendations from text"""
        # This would use NLP to extract structured recommendations
        # Simplified for example
        recommendations = []

        if "buy" in text.lower():
            recommendations.append({
                "action": "BUY",
                "confidence": 0.8,
                "reasoning": "Extracted from analysis"
            })

        return recommendations

    def _extract_risks(self, text: str) -> List[str]:
        """Extract risks from text"""
        risks = []

        risk_keywords = ['risk', 'concern', 'threat', 'weakness']
        for keyword in risk_keywords:
            if keyword in text.lower():
                risks.append(f"Potential {keyword} identified in analysis")

        return risks[:5]

    def _generate_follow_up_questions(self, question: str, answer: str) -> List[str]:
        """Generate relevant follow-up questions"""
        follow_ups = []

        if "undervalued" in question.lower():
            follow_ups.append("What are the key risks for these undervalued stocks?")
            follow_ups.append("How do these compare to the S&P 500 valuation?")

        if "invest" in question.lower():
            follow_ups.append("What is the optimal position size for my portfolio?")
            follow_ups.append("When would be the best entry point?")

        if "sector" in answer.lower():
            follow_ups.append("Which sectors are currently outperforming?")

        return follow_ups[:3]

    def _setup_agent(self) -> AgentExecutor:
        """Setup the LangChain agent"""

        # Create prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert investment research analyst with access to real-time market data and analysis tools.

Your goal is to provide comprehensive, actionable investment research based on:
1. Current market conditions
2. Fundamental and technical analysis
3. Risk assessment
4. Portfolio considerations

Be specific with numbers, percentages, and tickers. Always cite your data sources.
Consider the user's risk tolerance and investment timeline.

Context: {context}
Mode: {mode}"""),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create agent
        agent = (
            {
                "input": lambda x: x["input"],
                "context": lambda x: x.get("context", ""),
                "mode": lambda x: x.get("mode", "comprehensive"),
                "chat_history": lambda x: self.memory.chat_memory.messages,
                "agent_scratchpad": lambda x: format_to_openai_function_messages(
                    x["intermediate_steps"]
                ),
            }
            | prompt
            | self.llm.bind(functions=[t.as_tool() for t in self.tools])
            | OpenAIFunctionsAgentOutputParser()
        )

        # Create executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            return_intermediate_steps=True,
            max_iterations=10,
            handle_parsing_errors=True
        )

        return agent_executor