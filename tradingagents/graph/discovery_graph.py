from typing import Dict, Any, List
import re
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage

from tradingagents.agents.utils.agent_states import DiscoveryState
from tradingagents.agents.utils.agent_utils import (
    get_news,
    get_insider_transactions,
    get_fundamentals,
    get_indicators
)
from tradingagents.tools.executor import execute_tool
from tradingagents.schemas import TickerList, MarketMovers, ThemeList

class DiscoveryGraph:
    def __init__(self, config=None):
        """
        Initialize Discovery Graph.
        
        Args:
            config: Configuration dictionary
        """
        from langchain_openai import ChatOpenAI
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        import os
        
        self.config = config or {}
        
        # Initialize LLMs using the same pattern as TradingAgentsGraph
        if self.config["llm_provider"] == "openai" or self.config["llm_provider"] == "ollama" or self.config["llm_provider"] == "openrouter":
            self.deep_thinking_llm = ChatOpenAI(model=self.config["deep_think_llm"], base_url=self.config["backend_url"])
            self.quick_thinking_llm = ChatOpenAI(model=self.config["quick_think_llm"], base_url=self.config["backend_url"])
        elif self.config["llm_provider"] == "anthropic":
            self.deep_thinking_llm = ChatAnthropic(model=self.config["deep_think_llm"], base_url=self.config["backend_url"])
            self.quick_thinking_llm = ChatAnthropic(model=self.config["quick_think_llm"], base_url=self.config["backend_url"])
        elif self.config["llm_provider"] == "google":
            # Explicitly pass Google API key from environment
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                raise ValueError("GOOGLE_API_KEY environment variable not set. Please add it to your .env file.")
            self.deep_thinking_llm = ChatGoogleGenerativeAI(model=self.config["deep_think_llm"], google_api_key=google_api_key)
            self.quick_thinking_llm = ChatGoogleGenerativeAI(model=self.config["quick_think_llm"], google_api_key=google_api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config['llm_provider']}")
        
        # Extract discovery settings with defaults
        discovery_config = self.config.get("discovery", {})
        self.reddit_trending_limit = discovery_config.get("reddit_trending_limit", 15)
        self.market_movers_limit = discovery_config.get("market_movers_limit", 10)
        self.max_candidates_to_analyze = discovery_config.get("max_candidates_to_analyze", 10)
        self.news_lookback_days = discovery_config.get("news_lookback_days", 7)
        self.final_recommendations = discovery_config.get("final_recommendations", 3)
        self.graph = self._create_graph()

    def _create_graph(self):
        workflow = StateGraph(DiscoveryState)

        workflow.add_node("scanner", self.scanner_node)
        workflow.add_node("filter", self.filter_node)
        workflow.add_node("deep_dive", self.deep_dive_node)
        workflow.add_node("ranker", self.ranker_node)

        workflow.set_entry_point("scanner")
        workflow.add_edge("scanner", "filter")
        workflow.add_edge("filter", "deep_dive")
        workflow.add_edge("deep_dive", "ranker")
        workflow.add_edge("ranker", END)

        return workflow.compile()

    def scanner_node(self, state: DiscoveryState):
        """Scan the market for potential candidates."""
        print("🔍 Scanning market for opportunities...")
        
        candidates = []
        
        # 0. Macro Theme Discovery (Top-Down)
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Get Global News
            global_news = execute_tool("get_global_news", date=today, limit=5)
            
            # Extract Themes
            prompt = f"""Based on this global news, identify 3 trending market themes or sectors (e.g., 'Artificial Intelligence', 'Oil', 'Biotech').
            Return a JSON object with a 'themes' array of strings.
            
            News:
            {global_news}
            """
            
            structured_llm = self.quick_thinking_llm.with_structured_output(
                schema=ThemeList.model_json_schema(),
                method="json_schema"
            )
            response = structured_llm.invoke([HumanMessage(content=prompt)])
            themes = response.get("themes", [])
            
            print(f"   Identified Macro Themes: {themes}")
            
            # Find tickers for each theme
            for theme in themes:
                try:
                    tweets_report = execute_tool("get_tweets", query=f"{theme} stocks", count=15)
                    
                    prompt = f"""Extract ONLY valid stock ticker symbols related to the theme '{theme}' from this report.
                    Return a comma-separated list of tickers (1-5 uppercase letters).
                    
                    Report:
                    {tweets_report}
                    
                    Return a JSON object with a 'tickers' array."""
                    
                    structured_llm = self.quick_thinking_llm.with_structured_output(
                        schema=TickerList.model_json_schema(),
                        method="json_schema"
                    )
                    response = structured_llm.invoke([HumanMessage(content=prompt)])
                    theme_tickers = response.get("tickers", [])
                    
                    for t in theme_tickers:
                        t = t.upper().strip()
                        if re.match(r'^[A-Z]{1,5}$', t):
                             # Use validate_ticker tool logic (via execute_tool)
                            try:
                                if execute_tool("validate_ticker", symbol=t):
                                    candidates.append({"ticker": t, "source": f"macro_theme_{theme}", "sentiment": "unknown"})
                            except Exception:
                                continue
                except Exception as e:
                    print(f"   Error fetching tickers for theme {theme}: {e}")
                    
        except Exception as e:
            print(f"   Error in Macro Theme Discovery: {e}")

        # 1. Get Reddit Trending (Social Sentiment)
        try:
            reddit_report = execute_tool("get_trending_tickers", limit=self.reddit_trending_limit)
            # Use LLM to extract tickers
            prompt = """Extract ONLY valid stock ticker symbols from this Reddit report.
Return a comma-separated list of tickers (1-5 uppercase letters).
Do not include currencies (like RMB), cryptocurrencies (like BTC unless it's an ETF), or explanations.
Only include actual stock tickers.

Examples of valid tickers: AAPL, GOOGL, MSFT, TSLA, NVDA
Examples of invalid: RMB (currency), BTC (crypto)

Report:
{report}

Return a JSON object with a 'tickers' array containing only valid stock ticker symbols.""".format(report=reddit_report)
            
            # Use structured output for ticker extraction
            structured_llm = self.quick_thinking_llm.with_structured_output(
                schema=TickerList.model_json_schema(),
                method="json_schema"
            )
            response = structured_llm.invoke([HumanMessage(content=prompt)])
            
            # Validate and add tickers
            reddit_tickers = response.get("tickers", [])
            for t in reddit_tickers:
                t = t.upper().strip()
                # Validate ticker format (1-5 uppercase letters)
                if re.match(r'^[A-Z]{1,5}$', t):
                    candidates.append({"ticker": t, "source": "social_trending", "sentiment": "unknown"})
        except Exception as e:
            print(f"   Error fetching Reddit tickers: {e}")

        # 2. Get Twitter Trending (Social Sentiment)
        try:
            # Search for general market discussions
            tweets_report = execute_tool("get_tweets", query="stocks to watch", count=20)
            
            # Use LLM to extract tickers
            prompt = """Extract ONLY valid stock ticker symbols from this Twitter report.
Return a comma-separated list of tickers (1-5 uppercase letters).
Do not include currencies (like RMB), cryptocurrencies (like BTC unless it's an ETF), or explanations.
Only include actual stock tickers.

Examples of valid tickers: AAPL, GOOGL, MSFT, TSLA, NVDA
Examples of invalid: RMB (currency), BTC (crypto)

Report:
{report}

Return a JSON object with a 'tickers' array containing only valid stock ticker symbols.""".format(report=tweets_report)
            
            # Use structured output for ticker extraction
            structured_llm = self.quick_thinking_llm.with_structured_output(
                schema=TickerList.model_json_schema(),
                method="json_schema"
            )
            response = structured_llm.invoke([HumanMessage(content=prompt)])
            
            # Validate and add tickers
            twitter_tickers = response.get("tickers", [])
            valid_twitter_tickers = []
            for t in twitter_tickers:
                t = t.upper().strip()
                # Validate ticker format (1-5 uppercase letters)
                if re.match(r'^[A-Z]{1,5}$', t):
                    # Use validate_ticker tool logic (via execute_tool)
                    try:
                        if execute_tool("validate_ticker", symbol=t):
                            valid_twitter_tickers.append(t)
                    except Exception:
                        continue

            for t in valid_twitter_tickers:
                candidates.append({"ticker": t, "source": "twitter_sentiment", "sentiment": "unknown"})
        except Exception as e:
            print(f"   Error fetching Twitter tickers: {e}")

        # 2. Get Market Movers (Gainers & Losers)
        try:
            movers_report = execute_tool("get_market_movers", limit=self.market_movers_limit)
            # We need to parse this to separate Gainers vs Losers
            # Since it's a markdown report, we'll use LLM to structure it
            prompt = f"""Based on the following market movers data, extract the top {self.market_movers_limit} tickers.
Return a JSON object with a 'movers' array containing objects with 'ticker' and 'type' (either 'gainer' or 'loser') fields.

Data:
{movers_report}"""
            
            # Use structured output for market movers
            structured_llm = self.quick_thinking_llm.with_structured_output(
                schema=MarketMovers.model_json_schema(),
                method="json_schema"
            )
            response = structured_llm.invoke([HumanMessage(content=prompt)])
            
            # Validate and add tickers
            movers = response.get("movers", [])
            for m in movers:
                ticker = m.get('ticker', '').upper().strip()
                # Only add valid tickers (1-5 uppercase letters)
                if ticker and re.match(r'^[A-Z]{1,5}$', ticker):
                    mover_type = m.get('type', 'gainer')
                    candidates.append({
                        "ticker": ticker,
                        "source": mover_type,
                        "sentiment": "negative" if mover_type == "loser" else "positive"
                    })

        except Exception as e:
            print(f"   Error fetching Market Movers: {e}")

        # 3. Get Earnings Calendar (Event-based Discovery)
        try:
            from datetime import datetime, timedelta
            today = datetime.now()
            from_date = today.strftime("%Y-%m-%d")
            to_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")  # Next 7 days

            earnings_report = execute_tool("get_earnings_calendar", from_date=from_date, to_date=to_date)

            # Extract tickers from earnings calendar
            prompt = """Extract ONLY valid stock ticker symbols from this earnings calendar.
Return a comma-separated list of tickers (1-5 uppercase letters).
Only include actual stock tickers, not indexes or other symbols.

Earnings Calendar:
{report}

Return a JSON object with a 'tickers' array containing only valid stock ticker symbols.""".format(report=earnings_report)

            structured_llm = self.quick_thinking_llm.with_structured_output(
                schema=TickerList.model_json_schema(),
                method="json_schema"
            )
            response = structured_llm.invoke([HumanMessage(content=prompt)])

            earnings_tickers = response.get("tickers", [])
            for t in earnings_tickers:
                t = t.upper().strip()
                if re.match(r'^[A-Z]{1,5}$', t):
                    candidates.append({"ticker": t, "source": "earnings_catalyst", "sentiment": "unknown"})
        except Exception as e:
            print(f"   Error fetching Earnings Calendar: {e}")

        # 4. Get IPO Calendar (New Listings Discovery)
        try:
            from datetime import datetime, timedelta
            today = datetime.now()
            from_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")  # Past 7 days
            to_date = (today + timedelta(days=14)).strftime("%Y-%m-%d")   # Next 14 days

            ipo_report = execute_tool("get_ipo_calendar", from_date=from_date, to_date=to_date)

            # Extract tickers from IPO calendar
            prompt = """Extract ONLY valid stock ticker symbols from this IPO calendar.
Return a comma-separated list of tickers (1-5 uppercase letters).
Only include actual stock tickers that are listed or about to be listed.

IPO Calendar:
{report}

Return a JSON object with a 'tickers' array containing only valid stock ticker symbols.""".format(report=ipo_report)

            structured_llm = self.quick_thinking_llm.with_structured_output(
                schema=TickerList.model_json_schema(),
                method="json_schema"
            )
            response = structured_llm.invoke([HumanMessage(content=prompt)])

            ipo_tickers = response.get("tickers", [])
            for t in ipo_tickers:
                t = t.upper().strip()
                if re.match(r'^[A-Z]{1,5}$', t):
                    candidates.append({"ticker": t, "source": "ipo_listing", "sentiment": "unknown"})
        except Exception as e:
            print(f"   Error fetching IPO Calendar: {e}")

        # Deduplicate
        unique_candidates = {}
        for c in candidates:
            if c['ticker'] not in unique_candidates:
                unique_candidates[c['ticker']] = c
        
        final_candidates = list(unique_candidates.values())
        print(f"   Found {len(final_candidates)} unique candidates.")
        return {"tickers": [c['ticker'] for c in final_candidates], "candidate_metadata": final_candidates, "status": "scanned"}

    def filter_node(self, state: DiscoveryState):
        """Filter candidates based on strategy (Contrarian vs Momentum)."""
        candidates = state.get("candidate_metadata", [])
        if not candidates:
            # Fallback if metadata missing (backward compatibility)
            candidates = [{"ticker": t, "source": "unknown"} for t in state["tickers"]]
            
        print(f"🔍 Filtering {len(candidates)} candidates...")
        
        filtered_candidates = []
        
        for cand in candidates:
            ticker = cand['ticker']
            source = cand['source']
            
            try:
                # Get Fundamentals
                # We use get_fundamentals to get P/E, Market Cap, etc.
                # Since get_fundamentals returns a JSON string (from Alpha Vantage), we can parse it.
                # Note: In a real run, we'd use the tool. Here we simulate the logic.
                
                # Logic:
                # 1. Contrarian (Losers): Look for Strong Fundamentals (Low P/E, High Profit)
                # 2. Momentum (Gainers/Social): Look for Growth (Revenue Growth)
                
                # For this implementation, we'll pass them to the deep dive 
                # but tag them with the strategy we want to verify.
                
                strategy = "momentum"
                if source == "loser":
                    strategy = "contrarian_value"
                elif source == "social_trending" or source == "twitter_sentiment":
                    strategy = "social_hype"
                elif source == "earnings_catalyst":
                    strategy = "earnings_play"
                elif source == "ipo_listing":
                    strategy = "ipo_opportunity"
                
                cand['strategy'] = strategy
                
                # Technical Analysis Check (New)
                try:
                    from datetime import datetime
                    today = datetime.now().strftime("%Y-%m-%d")
                    
                    # Get RSI
                    rsi_data = execute_tool("get_indicators", symbol=ticker, indicator="rsi", curr_date=today, look_back_days=14)
                    
                    # Simple parsing of the string report to find the latest value
                    # The report format is usually "## rsi values...\n\nDATE: VALUE"
                    # We'll just store the report for the LLM to analyze in deep dive if needed, 
                    # OR we can try to parse it here. For now, let's just add it to metadata.
                    cand['technical_indicators'] = rsi_data
                    
                except Exception as e:
                    print(f"   Error getting technicals for {ticker}: {e}")
                
                filtered_candidates.append(cand)
                
            except Exception as e:
                print(f"   Error checking {ticker}: {e}")
        
        # Limit to configured max
        filtered_candidates = filtered_candidates[:self.max_candidates_to_analyze]
        
        print(f"   Selected {len(filtered_candidates)} for deep dive.")
        return {"filtered_tickers": [c['ticker'] for c in filtered_candidates], "candidate_metadata": filtered_candidates, "status": "filtered"}

    def deep_dive_node(self, state: DiscoveryState):
        """Perform deep dive analysis on selected candidates."""
        candidates = state.get("candidate_metadata", [])
        trade_date = state.get("trade_date", "")
        
        # Calculate date range for news (configurable days back from trade_date)
        from datetime import datetime, timedelta
        
        if trade_date:
            end_date_obj = datetime.strptime(trade_date, "%Y-%m-%d")
        else:
            end_date_obj = datetime.now()
            
        start_date_obj = end_date_obj - timedelta(days=self.news_lookback_days)
        start_date = start_date_obj.strftime("%Y-%m-%d")
        end_date = end_date_obj.strftime("%Y-%m-%d")
        
        print(f"🔍 Performing deep dive on {len(candidates)} candidates...")
        print(f"   News date range: {start_date} to {end_date}")
        
        opportunities = []
        
        for cand in candidates:
            ticker = cand['ticker']
            strategy = cand['strategy']
            print(f"   Analyzing {ticker} ({strategy})...")
            
            try:
                # 1. Get News Sentiment
                news = execute_tool("get_news", ticker=ticker, start_date=start_date, end_date=end_date)
                
                # 2. Get Insider Transactions & Sentiment
                insider = execute_tool("get_insider_transactions", ticker=ticker)
                insider_sentiment = execute_tool("get_insider_sentiment", ticker=ticker)
                
                # 3. Get Fundamentals (for the Contrarian check)
                fundamentals = execute_tool("get_fundamentals", ticker=ticker, curr_date=end_date)
                
                # 4. Get Analyst Recommendations
                recommendations = execute_tool("get_recommendation_trends", ticker=ticker)
                
                opportunities.append({
                    "ticker": ticker,
                    "strategy": strategy,
                    "news": news,
                    "insider_transactions": insider,
                    "insider_sentiment": insider_sentiment,
                    "fundamentals": fundamentals,
                    "recommendations": recommendations
                })
                
            except Exception as e:
                print(f"   Failed to analyze {ticker}: {e}")
        
        return {"opportunities": opportunities, "status": "analyzed"}

    def ranker_node(self, state: DiscoveryState):
        """Rank opportunities and select the best ones."""
        opportunities = state["opportunities"]
        print("🔍 Ranking opportunities...")
        
        # Truncate data to prevent token limit errors
        # Keep only essential info for ranking
        truncated_opps = []
        for opp in opportunities:
            truncated_opps.append({
                "ticker": opp["ticker"],
                "strategy": opp["strategy"],
                # Truncate to ~1000 chars each (roughly 250 tokens)
                "news": opp["news"][:1000] + "..." if len(opp["news"]) > 1000 else opp["news"],
                "insider_sentiment": opp.get("insider_sentiment", "")[:500],
                "insider_transactions": opp["insider_transactions"][:1000] + "..." if len(opp["insider_transactions"]) > 1000 else opp["insider_transactions"],
                "fundamentals": opp["fundamentals"][:1000] + "..." if len(opp["fundamentals"]) > 1000 else opp["fundamentals"],
                "recommendations": opp["recommendations"][:1000] + "..." if len(opp["recommendations"]) > 1000 else opp["recommendations"],
            })
        
        prompt = f"""
        Analyze these investment opportunities and select the TOP {self.final_recommendations} most promising ones.
        
        STRATEGIES TO LOOK FOR:
        1. **Contrarian Value**: Stock is a "Loser" or has bad sentiment, BUT has strong fundamentals (Low P/E, good financials).
        2. **Momentum/Hype**: Stock is Trending/Gainer AND has news/growth to support it.
        3. **Insider Play**: Significant insider buying regardless of trend.
        
        OPPORTUNITIES:
        {truncated_opps}
        
        Return a JSON list of the top {self.final_recommendations}, with fields: 
        - "ticker"
        - "strategy_match" (e.g., "Contrarian Value", "Momentum")
        - "reason" (Explain WHY it fits the strategy)
        - "confidence" (0-10)
        """
        
        response = self.deep_thinking_llm.invoke([HumanMessage(content=prompt)])
        
        print("   Ranking complete.")
        return {"status": "complete", "opportunities": opportunities, "final_ranking": response.content}
