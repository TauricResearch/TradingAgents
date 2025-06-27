#!/bin/bash

# TradingAgents Runner Script
# This script sets up the environment and runs TradingAgents with Anthropic

echo "🚀 Starting TradingAgents with Anthropic (Claude)..."
echo "================================================"

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env file..."
    export $(cat .env | xargs)
fi

# Check if Anthropic API key is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ Error: ANTHROPIC_API_KEY environment variable is not set!"
    echo "Please set it by:"
    echo "  1. Creating a .env file with: ANTHROPIC_API_KEY=your_key_here"
    echo "  2. Or export ANTHROPIC_API_KEY=your_key_here"
    exit 1
fi

# Activate virtual environment (bash/zsh shell)
source venv/bin/activate

echo "✅ Environment activated"
echo "✅ Anthropic API key loaded"
echo ""
echo "📝 When prompted, select:"
echo "   • LLM Provider: Anthropic"
echo "   • Quick Model: Claude Haiku 3.5"  
echo "   • Deep Model: Claude Sonnet 3.5"
echo ""
echo "🎯 Starting TradingAgents CLI..."
echo ""

# Run TradingAgents
python -c "from cli.main import app; app()" 