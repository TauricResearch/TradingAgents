#!/usr/bin/env bash
set -euo pipefail

# ╔════════════════════════════════════════════════════════════╗
# ║  TradingAgents Web — Termux Phone Setup                   ║
# ║  Run this inside Termux on your Android phone             ║
# ╚════════════════════════════════════════════════════════════╝

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║  TradingAgents — Termux Phone Setup       ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# Step 1: Install Termux packages
echo -e "${YELLOW}[1/6] Installing Termux packages...${NC}"
pkg update -y
pkg install -y python nodejs git binutils

# Step 2: Install Python tools
echo -e "${YELLOW}[2/6] Setting up Python environment...${NC}"
pip install --upgrade pip setuptools wheel

# Step 3: Install TradingAgents Python package
echo -e "${YELLOW}[3/6] Installing TradingAgents Python package...${NC}"
if [ -f "../pyproject.toml" ]; then
  cd ..
  pip install -e .
  cd web
elif [ -f "pyproject.toml" ]; then
  pip install -e .
fi

# Step 4: Install web dashboard dependencies
echo -e "${YELLOW}[4/6] Installing web dashboard (Node.js)...${NC}"
npm install

# Step 5: Setup .env
echo -e "${YELLOW}[5/6] Configuring environment...${NC}"
if [ ! -f "../.env" ] && [ -f "../.env.example" ]; then
  cp ../.env.example ../.env
  echo -e "${YELLOW}Created .env — edit it with your API keys:${NC}"
  echo -e "  ${CYAN}nano ../.env${NC}"
fi

mkdir -p .data/sessions

# Step 6: Create launch script
echo -e "${YELLOW}[6/6] Creating launch script...${NC}"

cat > launch.sh << 'LAUNCH'
#!/usr/bin/env bash
# TradingAgents Web — Launch in Termux
# Usage: bash launch.sh

cd "$(dirname "$0")"

export HOSTNAME="0.0.0.0"
export PORT="${PORT:-3000}"

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║  TradingAgents Web Dashboard              ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""
echo "  Starting on http://localhost:${PORT}"
echo "  Open this URL in your phone browser"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

npx next dev -p "$PORT" -H 0.0.0.0
LAUNCH
chmod +x launch.sh

echo ""
echo -e "${GREEN}${BOLD}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║  ✓ Setup complete!                               ║${NC}"
echo -e "${GREEN}${BOLD}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Quick start:${NC}"
echo -e "    ${CYAN}bash launch.sh${NC}"
echo ""
echo -e "  ${BOLD}Open in your phone browser:${NC}"
echo -e "    ${CYAN}http://localhost:3000${NC}"
echo ""
echo -e "  ${BOLD}Set your API keys:${NC}"
echo -e "    ${CYAN}nano ../.env${NC}"
echo ""
echo -e "  ${BOLD}To run from another device on your network:${NC}"
echo -e "    Find your phone IP: ${CYAN}ifconfig${NC}"
echo -e "    Open: ${CYAN}http://YOUR-IP:3000${NC}"
echo ""
echo -e "  ${BOLD}For port forwarding (access from anywhere):${NC}"
echo -e "    Use ${CYAN}ngrok${NC} or ${CYAN}cloudflared${NC}:"
echo -e "    ${CYAN}npx ngrok http 3000${NC}"
echo ""
