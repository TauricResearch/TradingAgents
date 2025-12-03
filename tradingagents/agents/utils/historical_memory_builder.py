"""
Historical Memory Builder for TradingAgents

This module creates agent memories from historical stock data by:
1. Analyzing market conditions at time T
2. Observing actual stock performance at time T + delta
3. Creating situation -> outcome mappings for each agent type
4. Storing memories in ChromaDB for future retrieval
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from tradingagents.tools.executor import execute_tool
from tradingagents.agents.utils.memory import FinancialSituationMemory


class HistoricalMemoryBuilder:
    """Build agent memories from historical stock data."""

    def __init__(self, config: dict):
        """Initialize the memory builder.

        Args:
            config: TradingAgents configuration dictionary
        """
        self.config = config
        self.memories_created = {
            "bull": 0,
            "bear": 0,
            "trader": 0,
            "invest_judge": 0,
            "risk_manager": 0
        }

    def _get_stock_data_for_period(self, ticker: str, date: str) -> Dict[str, str]:
        """Gather all available data for a stock on a specific date.

        Args:
            ticker: Stock ticker symbol
            date: Date in YYYY-MM-DD format

        Returns:
            Dictionary with market_report, news_report, sentiment_report, fundamentals_report
        """
        data = {}

        try:
            # Get technical/price data (what Market Analyst sees)
            stock_data = execute_tool("get_stock_data", symbol=ticker, start_date=date)
            indicators = execute_tool("get_indicators", symbol=ticker, start_date=date)
            data["market_report"] = f"Stock Data:\n{stock_data}\n\nTechnical Indicators:\n{indicators}"
        except Exception as e:
            data["market_report"] = f"Error fetching market data: {e}"

        try:
            # Get news (what News Analyst sees)
            news = execute_tool("get_news", symbol=ticker, from_date=date, to_date=date)
            data["news_report"] = news
        except Exception as e:
            data["news_report"] = f"Error fetching news: {e}"

        try:
            # Get sentiment (what Social Analyst sees)
            sentiment = execute_tool("get_reddit_discussions", symbol=ticker, from_date=date, to_date=date)
            data["sentiment_report"] = sentiment
        except Exception as e:
            data["sentiment_report"] = f"Error fetching sentiment: {e}"

        try:
            # Get fundamentals (what Fundamentals Analyst sees)
            fundamentals = execute_tool("get_fundamentals", symbol=ticker)
            data["fundamentals_report"] = fundamentals
        except Exception as e:
            data["fundamentals_report"] = f"Error fetching fundamentals: {e}"

        return data

    def _calculate_returns(self, ticker: str, start_date: str, end_date: str) -> Optional[float]:
        """Calculate stock returns between two dates.

        Args:
            ticker: Stock ticker symbol
            start_date: Starting date (YYYY-MM-DD)
            end_date: Ending date (YYYY-MM-DD)

        Returns:
            Percentage return, or None if data unavailable
        """
        try:
            # Get stock prices for both dates
            start_data = execute_tool("get_stock_data", symbol=ticker, start_date=start_date, end_date=start_date)
            end_data = execute_tool("get_stock_data", symbol=ticker, start_date=end_date, end_date=end_date)

            # Parse prices (this is simplified - you'd need to parse the actual response)
            # Assuming response has close price - adjust based on actual API response
            import re
            start_match = re.search(r'Close[:\s]+\$?([\d.]+)', str(start_data))
            end_match = re.search(r'Close[:\s]+\$?([\d.]+)', str(end_data))

            if start_match and end_match:
                start_price = float(start_match.group(1))
                end_price = float(end_match.group(1))
                return ((end_price - start_price) / start_price) * 100

            return None
        except Exception as e:
            print(f"Error calculating returns: {e}")
            return None

    def _create_bull_researcher_memory(self, situation: str, returns: float, ticker: str, date: str) -> str:
        """Create memory for bull researcher based on outcome.

        Returns lesson learned from bullish perspective.
        """
        if returns > 5:
            return f"""SUCCESSFUL BULLISH ANALYSIS for {ticker} on {date}:
The market conditions indicated strong bullish signals, and the stock delivered {returns:.2f}% returns.

Key takeaways:
- When similar conditions appear (strong fundamentals + positive sentiment + bullish technicals), aggressive BUY positions are warranted
- The combination of factors in this situation was a reliable indicator of upward momentum
- Continue to weight these signals heavily in future bullish arguments

Recommendation: In similar situations, advocate strongly for BUY positions with high conviction.
"""
        elif returns < -5:
            return f"""INCORRECT BULLISH SIGNALS for {ticker} on {date}:
Despite apparent bullish indicators, the stock declined {abs(returns):.2f}%.

Lessons learned:
- The bullish signals in this situation were misleading or outweighed by hidden risks
- Need to look deeper at: macro conditions, sector headwinds, or fundamental weaknesses that weren't apparent
- Be more cautious when similar patterns appear; consider bear arguments more seriously

Recommendation: In similar situations, temper bullish enthusiasm and scrutinize fundamentals more carefully.
"""
        else:
            return f"""NEUTRAL OUTCOME for {ticker} on {date}:
