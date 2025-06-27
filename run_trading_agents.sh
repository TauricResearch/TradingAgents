#!/bin/bash
# TradingAgents with Alternative AI Provider
# Usage: ./run_trading_agents.sh

export ANTHROPIC_API_KEY="your_key_here"  # Update this
# export GOOGLE_API_KEY="your_key_here"   # Or this for Google

cd "$(dirname "$0")"
source venv/bin/activate.fish
python -c "from cli.main import app; app()"
