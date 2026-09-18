#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${1:-8000}"
FRONTEND_PORT="${2:-5173}"

echo "=========================================================="
echo "   Starting TradingAgents Pro Multi-Agent Web Platform    "
echo "=========================================================="

# Activate virtualenv if available
if [ -f "/home/popeye/venv_tradingagents/bin/activate" ]; then
    source /home/popeye/venv_tradingagents/bin/activate
elif [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

echo "[1/2] Starting Backend on port $BACKEND_PORT..."
cd "$PROJECT_ROOT"
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload &
BACKEND_PID=$!

echo "[2/2] Starting Frontend on port $FRONTEND_PORT..."
cd "$PROJECT_ROOT/frontend"
npm run dev -- --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

echo ""
echo "✓ TradingAgents Pro platform running!"
echo "   Frontend UI:  http://localhost:$FRONTEND_PORT"
echo "   Backend API:  http://127.0.0.1:$BACKEND_PORT/docs"
echo "Press Ctrl+C to terminate both services."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true; exit 0" SIGINT SIGTERM
wait
