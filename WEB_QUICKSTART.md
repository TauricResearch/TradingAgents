# TradingAgents Web App - Quick Start Guide

Get the web application running locally in 5 minutes.

## Prerequisites

- Python 3.10+ (or Docker)
- At least one API key:
  - OpenAI: https://platform.openai.com/api-keys
  - Anthropic: https://console.anthropic.com/keys
  - Google: https://ai.google.dev/tutorials/setup

## Option 1: Local Python (Recommended for Development)

### 1. Install Dependencies

```bash
pip install fastapi uvicorn
# or install full package
pip install -e .
```

### 2. Set API Key

```bash
export OPENAI_API_KEY=sk-your-key-here
# or
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Run Web App

```bash
python -m web.app
```

You'll see:
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Open in Browser

Visit: **http://localhost:8000**

## Option 2: Docker (Recommended for Production-like Testing)

### 1. Create .env File

```bash
# Copy example
cp .env.example .env

# Edit .env and add your API key
# OPENAI_API_KEY=sk-...
```

### 2. Run Web Service

```bash
# Build and run with Docker Compose (web service)
docker-compose up web

# Or build and run manually
docker build -t tradingagents-web .
docker run -e OPENAI_API_KEY=sk-... -p 8000:8000 tradingagents-web
```

### 3. Open in Browser

Visit: **http://localhost:8000**

## Option 3: Docker Compose (All Services)

```bash
# Setup .env file
cp .env.example .env
# Edit .env with your API keys

# Run all services
docker-compose up

# In another terminal, test health
curl http://localhost:8000/health

# View logs
docker-compose logs -f web
```

## Using the Web App

### 1. Configure Analysis

**Left Sidebar:**
- **Stock Ticker**: e.g., `AAPL`, `NVDA`, `0700.HK`, `BTC-USD`
- **Analysis Date**: When to analyze (historical)
- **LLM Provider**: OpenAI, Anthropic, Google, etc.
- **Deep Thinking Model**: Model to use (auto-selects best)
- **Select Analysts**: Choose which agents to run

### 2. Advanced Options

Click **Advanced Options** to adjust:
- **Temperature**: 0.0 (deterministic) to 1.0 (creative)
- **Debate Rounds**: How many rounds of debate (1-5)
- **Checkpoint Resume**: Enable crash recovery

### 3. Start Analysis

Click **Start Analysis** button.

### 4. Monitor Progress

**Real-time Updates:**
- Progress bar (0-100%)
- Agent activity feed
- Timestamped messages
- Status indicators

### 5. View Results

Once complete, see:
- **Ticker & Date**: What was analyzed
- **Trading Decision**: BUY/SELL/HOLD recommendation
- **Rationale**: Agent reasoning and evidence

## Example Analyses

### Quick Test (1-2 minutes)
```
Ticker: NVDA
Date: 2025-01-10
Provider: OpenAI
Model: gpt-4-mini  # Fast model
Analysts: Market, Sentiment only
Debate Rounds: 1
```

### Full Analysis (3-5 minutes)
```
Ticker: AAPL
Date: 2025-01-15
Provider: OpenAI
Model: gpt-5.5  # Reasoning model
Analysts: Market, Social, News, Fundamentals
Debate Rounds: 2
```

### Crypto Analysis (2-3 minutes)
```
Ticker: BTC-USD
Date: 2025-01-10
Provider: Anthropic
Model: claude-4-turbo
Analysts: Market, Sentiment
```

## Troubleshooting

### "Port 8000 already in use"
```bash
# Use different port
PORT=8001 python -m web.app

# Or kill existing process
lsof -i :8000
kill -9 <PID>
```

### "Module not found: web"
```bash
# Make sure you're in the repo root
cd /path/to/StrattonOak

# Or install in editable mode
pip install -e .
```

### "API key not found"
```bash
# Check environment variable is set
echo $OPENAI_API_KEY

# If empty, export it
export OPENAI_API_KEY=sk-...

