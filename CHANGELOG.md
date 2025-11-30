# Changelog - November 29, 2025

## 🚀 New Features

### 1. Stock Screening Agent
- **New Agent**: Created `tradingagents/agents/screening_agent.py`.
- **Purpose**: Identifies potential stock candidates ("Hidden Gems") for further analysis by the main Trading Graph.
- **Strategy**: Implemented an "Early Bird" multi-factor strategy:
    - **Social Hype**: Detects stocks trending on StockTwits and Reddit.
    - **Insider Activity**: Checks for recent buying by company executives.
    - **Technical Analysis**: Identifies Oversold conditions (RSI < 30) or Divergence.
    - **Catalysts**: Checks for upcoming earnings reports.

### 2. New Tools & Data Sources
- **`get_trending_social`**: New tool in `tradingagents/dataflows/social_sentiment.py` to fetch trending tickers from StockTwits and Ape Wisdom (Reddit).
- **`get_market_movers`**: Added to `tradingagents/dataflows/alpha_vantage_market.py` to find Top Gainers/Losers.
- **`get_earnings_calendar`**: Added to `tradingagents/dataflows/alpha_vantage_market.py`.
- **Integrated Tools**: Exposed `get_insider_transactions` and `get_indicators` to the Screening Agent.

### 3. Execution Workflow
- **`main_screening.py`**: Created a dedicated script to run the Screening Agent.
    - **Multi-Step Reasoning**: Implemented a loop allowing the agent to chain tool calls (e.g., Screen -> Check Social -> Recommend) before outputting a final decision.

## 🛠️ Infrastructure & Fixes

### Dataflow & Routing
- **`interface.py`**: 
    - Updated `TOOLS_CATEGORIES` and `VENDOR_METHODS` to support new tools.
    - **Fix**: Resolved a critical `SyntaxError` caused by a corrupted edit.
- **`agent_utils.py`**:
    - **Fix**: Restored file integrity after it was corrupted during an edit.
    - Added imports for all new screening tools.

### Configuration
- **`.gitignore`**: Corrected to ensure `tradingagents/` source code is tracked by Git (removed accidental exclusion).
- **Dependencies**: Added `python-dotenv` to `requirements.txt` and `setup.py`.

## 🧪 Verification
- Verified `main_screening.py` execution with the new loop logic.
- Confirmed fallback behavior for Social Sentiment tools (StockTwits -> Reddit).