Stock moved {returns:.2f}%, indicating mixed signals.

Lesson: This pattern of indicators doesn't provide strong directional conviction. Look for clearer signals before making strong bullish arguments.
"""

    def _create_bear_researcher_memory(self, situation: str, returns: float, ticker: str, date: str) -> str:
        """Create memory for bear researcher based on outcome."""
        if returns < -5:
            return f"""SUCCESSFUL BEARISH ANALYSIS for {ticker} on {date}:
Bearish indicators correctly predicted decline of {abs(returns):.2f}%.

Key takeaways:
- The risk factors identified were valid and material
- Similar warning signs should be treated seriously in future analysis
- When these patterns appear, advocate strongly for SELL or reduce positions

Recommendation: In similar situations, maintain bearish stance with high conviction.
"""
        elif returns > 5:
            return f"""INCORRECT BEARISH SIGNALS for {ticker} on {date}:
Despite bearish indicators, stock rallied {returns:.2f}%.

Lessons learned:
- The bearish concerns were either overstated or offset by stronger positive factors
- Market sentiment or momentum can override fundamental concerns in short term
- Need to better assess whether bearish factors are already priced in

Recommendation: In similar situations, be more cautious about strong SELL recommendations.
"""
        else:
            return f"""NEUTRAL OUTCOME for {ticker} on {date}:
Stock moved {returns:.2f}%, mixed signals.

Lesson: These indicators don't provide clear bearish conviction. Need stronger warning signs for definitive bearish stance.
"""

    def _create_trader_memory(self, situation: str, returns: float, ticker: str, date: str) -> str:
        """Create memory for trader based on outcome."""
        if abs(returns) < 2:
            action = "HOLD"
            result = "correct - low volatility"
        elif returns > 5:
            action = "BUY"
            result = "would have been optimal"
        elif returns < -5:
            action = "SELL or avoid"
            result = "would have been optimal"
        else:
            action = "modest position"
            result = "moderate returns"

        return f"""TRADING OUTCOME for {ticker} on {date}:
Stock returned {returns:.2f}% over the evaluation period.

Optimal action: {action} - {result}

Market conditions at the time:
{situation[:500]}...

Trading lesson:
- When similar market conditions appear, consider {action} strategy
- Risk/reward profile: {'Favorable' if abs(returns) > 3 else 'Neutral'}
- Position sizing: {'Aggressive' if abs(returns) > 7 else 'Moderate' if abs(returns) > 3 else 'Conservative'}

Recommendation: Pattern recognition suggests {action} in similar future scenarios.
"""

    def _create_invest_judge_memory(self, situation: str, returns: float, ticker: str, date: str) -> str:
        """Create memory for investment judge/research manager."""
        if returns > 5:
            verdict = "Strong BUY recommendation was warranted"
        elif returns > 2:
            verdict = "Moderate BUY recommendation was appropriate"
        elif returns < -5:
            verdict = "SELL or AVOID recommendation was warranted"
        elif returns < -2:
            verdict = "HOLD or reduce exposure was appropriate"
        else:
            verdict = "HOLD recommendation was appropriate"

        return f"""INVESTMENT DECISION REVIEW for {ticker} on {date}:
Actual outcome: {returns:.2f}% return

Optimal decision: {verdict}

When synthesizing bull/bear arguments in similar conditions:
- Weight the arguments based on which perspective proved more accurate
- {"Bull arguments were stronger" if returns > 0 else "Bear arguments were stronger"}
- Factor reliability: {'High' if abs(returns) > 5 else 'Medium' if abs(returns) > 2 else 'Low'}

Recommendation for similar situations: {verdict}
"""

    def _create_risk_manager_memory(self, situation: str, returns: float, ticker: str, date: str) -> str:
        """Create memory for risk manager."""
        volatility = "HIGH" if abs(returns) > 10 else "MEDIUM" if abs(returns) > 5 else "LOW"

        if abs(returns) > 10:
            risk_assessment = "High risk - extreme volatility observed"
        elif abs(returns) > 5:
            risk_assessment = "Moderate risk - significant movement"
        else:
            risk_assessment = "Low risk - stable price action"

        return f"""RISK ASSESSMENT REVIEW for {ticker} on {date}:
Observed volatility: {volatility} (actual return: {returns:.2f}%)

Risk factors that materialized:
- Price volatility: {volatility}
- Directional risk: {'Significant downside' if returns < -5 else 'Significant upside' if returns > 5 else 'Minimal'}

Risk management lesson:
In similar market conditions:
- Position size: {'Small (high risk)' if abs(returns) > 10 else 'Moderate' if abs(returns) > 5 else 'Standard'}
- Stop loss: {'Tight (±5%)' if abs(returns) > 10 else 'Standard (±7%)' if abs(returns) > 5 else 'Relaxed (±10%)'}
- Diversification: {'Critical' if abs(returns) > 10 else 'Recommended' if abs(returns) > 5 else 'Standard'}

