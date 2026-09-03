#!/usr/bin/env bash
cd "$(dirname "$0")"

export HOSTNAME="0.0.0.0"
export PORT="${PORT:-3000}"

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║  TradingAgents Web Dashboard              ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""
echo "  Starting on http://localhost:${PORT}"
echo "  Press Ctrl+C to stop"
echo ""

npx next dev -p "$PORT" -H 0.0.0.0
