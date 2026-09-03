# TradingAgents Web Dashboard — Quick Start

## Option 1: Freebuff (Current)

The web dashboard is running on **port 3001** in this sandbox.
Freebuff manages the preview through its platform UI — the `freebuff-preview` CLI
is not available inside the sandbox itself.

To access the preview, look for the **Preview** panel in Freebuff.

---

## Option 2: Termux on Android Phone

Run the entire stack on your phone with Termux.

### One-line install (paste into Termux):

```bash
pkg install -y python nodejs git && pip install -e .. && cd web && npm install && bash launch.sh
```

### Or step-by-step:

```bash
# 1. Install prerequisites
pkg update -y
pkg install -y python nodejs git

# 2. Install TradingAgents Python package
cd ~/TradingAgents
pip install -e .

# 3. Install web dashboard
cd web
npm install

# 4. Set your API keys
nano ../.env
# Add: OPENAI_API_KEY=sk-...

# 5. Start the dashboard
bash launch.sh

# 6. Open in phone browser
# http://localhost:3000
```

### To expose to other devices:

```bash
# Find your phone's IP
ifconfig wlan0

# Other devices open: http://YOUR-IP:3000
```

### To expose to the internet (tunnel):

```bash
npx ngrok http 3000
# or
npx cloudflared tunnel --url http://localhost:3000
```

---

## Option 3: Desktop / Laptop

```bash
# Clone the repo
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents

# Install Python package
pip install -e .

# Setup web dashboard
cd web
npm install
cp ../.env.example ../.env   # edit with your keys
nano ../.env

# Start
bash start.sh
# Open: http://localhost:3000
```

---

## Option 4: Docker

```bash
# From the repo root
docker compose run --rm tradingagents

# Or build everything including the web dashboard
docker compose up
```

---

## Pages

| URL | Page |
|-----|------|
| `/dashboard` | Session overview with live status |
| `/new` | Configure & launch new analysis |
| `/run/[id]` | Live logs, agent events, decision |
| `/reports/[id]` | View generated markdown reports |
| `/settings` | Default LLM config & API keys |

## Requirements

- **Node.js** >= 18
- **Python** >= 3.10
- **TradingAgents** Python package installed (`pip install -e .`)
- At least one LLM API key in `.env`
