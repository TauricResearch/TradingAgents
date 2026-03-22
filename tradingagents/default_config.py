# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "anthropic",
    "deep_think_llm": "claude-sonnet-4-6",
    "quick_think_llm": "claude-haiku-4-5-20251001",
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "dart_data": "opendart",             # Options: opendart
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Investment persona configuration
    # Options: None, "warren_buffett", "ray_dalio", "peter_lynch"
    "persona": None,
    # Broker execution configuration
    "broker": {
        "enabled": False,  # Master switch for trade execution
        "provider": "kis",  # Broker provider: "kis"
        "mode": "paper",  # "paper" (모의투자) or "real" (실투자)
        "kis_app_key": None,  # KIS APP_KEY (or env: KIS_APP_KEY)
        "kis_app_secret": None,  # KIS APP_SECRET (or env: KIS_APP_SECRET)
        "kis_account_no": None,  # Account number "XXXXXXXX-XX" (or env: KIS_ACCOUNT_NO)
        "default_order_type": "market",  # "market" or "limit"
        "default_quantity": None,  # Fixed quantity per trade (None = use percentage)
        "default_position_pct": 0.05,  # 5% of portfolio per trade
        "safety": {
            "max_position_pct": 0.10,  # Max 10% of portfolio in one stock
            "max_order_amount": 5_000_000,  # Max 5M KRW per order
            "daily_loss_limit": -500_000,  # Stop trading if daily loss exceeds 500K KRW
            "enforce_market_hours": True,  # Only trade during KRX hours (09:00-15:30)
            "require_confirmation": True,  # Prompt before real trades
        },
    },
}
