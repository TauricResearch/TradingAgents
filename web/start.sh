#!/usr/bin/env bash
set -euo pipefail

# TradingAgents Web Dashboard — Start Script
# Usage: bash start.sh [dev|prod]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-dev}"

# Ensure data directory exists
mkdir -p .data/sessions

echo "  ╔═══════════════════════════════════════════╗"
echo "  ║     TradingAgents Web Dashboard           ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

if [ "$MODE" = "prod" ]; then
  echo "Building for production..."
  if command -v bun &>/dev/null; then
    bun run build
  else
    npm run build
  fi
  echo "Starting production server on port 3000..."
  export HOSTNAME="0.0.0.0"
  export PORT="3000"
  exec node .next/standalone/server.js 2>/dev/null || npm start
else
  echo "Starting development server on http://localhost:3000..."
  export HOSTNAME="0.0.0.0"
  export PORT="3000"
  if command -v bun &>/dev/null; then
    exec bun run dev
  else
    exec npm run dev
  fi
fi
