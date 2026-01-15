#!/bin/bash

# 0. Check & Start Claude Proxy
# Check if port 10909 is open (Proxy running) using pure bash TCP check
if ! (echo > /dev/tcp/localhost/10909) 2>/dev/null; then
    echo "🔌 Claude Proxy not detected on port 10909"
    echo "Select Proxy Provider:"
    echo "1) gemini (default)"
    echo "2) anthropic"
    read -p "Choice [1]: " choice
    case $choice in
        2) PROXY_TYPE="anthropic" ;;
        *) PROXY_TYPE="gemini" ;;
    esac

    echo "🔌 Starting Claude Proxy ($PROXY_TYPE)..."
    /home/prem/git/antigravity-claude-proxy/startProxy.sh "$PROXY_TYPE" &

    # Wait a moment for it to initialize with a progress bar
    echo -n "⏳ Initializing proxy: ["
    for i in {1..20}; do
        echo -n "■"
        sleep 0.1
    done
    echo "] 100% Ready!"
else
    echo "✅ Claude Proxy already running on port 10909"
fi

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
fi

# Check if keys are set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY is missing! Set it if using OpenAI."
fi

if [ -z "$GOOGLE_API_KEY" ]; then
    echo "⚠️  GOOGLE_API_KEY is missing! Set it if using Gemini."
fi

# Ensure Embedding URL is set (default to local TEI port 11434)
if [ -z "$EMBEDDING_API_URL" ]; then
    echo "ℹ️  Setting default EMBEDDING_API_URL to http://localhost:11434/v1"
    export EMBEDDING_API_URL="http://localhost:11434/v1"
    export EMBEDDING_MODEL="all-MiniLM-L6-v2"
fi

if [ -z "$EMBEDDING_TRUNCATION_LIMIT" ]; then
    export EMBEDDING_TRUNCATION_LIMIT=800
fi

# 3. Start the Trading Agents
echo "🚀 Starting Trading Agents..."
# Note: Debug print() statements will appear in the terminal
# Rich library's Live display handles the animated UI
# Note: Debug print() statements will appear in the terminal
# Rich library's Live display handles the animated UI
python3 run_agent.py "$@"

# 4. Open Reports
echo "📊 Searching for latest generated reports..."
# Find the latest "reports" directory by modification time (most recent last -> tail -1)
# Works by printing timestamp (%T@) and path (%p), sorting numerically, picking last, cleaning output
LATEST_REPORT_DIR=$(find results -type d -name "reports" -printf '%T@ %p\n' | sort -n | tail -1 | cut -f2- -d" ")

if [ -n "$LATEST_REPORT_DIR" ]; then
    echo "✅ Found reports in: $LATEST_REPORT_DIR"
    
    # Generate HTML Dashboard
    echo "🎨 Generating Report Dashboard..."
    python3 scripts/generate_report_html.py "$LATEST_REPORT_DIR"
    
    REPORT_HTML="$LATEST_REPORT_DIR/index.html"
    
    # Check if xdg-open exists (Linux)
    if [ -f "$REPORT_HTML" ] && command -v xdg-open &> /dev/null; then
        echo "🌐 Opening dashboard in browser..."
        xdg-open "$REPORT_HTML" &> /dev/null &
    else
        echo "ℹ️  Dashboard generated at:"
        echo "   file://$(pwd)/$REPORT_HTML"
    fi
else
    echo "⚠️  No reports found to open."
fi
