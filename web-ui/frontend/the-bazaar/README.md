# The Bazaar — TradingAgents Alternative UI Prototype

A character-driven conversational trading interface. Summon your analyst team, watch them debate in real-time as distinct personas, and receive a dramatic verdict on your trade.

## Quick Start

```bash
# Make sure the TradingAgents backend is running first:
cd /Users/zachb/Desktop/TradingAgents/web-ui
bash start.sh

# Then open the prototype:
open /path/to/the-bazaar/index.html
# OR serve with any static file server:
python3 -m http.server 8081
# then visit http://localhost:8081
```

The prototype connects to the existing TradingAgents API at `http://localhost:8000` by default. Set `?api=http://other-host:8000` to change the backend URL.

## Design System

**The Bazaar** is the recommended primary UI concept from the TradingAgents redesign project. Key principles:

- **Warm, inviting atmosphere** — amber/gold on dark earth tones
- **Character-driven** — each analyst is a distinct persona with avatar, color, and voice
- **Conversational** — analysis unfolds as a chat between agents and user
- **Lively animations** — typing indicators, entrance animations, dramatic verdict reveals

## Design Tokens

| Token | Value | Usage |
|-------|-------|-------|
| Background | `#1A1410` | Page background |
| Surface | `#241C14` | Cards, panels |
| Elevated | `#2D241A` | Raised elements |
| Primary | `#E8A840` | Actions, accents |
| Border | `#3D3226` | Dividers |

## Agent Personas

| # | Character | Role | Color | Avatar |
|---|-----------|------|-------|--------|
| 1 | Flint | Market Analyst | `#8B6B4A` | 🐂 |
| 2 | Vera | Sentiment Analyst | `#C44B4B` | 🔮 |
| 3 | Reed | News Analyst | `#4B7A9E` | 📜 |
| 4 | Sage | Fundamentals Analyst | `#5C8A6F` | 📊 |
| 5 | Balthazar | Investment Debater | `#D4A030` | ⚖️ |
| 6 | Morwen | Risk Debater | `#7B8B9A` | 🛡️ |
| 7 | Kael | Trader | `#C07840` | 🏃 |
| 8 | Elder Aldric | Judge | `#9B8BAA` | 👑 |

## Flow

```
Bazaar Input → Debate Hall (SSE stream) → The Ledger (Verdict)
```

## Structure

```
the-bazaar/
├── README.md          # This file
└── index.html         # Self-contained React SPA (CDN deps)
```

## Integration

To integrate into the existing TradingAgents repo:

```bash
cp -r the-bazaar /Users/zachb/Desktop/TradingAgents/web-ui/frontend/the-bazaar/
```

The existing backend (FastAPI at `web-ui/backend/main.py`) serves this prototype automatically if placed under the static files mount point.
