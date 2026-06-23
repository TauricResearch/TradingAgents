# TradingAgents Web Application

Modern web interface for the TradingAgents multi-agent financial trading framework.

## Features

✨ **Real-Time Analysis**
- Live WebSocket updates during analysis
- Progress tracking with detailed agent activity
- Streaming message log

🎨 **User-Friendly Interface**
- Responsive design (desktop, tablet, mobile)
- Intuitive configuration panel
- Beautiful result visualization

⚙️ **Flexible Configuration**
- Support for 9+ LLM providers
- Dynamic model selection per provider
- Advanced options: temperature, debate rounds, checkpoint resume
- Analyst selection (Market, Sentiment, News, Fundamentals)

🚀 **Production Ready**
- FastAPI backend with async support
- Docker containerization
- Railway.com deployment ready
- Health check endpoint

## Quick Start

### Local Development

```bash
# 1. Install dependencies
pip install fastapi uvicorn

# 2. Set API keys
export OPENAI_API_KEY=sk-...

# 3. Run the web app
python -m web.app

# 4. Open http://localhost:8000
```

### Docker

```bash
# Build
docker build -t tradingagents-web .

# Run
docker run -e OPENAI_API_KEY=sk-... -p 8000:8000 tradingagents-web

# Visit http://localhost:8000
```

### Railway.com Deployment

See [DEPLOYMENT_RAILWAY.md](../DEPLOYMENT_RAILWAY.md) for complete instructions.

## Directory Structure

```
web/
├── app.py              # FastAPI application
├── static/
│   └── index.html      # Web UI (HTML + CSS + JS)
└── README.md           # This file
```

## API Endpoints

### Web Interface
- `GET /` - Main web application

### Configuration
- `GET /api/config` - Get available providers, models, and analysts

### Analysis
- `POST /api/analyze/start` - Start a new analysis
- `GET /api/analyze/{id}` - Get analysis status
- `GET /api/analyze/{id}/messages` - Get analysis messages
- `WS /ws/analyze/{id}` - WebSocket for real-time updates

### Health
- `GET /health` - Health check

## Request Examples

### Start Analysis
```bash
curl -X POST http://localhost:8000/api/analyze/start \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "date": "2025-01-15",
    "config": {
      "llm_provider": "openai",
      "deep_think_llm": "gpt-5.5",
      "temperature": 0.7,
      "max_debate_rounds": 2
    },
    "analysts": ["market", "social", "news", "fundamentals"]
  }'
```

Response:
```json
{
  "analysis_id": "AAPL_1704067200",
  "status": "queued"
}
```

### Get Status
```bash
curl http://localhost:8000/api/analyze/AAPL_1704067200
```

### WebSocket Connection
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/analyze/AAPL_1704067200');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.type, data.data);
};
```

## Configuration Reference

### LLM Providers
- `openai` - OpenAI (GPT models)
- `google` - Google Gemini
- `anthropic` - Anthropic Claude
- `xai` - xAI Grok
- `deepseek` - DeepSeek
- `qwen` - Alibaba Qwen (International)
- `qwen-cn` - Alibaba Qwen (China)
- `glm` - Zhipu GLM (International)
- `glm-cn` - Zhipu GLM (China)
- `minimax` - MiniMax (Global)
- `minimax-cn` - MiniMax (China)
- `openrouter` - OpenRouter
- `ollama` - Local Ollama

### Analysts
- `market` - Market Analyst (technical indicators)
- `social` - Sentiment Analyst (StockTwits, Reddit)
- `news` - News Analyst (macroeconomic news)
- `fundamentals` - Fundamentals Analyst (financial statements)

## Environment Variables

```bash
# Required: At least one API key
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Optional: Port
PORT=8000

# Optional: Default configuration
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.5
TRADINGAGENTS_TEMPERATURE=0.7
TRADINGAGENTS_MAX_DEBATE_ROUNDS=2
```

See [DEPLOYMENT_RAILWAY.md](../DEPLOYMENT_RAILWAY.md) for complete environment variable reference.

## Frontend Features

### Real-Time Updates
- Live progress bar (0-100%)
- Agent activity feed with timestamps
- Color-coded messages (info, success, warning, error)
- Auto-scrolling message log

### Configuration Panel
- Ticker input with validation
- Date picker (defaults to today)
- Provider dropdown with auto-model loading
- Model selection based on provider
- Analyst multi-select with descriptions
- Advanced options (temperature, debate rounds, checkpoint)

### Results Display
- Trading decision summary
- Agent reasoning and rationale
- Structured JSON output
- Copy-paste ready format

## Performance Optimization

### Frontend
- Lightweight vanilla JavaScript (no frameworks)
- Efficient WebSocket message handling
- CSS grid for responsive layout
- Local storage for user preferences (future)

### Backend
- Async FastAPI handlers
- Background task execution
- Efficient message buffering
- Memory-efficient state management

## Known Limitations

1. **Single Instance**: Web app runs on single Railway instance
   - Max 2-3 concurrent analyses
   - Use Railway's auto-scaling for production

2. **State Persistence**: In-memory state (lost on restart)
   - Future: Add PostgreSQL for persistence
   - Analysis logs saved to `~/.tradingagents/memory/`

3. **Request Timeout**: 120-second timeout on requests
   - Long analyses use background tasks
   - WebSocket keeps connection open during analysis

## Troubleshooting

### "Module not found" Error
```bash
# Ensure imports work locally first
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph"
```

### API Key Not Recognized
```bash
# Check environment variable is set
echo $OPENAI_API_KEY

# Railway: Verify in Dashboard > Variables tab
# Local: Export before running
export OPENAI_API_KEY=sk-...
```

### WebSocket Connection Failed
- Check firewall/proxy settings
- Verify app is running (`curl http://localhost:8000/health`)
- Check browser console for errors (F12)

### Analysis Hangs
- Check LLM API quota/limits
- Verify internet connection
- Check Railway logs: `railway logs`

## Future Enhancements

- [ ] User authentication (GitHub OAuth)
- [ ] Persistent analysis history (PostgreSQL)
- [ ] Team collaboration features
- [ ] Analysis scheduling and automation
- [ ] Advanced charting (TradingView integration)
- [ ] Export results (PDF, CSV)
- [ ] Dark/light theme toggle
- [ ] Multi-language support
- [ ] Mobile app (React Native)

## Contributing

See main repository [CONTRIBUTING.md](../CONTRIBUTING.md) (if exists).

## License

Same as main TradingAgents repository.

## Support

- GitHub Issues: https://github.com/fawazzzbello/strattonoak/issues
- Deployment Help: See [DEPLOYMENT_RAILWAY.md](../DEPLOYMENT_RAILWAY.md)
- Documentation: See main [README.md](../README.md)