# Then run app
python -m web.app
```

### "Connection refused" on browser
```bash
# Check if app is running
curl http://localhost:8000/health

# Check if port is open
netstat -an | grep 8000

# View app logs
# (check terminal where you ran python -m web.app)
```

### WebSocket connection fails
- Check browser console: F12 > Console tab
- Verify app is running: `curl http://localhost:8000/health`
- Try refreshing page
- Check firewall settings

### Analysis times out
- Long analyses use background tasks
- Check logs for API errors
- Verify API key is valid
- Try smaller subset of analysts

## Development Tips

### Enable Debug Mode

```bash
# In web/app.py, change:
# logging.basicConfig(level=logging.DEBUG)

# Or via environment
export LOG_LEVEL=DEBUG
```

### Test API Endpoints

```bash
# Get configuration
curl http://localhost:8000/api/config | jq

# Get health
curl http://localhost:8000/health

# Start analysis
curl -X POST http://localhost:8000/api/analyze/start \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "date": "2025-01-15",
    "config": {
      "llm_provider": "openai",
      "temperature": 0.5
    },
    "analysts": ["market"]
  }'
```

### View WebSocket Messages

```bash
# Use websocat (install via: cargo install websocat)
websocat ws://localhost:8000/ws/analyze/AAPL_1234567890

# Or use browser console in web app (see Network tab, WS filter)
```

## Files You Need

Essential files for the web app:

```
tradingagents/
  └── (main framework)

web/
  ├── app.py                  # FastAPI backend
  ├── __init__.py
  └── static/
      └── index.html          # Web UI

Dockerfile                     # Container config
docker-compose.yml            # Compose config
pyproject.toml               # Dependencies (fastapi, uvicorn added)
Procfile                      # Railway.com config
```

## Next Steps

### 1. Test Locally ✅
- [ ] Run web app
- [ ] Open http://localhost:8000
- [ ] Configure and run a test analysis

### 2. Deploy to Railway.com
See [DEPLOYMENT_RAILWAY.md](DEPLOYMENT_RAILWAY.md)

### 3. Customize
- Edit `web/static/index.html` for UI changes
- Update `web/app.py` for backend changes
- Add new endpoints as needed

### 4. Production Setup
- Use Railway.com or Docker host
- Set up monitoring/logging
- Configure auto-scaling if needed

## Common Tasks

### Change Port
```bash
# Local
PORT=9000 python -m web.app

# Docker
docker run -p 9000:8000 ...

# Docker Compose
docker-compose.yml: change ports: ["9000:8000"]
```

### Use Different LLM Provider
```bash
# Set default
export TRADINGAGENTS_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# Or select in UI
```

### Enable Checkpoint Resume
```bash
# Via UI: Check "Enable Checkpoint Resume"

# Or via env
export TRADINGAGENTS_CHECKPOINT_ENABLED=true
```

### View Analysis History
```bash
# Memory log (after analyses)
cat ~/.tradingagents/memory/trading_memory.md

# Cached data
ls ~/.tradingagents/cache/
```

## Performance Notes

- **First startup**: 2-3 seconds (Python load)
- **First analysis**: 10-20 seconds (model download/setup)
- **Subsequent analyses**: 2-5 minutes (LLM processing)
- **WebSocket update latency**: <100ms

## Security Notes

- **API Keys**: Stored in environment variables only
- **No secrets in code**: All config via env vars
- **No public API exposed**: Local/deployed instance only
- **CORS enabled**: For development (can restrict in production)

## Getting Help

### Documentation
- [DEPLOYMENT_RAILWAY.md](DEPLOYMENT_RAILWAY.md) - Railway.com setup
- [web/README.md](web/README.md) - Web app details
- [README.md](README.md) - Main project docs

### GitHub Issues
Report bugs: https://github.com/fawazzzbello/strattonoak/issues

### Local Testing
```bash
# Check all imports work
python -c "from web.app import app; print('OK')"

# Test core functionality
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('OK')"
```

---

**Ready?** Start with Option 1 or 2 above! 🚀
