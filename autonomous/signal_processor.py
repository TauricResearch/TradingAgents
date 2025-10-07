"""
Signal Processor
===============

Processes signals from multiple sources and generates actionable trading recommendations
with specific entry/exit prices using TradingAgents AI.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import statistics

# Import TradingAgents
import sys
sys.path.append('..')
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Import our modules
from .ibkr_connector import IBKRConnector, Position
from .data_aggregator import DataAggregator, MarketSignal

logger = logging.getLogger(__name__)


@dataclass
class TradingRecommendation:
    """Complete trading recommendation with entry/exit points"""
    ticker: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    current_price: float
    entry_price_min: float
    entry_price_max: float
    target_price_1: float
    target_price_2: float
    stop_loss: float
    confidence: float  # 0-100
    position_size: float  # Percentage of portfolio
    reasoning: str
    data_sources: List[str]
    risk_level: str  # 'LOW', 'MEDIUM', 'HIGH'
    timestamp: datetime


class SignalProcessor:
    """
    Processes signals and generates trading recommendations
    """

    def __init__(self,
                 ibkr_connector: IBKRConnector,
                 data_aggregator: DataAggregator,
                 config: Optional[Dict] = None):
        """
        Initialize signal processor

        Args:
            ibkr_connector: IBKR connection instance
            data_aggregator: Data aggregator instance
            config: Configuration dictionary
        """
        self.ibkr = ibkr_connector
        self.data_agg = data_aggregator
        self.config = config or DEFAULT_CONFIG.copy()

        # Configure TradingAgents for fast processing
        self.config['deep_think_llm'] = 'gpt-4o-mini'
        self.config['quick_think_llm'] = 'gpt-4o-mini'
        self.config['max_debate_rounds'] = 1

        self.trading_agents = TradingAgentsGraph(debug=False, config=self.config)
        self.recommendations: List[TradingRecommendation] = []

    async def calculate_technical_levels(self, ticker: str) -> Dict[str, float]:
        """
        Calculate technical support/resistance levels

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with technical levels
        """
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)

            # Get recent price data
            hist = stock.history(period="3mo")

            if hist.empty:
                return {}

            current_price = hist['Close'].iloc[-1]
            high_3m = hist['High'].max()
            low_3m = hist['Low'].min()

            # Calculate moving averages
            ma_20 = hist['Close'].tail(20).mean()
            ma_50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else ma_20

            # Calculate support/resistance levels
            # Using pivot points
            last_high = hist['High'].iloc[-1]
            last_low = hist['Low'].iloc[-1]
            last_close = hist['Close'].iloc[-1]
            pivot = (last_high + last_low + last_close) / 3

            resistance_1 = 2 * pivot - last_low
            resistance_2 = pivot + (last_high - last_low)
            support_1 = 2 * pivot - last_high
            support_2 = pivot - (last_high - last_low)

            # Calculate RSI
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]

            return {
                'current_price': current_price,
                'resistance_1': resistance_1,
                'resistance_2': resistance_2,
                'support_1': support_1,
                'support_2': support_2,
                'ma_20': ma_20,
                'ma_50': ma_50,
                'high_3m': high_3m,
                'low_3m': low_3m,
                'rsi': current_rsi,
                'pivot': pivot
            }

        except Exception as e:
            logger.error(f"Error calculating technical levels for {ticker}: {e}")
            return {}

    async def analyze_position_sizing(self,
                                     ticker: str,
                                     confidence: float,
                                     risk_level: str) -> float:
        """
        Calculate appropriate position size based on portfolio and risk

        Args:
            ticker: Stock ticker
            confidence: Signal confidence (0-100)
            risk_level: Risk level of the trade

        Returns:
            Position size as percentage of portfolio
        """
        # Get current portfolio info
        await self.ibkr.sync_portfolio()
        portfolio_summary = self.ibkr.get_portfolio_summary()

        # Check if we already have a position
        existing_position = await self.ibkr.get_position(ticker)

        # Base position sizing rules
        max_position = 0.20  # Max 20% in any single position
        base_size = 0.10  # Base 10% position

        # Adjust based on confidence
        if confidence > 90:
            size_multiplier = 1.5
        elif confidence > 80:
            size_multiplier = 1.2
        elif confidence > 70:
            size_multiplier = 1.0
        else:
            size_multiplier = 0.7

        # Adjust based on risk
        risk_multipliers = {
            'LOW': 1.2,
            'MEDIUM': 1.0,
            'HIGH': 0.6
        }
        risk_multiplier = risk_multipliers.get(risk_level, 1.0)

        # Calculate position size
        position_size = base_size * size_multiplier * risk_multiplier

        # If we already have a position, consider scaling
        if existing_position:
            current_weight = existing_position.market_value / portfolio_summary['total_value']
            remaining_capacity = max_position - current_weight
            position_size = min(position_size, remaining_capacity)

        # Ensure within limits
        position_size = max(0.05, min(position_size, max_position))  # Between 5% and 20%

        return round(position_size, 3)

    async def process_signals(self, ticker: str) -> Optional[TradingRecommendation]:
        """
        Process all signals for a ticker and generate recommendation

        Args:
            ticker: Stock ticker

        Returns:
            Trading recommendation if signals are strong enough
        """
        try:
            # Get all signals for this ticker
            signals = [s for s in self.data_agg.market_signals if s.ticker == ticker]

            if not signals:
                logger.info(f"No signals for {ticker}")
                return None

            # Calculate technical levels
            tech_levels = await self.calculate_technical_levels(ticker)

            if not tech_levels:
                logger.warning(f"Could not calculate technical levels for {ticker}")
                return None

            current_price = tech_levels['current_price']

            # Run TradingAgents analysis
            logger.info(f"Running TradingAgents analysis for {ticker}")
            _, ai_decision = self.trading_agents.propagate(ticker, datetime.now().strftime('%Y-%m-%d'))

            # Combine AI decision with our signals
            avg_confidence = statistics.mean([s.confidence for s in signals])

            # Determine action based on signals and AI
            buy_signals = [s for s in signals if s.action == 'BUY']
            sell_signals = [s for s in signals if s.action == 'SELL']

            if len(buy_signals) > len(sell_signals) and 'buy' in ai_decision.lower():
                action = 'BUY'
                # Entry points near support or current price
                entry_min = min(current_price * 0.995, tech_levels['support_1'])
                entry_max = current_price * 1.005

                # Targets based on resistance levels
                target_1 = tech_levels['resistance_1']
                target_2 = tech_levels['resistance_2']

                # Stop loss below support
                stop_loss = tech_levels['support_1'] * 0.98

            elif len(sell_signals) > len(buy_signals) or 'sell' in ai_decision.lower():
                action = 'SELL'
                # For selling, entry is current price range
                entry_min = current_price * 0.995
                entry_max = current_price * 1.01

                # Targets for selling (lower prices)
                target_1 = tech_levels['support_1']
                target_2 = tech_levels['support_2']

                # Stop loss above resistance for shorts
                stop_loss = tech_levels['resistance_1'] * 1.02

            else:
                action = 'HOLD'
                entry_min = entry_max = current_price
                target_1 = target_2 = current_price
                stop_loss = current_price * 0.95

            # Determine risk level
            rsi = tech_levels.get('rsi', 50)
            if rsi > 70 or rsi < 30:
                risk_level = 'HIGH'
            elif 40 <= rsi <= 60:
                risk_level = 'LOW'
            else:
                risk_level = 'MEDIUM'

            # Calculate position size
            position_size = await self.analyze_position_sizing(ticker, avg_confidence, risk_level)

            # Build reasoning
            reasoning_parts = [
                f"AI Analysis: {ai_decision[:200]}",
                f"Signals: {len(buy_signals)} buy, {len(sell_signals)} sell"
            ]

            for signal in signals[:2]:  # Include top 2 signals
                if signal.signal_type == 'congressional':
                    reasoning_parts.append(f"Congressional activity detected")
                elif signal.signal_type == 'insider':
                    reasoning_parts.append(f"Insider buying activity")
                elif signal.signal_type == 'sentiment':
                    reasoning_parts.append(f"Positive market sentiment")

            reasoning_parts.append(f"RSI: {rsi:.1f}")

            # Create recommendation
            recommendation = TradingRecommendation(
                ticker=ticker,
                action=action,
                current_price=current_price,
                entry_price_min=round(entry_min, 2),
                entry_price_max=round(entry_max, 2),
                target_price_1=round(target_1, 2),
                target_price_2=round(target_2, 2),
                stop_loss=round(stop_loss, 2),
                confidence=avg_confidence,
                position_size=position_size,
                reasoning=' | '.join(reasoning_parts),
                data_sources=[s.signal_type for s in signals],
                risk_level=risk_level,
                timestamp=datetime.now()
            )

            self.recommendations.append(recommendation)
            return recommendation

        except Exception as e:
            logger.error(f"Error processing signals for {ticker}: {e}")
            return None

    async def process_portfolio(self) -> List[TradingRecommendation]:
        """
        Process entire portfolio and generate recommendations

        Returns:
            List of trading recommendations
        """
        # Get current positions
        await self.ibkr.sync_portfolio()
        positions = self.ibkr.positions

        # Get tickers from portfolio
        portfolio_tickers = list(positions.keys())

        # Also analyze some high-opportunity tickers even if not in portfolio
        watchlist = ["NVDA", "TSLA", "AAPL", "MSFT", "AVGO"]
        all_tickers = list(set(portfolio_tickers + watchlist))

        # Get signals for all tickers
        await self.data_agg.aggregate_signals(all_tickers)

        # Process each ticker
        recommendations = []
        for ticker in all_tickers:
            logger.info(f"Processing {ticker}")
            rec = await self.process_signals(ticker)
            if rec and rec.action != 'HOLD':
                recommendations.append(rec)

        # Sort by confidence
        recommendations.sort(key=lambda x: x.confidence, reverse=True)

        logger.info(f"Generated {len(recommendations)} recommendations")
        return recommendations

    def format_recommendation(self, rec: TradingRecommendation) -> str:
        """
        Format recommendation for display

        Args:
            rec: Trading recommendation

        Returns:
            Formatted string
        """
        # Calculate percentage gains
        gain_1 = ((rec.target_price_1 - rec.current_price) / rec.current_price) * 100
        gain_2 = ((rec.target_price_2 - rec.current_price) / rec.current_price) * 100
        loss = ((rec.stop_loss - rec.current_price) / rec.current_price) * 100

        formatted = f"""