Recommendation: {risk_assessment}
"""

    def build_memories_for_stock(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        lookforward_days: int = 7,
        interval_days: int = 30
    ) -> Dict[str, List[Tuple[str, str]]]:
        """Build historical memories for a stock across a date range.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            lookforward_days: How many days forward to measure returns (default: 7)
            interval_days: Days between memory samples (default: 30)

        Returns:
            Dictionary mapping agent type to list of (situation, lesson) tuples
        """
        memories = {
            "bull": [],
            "bear": [],
            "trader": [],
            "invest_judge": [],
            "risk_manager": []
        }

        current_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        print(f"\n🧠 Building historical memories for {ticker}")
        print(f"   Period: {start_date} to {end_date}")
        print(f"   Lookforward: {lookforward_days} days")
        print(f"   Sampling interval: {interval_days} days\n")

        sample_count = 0
        while current_date <= end_dt:
            date_str = current_date.strftime("%Y-%m-%d")
            future_date_str = (current_date + timedelta(days=lookforward_days)).strftime("%Y-%m-%d")

            print(f"   📊 Sampling {date_str}...", end=" ")

            # Get historical data for this period
            data = self._get_stock_data_for_period(ticker, date_str)
            situation = f"{data['market_report']}\n\n{data['sentiment_report']}\n\n{data['news_report']}\n\n{data['fundamentals_report']}"

            # Calculate actual returns
            returns = self._calculate_returns(ticker, date_str, future_date_str)

            if returns is not None:
                print(f"Return: {returns:+.2f}%")

                # Create agent-specific memories
                memories["bull"].append((
                    situation,
                    self._create_bull_researcher_memory(situation, returns, ticker, date_str)
                ))

                memories["bear"].append((
                    situation,
                    self._create_bear_researcher_memory(situation, returns, ticker, date_str)
                ))

                memories["trader"].append((
                    situation,
                    self._create_trader_memory(situation, returns, ticker, date_str)
                ))

                memories["invest_judge"].append((
                    situation,
                    self._create_invest_judge_memory(situation, returns, ticker, date_str)
                ))

                memories["risk_manager"].append((
                    situation,
                    self._create_risk_manager_memory(situation, returns, ticker, date_str)
                ))

                sample_count += 1
            else:
                print("⚠️  No data")

            # Move to next interval
            current_date += timedelta(days=interval_days)

        print(f"\n✅ Created {sample_count} memory samples for {ticker}")
        for agent_type in memories:
            self.memories_created[agent_type] += len(memories[agent_type])

        return memories

    def populate_agent_memories(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        lookforward_days: int = 7,
        interval_days: int = 30
    ) -> Dict[str, FinancialSituationMemory]:
        """Build and populate memories for all agent types across multiple stocks.

        Args:
            tickers: List of stock ticker symbols
            start_date: Start date for historical analysis
            end_date: End date for historical analysis
            lookforward_days: Days forward to measure returns
            interval_days: Days between samples

        Returns:
            Dictionary of populated memory instances for each agent type
        """
        # Initialize memory stores
        agent_memories = {
            "bull": FinancialSituationMemory("bull_memory", self.config),
            "bear": FinancialSituationMemory("bear_memory", self.config),
            "trader": FinancialSituationMemory("trader_memory", self.config),
            "invest_judge": FinancialSituationMemory("invest_judge_memory", self.config),
            "risk_manager": FinancialSituationMemory("risk_manager_memory", self.config)
        }

        print("=" * 70)
        print("🏗️  HISTORICAL MEMORY BUILDER")
        print("=" * 70)

        # Build memories for each ticker
        for ticker in tickers:
            memories = self.build_memories_for_stock(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                lookforward_days=lookforward_days,
                interval_days=interval_days
            )

            # Add memories to each agent's memory store
            for agent_type, memory_list in memories.items():
                if memory_list:
                    agent_memories[agent_type].add_situations(memory_list)

        # Print summary
        print("\n" + "=" * 70)
        print("📊 MEMORY CREATION SUMMARY")
        print("=" * 70)
        for agent_type, count in self.memories_created.items():
            print(f"   {agent_type.ljust(15)}: {count} memories")
        print("=" * 70 + "\n")

        return agent_memories


# Example usage
if __name__ == "__main__":
    from tradingagents.default_config import DEFAULT_CONFIG

    # Initialize builder
    builder = HistoricalMemoryBuilder(DEFAULT_CONFIG)

    # Build memories for specific stocks over past year
    tickers = ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"]

    memories = builder.populate_agent_memories(
        tickers=tickers,
        start_date="2024-01-01",
        end_date="2024-12-01",
        lookforward_days=7,     # 1-week returns
        interval_days=30        # Sample monthly
    )

    # Test retrieval
    test_situation = "Strong earnings beat with positive sentiment and bullish technical indicators in tech sector"

    print("\n🔍 Testing memory retrieval...")
    print(f"Query: {test_situation}\n")

    for agent_type, memory in memories.items():
        print(f"\n{agent_type.upper()} MEMORIES:")
        results = memory.get_memories(test_situation, n_matches=2)
        for i, result in enumerate(results, 1):
            print(f"\n  Match {i} (similarity: {result['similarity_score']:.2f}):")
            print(f"  {result['recommendation'][:200]}...")
