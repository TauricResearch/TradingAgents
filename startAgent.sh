#!/bin/bash
/home/prem/git/antigravity-claude-proxy/startProxy.sh &

./startEmbedding.sh

# 1. Activate Virtual Environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✅ Virtual Environment (.venv) Activated"
else
    echo "❌ Virtual Environment not found! Run 'uv venv --python 3.13' first."
    exit 1
fi

# 2. Export API Keys (PLACEHOLDERS - PLEASE UPDATE)
# You can also load these from a .env file if preferred
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
    echo "✅ Loaded keys from .env"
else
    echo "⚠️  No .env file found. Using default/exported keys."
    # START: REPLACE WITH YOUR ACTUAL KEYS IF NOT USING .ENV
    # export OPENAI_API_KEY="sk-your-key-here"
    # export ALPHA_VANTAGE_API_KEY="your-key-here"
    # export GOOGLE_API_KEY="your-key-here"
    # END
fi

# Check if keys are set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY is missing! Set it if using OpenAI."
fi

if [ -z "$GOOGLE_API_KEY" ]; then
    echo "⚠️  GOOGLE_API_KEY is missing! Set it if using Gemini."
fi

# 3. Start the Shadow Run (Daily Execution)
echo "🚀 Starting Shadow Run Daily Execution..."
python3 -m cli.main
