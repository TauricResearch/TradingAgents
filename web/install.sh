#!/usr/bin/env bash
set -euo pipefail

# TradingAgents Web Dashboard — One-Line Installer
# Usage: bash install.sh
#
# This installs the Next.js web dashboard for TradingAgents.
# Prerequisites: Node.js >= 18, Python 3.10+, and the tradingagents package installed.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║     TradingAgents Web Dashboard Setup     ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$SCRIPT_DIR"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v node &>/dev/null; then
  echo -e "${RED}Error: Node.js not found. Install Node.js >= 18 first.${NC}"
  echo "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
  echo "  sudo apt-get install -y nodejs"
  exit 1
fi

NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
  echo -e "${RED}Error: Node.js >= 18 required (found v$(node -v))${NC}"
  exit 1
fi

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo -e "${RED}Error: Python not found. Install Python 3.10+ first.${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Node.js $(node -v)${NC}"
echo -e "${GREEN}✓ Python $(python3 --version 2>/dev/null || python --version 2>/dev/null)${NC}"

# Check if tradingagents Python package is importable
if python3 -c "import tradingagents" 2>/dev/null || python -c "import tradingagents" 2>/dev/null; then
  echo -e "${GREEN}✓ TradingAgents Python package installed${NC}"
else
  echo -e "${YELLOW}⚠ TradingAgents Python package not found in current environment${NC}"
  echo -e "  Install it from the project root: ${CYAN}pip install .${NC}"
fi

# Install Node.js dependencies
echo ""
echo -e "${YELLOW}Installing web dashboard dependencies...${NC}"

cd "$WEB_DIR"
if command -v bun &>/dev/null; then
  echo -e "Using ${CYAN}bun${NC} package manager"
  bun install
elif command -v npm &>/dev/null; then
  echo -e "Using ${CYAN}npm${NC} package manager"
  npm install
else
  echo -e "${RED}Error: Neither bun nor npm found.${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Dependencies installed${NC}"

# Create data directory
mkdir -p "$WEB_DIR/.data/sessions"

# Copy .env.example if .env doesn't exist in project root
if [ ! -f "$PROJECT_ROOT/.env" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  echo -e "${YELLOW}Created .env from .env.example — add your API keys there${NC}"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓ TradingAgents Web Dashboard installed!        ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Start the dashboard:"
echo -e "    ${CYAN}cd web && bash start.sh${NC}"
echo ""
echo -e "  Or use npm/bun directly:"
echo -e "    ${CYAN}cd web && npm run dev${NC}"
echo ""
echo -e "  Open in browser: ${CYAN}http://localhost:3000${NC}"
echo ""
