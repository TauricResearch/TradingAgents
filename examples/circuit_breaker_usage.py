"""
Example: Apply circuit breaker to external API calls in TradingAgents
======================================================================

Usage:
    @with_circuit("yfinance", failure_threshold=5, recovery_timeout=60)
    def fetch_yfinance_data(ticker: str):
        ...

    @with_circuit("alpaca", failure_threshold=5, recovery_timeout=60)
    async def fetch_alpaca_news(ticker: str):
        ...
"""

# Example decorators to add to your existing dataflow methods:

# 1. YFinance data calls
# @with_circuit("yfinance", failure_threshold=5, recovery_timeout=60)
# def get_stock_data(self, ticker: str, period: str = "1y"):
#     ...

# 2. Alpaca news/data calls
# @with_circuit("alpaca", failure_threshold=5, recovery_timeout=60)
# async def get_news_sentiment(ticker: str):
#     ...

# 3. Alpha Vantage calls
# @with_circuit("alphavantage", failure_threshold=3, recovery_timeout=30)
# async def get_technical_indicators(ticker: str):
#     ...

# 4. LLM provider calls (OpenAI, Anthropic, Google)
# @with_circuit("openai", failure_threshold=3, recovery_timeout=30)
# async def chat_with_openai(messages: list):
#     ...

# Add these imports to the top of your dataflow files:
# from tradingagents.default_config import with_circuit, CircuitBreakerError
# OR copy the circuit breaker code from sharkquant/src/utils/circuit_breaker.py

print("Circuit breaker examples ready - see comments in this file")