━━━━━━━━━━━━━━━━━━━━━━━
🎯 ACTION: {rec.action}
📈 TICKER: {rec.ticker}
💰 CURRENT: ${rec.current_price:.2f}
📍 ENTRY: ${rec.entry_price_min:.2f} - ${rec.entry_price_max:.2f}
🎯 TARGET 1: ${rec.target_price_1:.2f} ({gain_1:+.1f}%)
🎯 TARGET 2: ${rec.target_price_2:.2f} ({gain_2:+.1f}%)
🛑 STOP LOSS: ${rec.stop_loss:.2f} ({loss:.1f}%)
📊 CONFIDENCE: {rec.confidence:.0f}%
💼 POSITION SIZE: {rec.position_size:.1%} of portfolio
⚠️ RISK: {rec.risk_level}

📝 REASONING:
{rec.reasoning}

📅 Generated: {rec.timestamp.strftime('%Y-%m-%d %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━
        """
        return formatted


# Example usage
async def main():
    """Example of using the signal processor"""
    # Initialize components
    ibkr = IBKRConnector()
    data_agg = DataAggregator()
    processor = SignalProcessor(ibkr, data_agg)

    # Connect to IBKR (would need TWS running)
    # await ibkr.connect()

    # Process a single ticker
    rec = await processor.process_signals("NVDA")
    if rec:
        print(processor.format_recommendation(rec))


if __name__ == "__main__":
    asyncio.run(main())