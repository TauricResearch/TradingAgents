# TradingDesk

Native macOS app (SwiftUI) for the TradingAgents engine. It drives the engine
through a Dockerized FastAPI backend and presents a research workspace:
watchlist → decisions journal + run-document library → live agent theater.

Full design & feature documentation (architecture, every feature with its
rationale and implementation, the event protocol, and known constraints):
**[../../docs/TRADINGDESK.md](../../docs/TRADINGDESK.md)**.

## Quick start (dev)

```bash
# One-time: stable self-signed signing identity (avoids per-rebuild Keychain prompts)
bash scripts/dev-signing-setup.sh

# Backend (from the repo root)
docker compose build desk-server && docker compose up -d desk-server   # 127.0.0.1:8765

# Build + sign + launch the preview app
bash scripts/make-preview-app.sh && open .build/TradingDesk.app
```

Requirements: macOS 14+, Xcode 26 / Swift 6, Docker Desktop.
