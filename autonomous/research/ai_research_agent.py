"""
AI Research Agent - FIXED VERSION
Conversational interface for complex investment research with proper async handling.
"""

import asyncio
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import logging
from decimal import Decimal

from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool, StructuredTool
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage, HumanMessage
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class ResearchQuery(BaseModel):
    """Structure for research queries"""
    question: str = Field(..., description="The investment research question")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")
    depth: str = Field(default="standard", description="Depth of analysis: quick, standard, deep")
    include_portfolio: bool = Field(default=True, description="Consider current portfolio")
    time_horizon: Optional[str] = Field(default=None, description="Investment time horizon")

    @validator('question')
    def sanitize_question(cls, v):
        # Sanitize input to prevent injection
        if len(v) > 1000:
            v = v[:1000]
        # Remove potential injection patterns
        v = re.sub(r'[<>{}]', '', v)
        return v


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
    QUICK_ANSWER = "quick"
    COMPREHENSIVE = "comprehensive"
    REAL_TIME = "real_time"
    HISTORICAL = "historical"
    COMPARATIVE = "comparative"


class AIResearchAgent:
    """
    Fixed AI Research Agent with proper async handling and error management.
    """

    def __init__(self,
                 openai_api_key: str,
                 perplexity_connector=None,
                 db_manager=None,
                 cache=None,
                 config: Optional[Dict] = None):
        """
        Initialize the AI Research Agent.

        Args:
            openai_api_key: OpenAI API key for LLM
            perplexity_connector: Perplexity Finance connector (optional)
            db_manager: Database manager (optional)
            cache: Redis cache (optional)
            config: Additional configuration
        """
        if not openai_api_key:
            raise ValueError("OpenAI API key is required")

        self.llm = ChatOpenAI(
            temperature=0.3,
            model="gpt-4o-mini",
            openai_api_key=openai_api_key
        )

        self.perplexity = perplexity_connector
        self.db = db_manager
        self.cache = cache
        self.config = config or {}

        # Initialize other components with proper dependencies
        self.data_aggregator = None
        self.signal_processor = None
        self.risk_manager = None

        # Only initialize if we have required dependencies
        try:
            if config:
                from autonomous.data_aggregator import DataAggregator
                self.data_aggregator = DataAggregator(config)
        except ImportError as e:
            logger.warning(f"Could not initialize DataAggregator: {e}")

        # Setup conversation memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        # Create research tools (synchronous versions for LangChain)
        self.tools = self._create_research_tools()

        # Setup the agent
        self.agent_executor = self._setup_agent()

    def _create_research_tools(self) -> List[Tool]:
        """Create synchronous tool wrappers for LangChain"""

        # Create synchronous wrappers for async methods
        def sync_wrapper(async_func):
            """Wrapper to make async functions sync for LangChain"""
            def wrapper(*args, **kwargs):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're already in an async context
                        # Create a new task and wait for it
                        future = asyncio.ensure_future(async_func(*args, **kwargs))
                        return asyncio.run_coroutine_threadsafe(
                            async_func(*args, **kwargs),
                            loop
                        ).result()
                    else:
                        # No event loop running, create one
                        return asyncio.run(async_func(*args, **kwargs))
                except Exception as e:
                    logger.error(f"Tool execution error: {e}")
                    return f"Error: {str(e)}"
            return wrapper

        tools = [
            Tool(
                name="analyze_stock_fundamental",
                func=sync_wrapper(self._tool_analyze_fundamental),
                description="Analyze fundamental data for a specific stock. Input: ticker symbol"
            ),
            Tool(
                name="screen_undervalued_stocks",
                func=sync_wrapper(self._tool_screen_undervalued),
                description="Find undervalued stocks based on criteria. Input: JSON criteria or 'default'"
            ),
            Tool(
                name="compare_stocks",
                func=sync_wrapper(self._tool_compare_stocks),
                description="Compare multiple stocks. Input: comma-separated tickers"
            ),
            Tool(
                name="analyze_sector",
                func=sync_wrapper(self._tool_analyze_sector),
                description="Analyze a specific sector. Input: sector name"
            ),
            Tool(
                name="get_market_sentiment",
                func=sync_wrapper(self._tool_get_sentiment),
                description="Get current market sentiment. Input: 'overall' or sector name"
            ),
            Tool(
                name="analyze_portfolio_gaps",
                func=sync_wrapper(self._tool_analyze_portfolio_gaps),
                description="Identify gaps in current portfolio. Input: 'analyze'"
            ),
            Tool(
                name="find_growth_stocks",
                func=sync_wrapper(self._tool_find_growth),
                description="Find high-growth stocks. Input: 'default' or JSON criteria"
            ),
            Tool(
                name="analyze_risk_reward",
                func=sync_wrapper(self._tool_analyze_risk_reward),
                description="Analyze risk-reward for a stock. Input: ticker symbol"
            ),
        ]

        return tools

    async def research(self,
                      query: ResearchQuery,
                      mode: ResearchMode = ResearchMode.COMPREHENSIVE) -> ResearchResponse:
        """
        Execute a research query and return comprehensive response.
        """
        logger.info(f"Processing research query: {query.question[:100]}...")

        # Check cache for recent similar queries
        cache_key = None
        if self.cache and mode == ResearchMode.QUICK_ANSWER:
            cache_key = f"research:{hash(query.question) % 1000000}"
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    logger.info("Returning cached research response")
                    # Reconstruct ResearchResponse
                    cached['timestamp'] = datetime.fromisoformat(cached['timestamp'])
                    return ResearchResponse(**cached)
            except Exception as e:
                logger.warning(f"Cache retrieval error: {e}")

        # Prepare context
        context = await self._prepare_context(query)

        # Execute agent with query
        try:
            # Run synchronously since LangChain agent is sync
            result = self.agent_executor.invoke({
                "input": query.question,
                "context": json.dumps(context),
                "mode": mode.value,
                "chat_history": []
            })

            # Parse and structure response
            response = await self._structure_response(query.question, result, context)

            # Cache if appropriate
            if self.cache and cache_key and mode != ResearchMode.REAL_TIME:
                try:
                    cache_data = response.dict()
                    cache_data['timestamp'] = cache_data['timestamp'].isoformat()
                    await self.cache.set(cache_key, cache_data, ttl=1800)  # 30 minutes
                except Exception as e:
                    logger.warning(f"Cache storage error: {e}")

            return response

        except Exception as e:
            logger.error(f"Research error: {e}")
            return ResearchResponse(
                query=query.question,
                answer=f"I encountered an error while researching: {str(e)[:200]}",
                confidence=0.0,
                data_points=[],
                recommendations=[],
                risks=["Research process encountered an error"],
                sources=[],
                timestamp=datetime.now(timezone.utc),
                follow_up_questions=[]
            )

    async def screen_stocks(self,
                          natural_language_query: str,
                          criteria: Optional[ScreeningCriteria] = None) -> List[Dict[str, Any]]:
        """
        Screen stocks based on natural language query and criteria.
        """
        if not self.perplexity:
            logger.warning("Perplexity connector not available for screening")
            return []

        try:
            # Use fixed Perplexity connector
            from autonomous.connectors.perplexity_finance_fixed import ResearchDepth

            screening_result = await self.perplexity.screen_stocks(
                natural_language_query,
                max_results=20,
                filters=criteria.__dict__ if criteria else None
            )

            enhanced_results = []
            for stock in screening_result.stocks[:10]:
                ticker = stock.get('ticker')
                if ticker:
                    enhanced_results.append({
                        "ticker": ticker,
                        "company": stock.get('company_name', ''),
                        "current_price": stock.get('price', 0),
                        "market_cap": stock.get('market_cap', 0),
                        "pe_ratio": stock.get('pe_ratio'),
                        "match_reason": stock.get('match_reason', ''),
                        "risk_level": "Medium"  # Default
                    })

            return enhanced_results

        except Exception as e:
            logger.error(f"Stock screening error: {e}")
            return []

    async def answer_question(self, question: str) -> str:
        """
        Simple interface to answer investment questions.
        """
        query = ResearchQuery(
            question=question,
            depth="standard",
            include_portfolio=False  # Don't include portfolio by default
        )

        response = await self.research(query, mode=ResearchMode.COMPREHENSIVE)
        return response.answer

    # Tool implementation methods (async versions)
    async def _tool_analyze_fundamental(self, ticker: str) -> str:
        """Tool: Analyze fundamental data"""
        if not self.perplexity:
            return "Perplexity connector not available for analysis"

        try:
            from autonomous.connectors.perplexity_finance_fixed import AnalysisType, ResearchDepth

            analysis = await self.perplexity.analyze_stock(
                ticker,
                AnalysisType.FUNDAMENTAL,
                ResearchDepth.STANDARD
            )

            return f"""
Fundamental Analysis for {ticker}:
- Current Price: ${analysis.current_price:.2f}
- Fair Value: ${analysis.fair_value:.2f if analysis.fair_value else 'N/A'}
- Upside Potential: {analysis.upside_potential:.1f}% if analysis.upside_potential else 'N/A'
- P/E Ratio: {analysis.pe_ratio if analysis.pe_ratio else 'N/A'}
- Rating: {analysis.rating}
- Confidence: {analysis.confidence_score}%

Bull Case: {analysis.bull_case[:200] if analysis.bull_case else 'N/A'}
Key Risks: {', '.join(analysis.key_risks[:3]) if analysis.key_risks else 'N/A'}
"""
        except Exception as e:
            logger.error(f"Fundamental analysis error: {e}")
            return f"Error analyzing {ticker}: {str(e)[:100]}"

    async def _tool_screen_undervalued(self, criteria_input: str) -> str:
        """Tool: Screen for undervalued stocks"""
        if not self.perplexity:
            return "Screening not available without Perplexity connector"

        try:
            # Parse criteria if JSON provided
            criteria = {}
            if criteria_input and criteria_input != 'default':
                try:
                    criteria = json.loads(criteria_input)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON criteria: {criteria_input}")

            query = "Find undervalued stocks with strong fundamentals"
            if criteria:
                query += f" with criteria: {criteria}"

            result = await self.perplexity.screen_stocks(query, max_results=10)

            if not result.stocks:
                return "No undervalued stocks found matching criteria"

            stocks_summary = []
            for stock in result.stocks[:5]:
                stocks_summary.append(
                    f"- {stock.get('ticker', 'N/A')}: "
                    f"${stock.get('price', 'N/A')}"
                )

            return f"""
Undervalued Stocks Found:
{chr(10).join(stocks_summary)}

Total Results: {result.total_results}
"""
        except Exception as e:
            logger.error(f"Screening error: {e}")
            return f"Screening error: {str(e)[:100]}"

    async def _tool_compare_stocks(self, tickers: str) -> str:
        """Tool: Compare multiple stocks"""
        if not self.perplexity:
            return "Stock comparison not available"

        try:
            ticker_list = [t.strip().upper() for t in tickers.split(',')]
            if len(ticker_list) > 5:
                ticker_list = ticker_list[:5]  # Limit to 5

            from autonomous.connectors.perplexity_finance_fixed import AnalysisType, ResearchDepth

            comparisons = []
            for ticker in ticker_list:
                try:
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
                except Exception as e:
                    logger.warning(f"Could not analyze {ticker}: {e}")

            comparison_text = []
            for comp in comparisons:
                comparison_text.append(
                    f"{comp['ticker']}: "
                    f"Price ${comp['price']:.2f}, "
                    f"Fair Value ${comp['fair_value']:.2f if comp['fair_value'] else 'N/A'}, "
                    f"P/E {comp['pe_ratio'] if comp['pe_ratio'] else 'N/A'}, "
                    f"Rating: {comp['rating']}"
                )

            return f"""
Stock Comparison:
{chr(10).join(comparison_text)}
"""
        except Exception as e:
            logger.error(f"Comparison error: {e}")
            return f"Comparison error: {str(e)[:100]}"

    async def _tool_analyze_sector(self, sector: str) -> str:
        """Tool: Analyze sector performance"""
        if not self.perplexity:
            return "Sector analysis not available"

        try:
            sentiment = await self.perplexity.get_market_sentiment(sector)
            return f"""
Sector Analysis for {sector}:
{sentiment.get('analysis', 'No analysis available')[:500]}
"""
        except Exception as e:
            return f"Sector analysis error: {str(e)[:100]}"

    async def _tool_get_sentiment(self, target: str) -> str:
        """Tool: Get market sentiment"""
        if not self.perplexity:
            return "Sentiment analysis not available"

        try:
            sector = None if target.lower() == 'overall' else target
            sentiment = await self.perplexity.get_market_sentiment(sector)
            return f"""
Market Sentiment ({target}):
{sentiment.get('analysis', 'No analysis available')[:500]}
"""
        except Exception as e:
            return f"Sentiment analysis error: {str(e)[:100]}"

    async def _tool_analyze_portfolio_gaps(self, command: str) -> str:
        """Tool: Analyze portfolio gaps"""
        if not self.db:
            return "Portfolio analysis unavailable - no database connection"

        try:
            # Note: DatabaseManager methods are synchronous
            positions = self.db.get_active_positions()

            if not positions:
                return "No active positions found in portfolio"

            # Analyze sector distribution
            sectors = {}
            for pos in positions:
                # Simplified sector mapping
                sector = "Technology"  # Would need actual sector lookup
                sectors[sector] = sectors.get(sector, 0) + 1

            gaps = []
            common_sectors = ['Technology', 'Healthcare', 'Finance', 'Consumer', 'Energy']
            for sector in common_sectors:
                if sector not in sectors:
                    gaps.append(f"No {sector} exposure")

            return f"""
Portfolio Analysis:
Current Positions: {len(positions)}
Sectors: {', '.join(sectors.keys())}
Identified Gaps: {', '.join(gaps) if gaps else 'Well-diversified'}
"""
        except Exception as e:
            logger.error(f"Portfolio analysis error: {e}")
            return f"Portfolio analysis error: {str(e)[:100]}"

    async def _tool_find_growth(self, criteria_input: str) -> str:
        """Tool: Find growth stocks"""
        if not self.perplexity:
            return "Growth stock search not available"

        try:
            query = "Find high-growth stocks with strong revenue and earnings growth"
            result = await self.perplexity.screen_stocks(query, max_results=10)

            if not result.stocks:
                return "No growth stocks found"

            stocks = []
            for stock in result.stocks[:5]:
                stocks.append(f"- {stock.get('ticker', 'N/A')}: {stock.get('company_name', 'N/A')}")

            return f"""
High-Growth Stocks:
{chr(10).join(stocks)}
"""
        except Exception as e:
            return f"Growth stock search error: {str(e)[:100]}"

    async def _tool_analyze_risk_reward(self, ticker: str) -> str:
        """Tool: Analyze risk-reward profile"""
        if not self.perplexity:
            return "Risk analysis not available"

        try:
            from autonomous.connectors.perplexity_finance_fixed import AnalysisType, ResearchDepth

            analysis = await self.perplexity.analyze_stock(
                ticker,
                AnalysisType.FUNDAMENTAL,
                ResearchDepth.STANDARD
            )

            # Calculate simple risk-reward
            risk_level = "High"
            if analysis.pe_ratio and analysis.pe_ratio < 20:
                risk_level = "Low"
            elif analysis.pe_ratio and analysis.pe_ratio < 30:
                risk_level = "Medium"

            reward_potential = analysis.upside_potential or 0
            risk_reward_ratio = abs(reward_potential / 10) if reward_potential else 0

            return f"""
Risk-Reward Analysis for {ticker}:
- Risk Level: {risk_level}
- Reward Potential: {reward_potential:.1f}%
- Risk/Reward Ratio: {risk_reward_ratio:.2f}
- Key Risks: {', '.join(analysis.key_risks[:3]) if analysis.key_risks else 'N/A'}
"""
        except Exception as e:
            return f"Risk analysis error: {str(e)[:100]}"

    # Helper methods
    async def _prepare_context(self, query: ResearchQuery) -> Dict[str, Any]:
        """Prepare context for research query"""
        context = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "depth": query.depth
        }

        # Add portfolio context if requested and available
        if query.include_portfolio and self.db:
            try:
                positions = self.db.get_active_positions()
                if positions:
                    context["portfolio"] = [
                        {
                            "ticker": p.ticker,
                            "shares": p.quantity,
                            "value": float(p.market_value) if hasattr(p, 'market_value') else 0
                        }
                        for p in positions
                    ]
            except Exception as e:
                logger.warning(f"Could not get portfolio context: {e}")

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
            confidence=0.75,  # Default confidence
            data_points=[],
            recommendations=recommendations,
            risks=risks,
            sources=["Perplexity AI", "Market Data"],
            timestamp=datetime.now(timezone.utc),
            follow_up_questions=follow_ups
        )

    def _generate_follow_up_questions(self, question: str, answer: str) -> List[str]:
        """Generate relevant follow-up questions"""
        follow_ups = []

        question_lower = question.lower()
        if "undervalued" in question_lower:
            follow_ups.append("What are the key risks for these undervalued stocks?")
            follow_ups.append("How do these compare to the S&P 500 valuation?")
        elif "invest" in question_lower:
            follow_ups.append("What is the optimal position size for my portfolio?")
            follow_ups.append("When would be the best entry point?")
        elif "sector" in answer.lower():
            follow_ups.append("Which sectors are currently outperforming?")

        return follow_ups[:3]

    def _extract_recommendations(self, text: str) -> List[Dict[str, Any]]:
        """Extract recommendations from text"""
        recommendations = []

        # Simple pattern matching
        if re.search(r'\bbuy\b', text, re.IGNORECASE):
            recommendations.append({
                "action": "BUY",
                "confidence": 0.7,
                "reasoning": "Based on analysis"
            })
        if re.search(r'\bsell\b', text, re.IGNORECASE):
            recommendations.append({
                "action": "SELL",
                "confidence": 0.6,
                "reasoning": "Based on analysis"
            })

        return recommendations[:5]

    def _extract_risks(self, text: str) -> List[str]:
        """Extract risks from text"""
        risks = []

        risk_keywords = ['risk', 'concern', 'threat', 'weakness', 'vulnerable']
        lines = text.split('\n')

        for line in lines:
            if any(keyword in line.lower() for keyword in risk_keywords):
                risk = line.strip()
                if len(risk) > 10 and len(risk) < 200:
                    risks.append(risk)

        return risks[:5]

    def _setup_agent(self) -> AgentExecutor:
        """Setup the LangChain agent with proper configuration"""

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

        # Create the agent using the new method
        from langchain.agents import create_openai_functions_agent

        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        # Create executor with proper error handling
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            return_intermediate_steps=False,
            max_iterations=5,
            handle_parsing_errors=True,
            max_execution_time=30  # 30 second timeout
        )

        return agent_executor