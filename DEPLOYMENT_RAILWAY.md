# TradingAgents Web App - Railway.com Deployment Guide

This guide explains how to deploy the TradingAgents web application on Railway.com.

## Overview

The TradingAgents Web App is a modern FastAPI application with a responsive HTML/JS frontend. It allows users to:
- Configure and run multi-agent trading analysis via web browser
- Select LLM providers and models
- Choose analysis date and stock ticker
- Monitor analysis progress in real-time
- View detailed trading decisions and agent reasoning

## Prerequisites

1. **Railway.com Account**: Sign up at [railway.app](https://railway.app)
2. **GitHub Repository**: Push your code to GitHub
3. **API Keys**: Obtain keys for at least one LLM provider:
   - OpenAI: `OPENAI_API_KEY`
   - Anthropic: `ANTHROPIC_API_KEY`
   - Google: `GOOGLE_API_KEY`
   - Others as needed

## Deployment Steps

### 1. Connect GitHub Repository

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click **+ New Project**
3. Select **Deploy from GitHub**
4. Authorize Railway to access your GitHub account
5. Select the `fawazzzbello/strattonoak` repository
6. Select the `claude/affectionate-heisenberg-WkYmA` branch (or your feature branch)

### 2. Configure Environment Variables

Railway will automatically detect the Dockerfile. Before deploying, add environment variables:

1. In Railway Dashboard, go to your project
2. Click **Variables** tab
3. Add the following environment variables:

```bash
# Required: API Keys (choose at least one provider)
OPENAI_API_KEY=sk-...
# OR
ANTHROPIC_API_KEY=sk-ant-...
# OR
GOOGLE_API_KEY=...

# Optional: Default Configuration
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.5
TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4
TRADINGAGENTS_TEMPERATURE=0.7
TRADINGAGENTS_MAX_DEBATE_ROUNDS=2
TRADINGAGENTS_OUTPUT_LANGUAGE=en

# Optional: Port (Railway auto-assigns, but can override)
PORT=8000
```

### 3. Configure Railway Service

1. Click **Settings** tab
2. Under **Runtime**:
   - Ensure **Dockerfile** is selected as the build method
   - Python 3.12 should be auto-detected
3. Under **Deploy**:
   - Automatic deployment on push is enabled by default
   - Check **Restart on deploy** if desired

### 4. Deploy

The deployment will start automatically if auto-deploy is enabled. Otherwise:

1. Click **Deploy** button
2. Railway will:
   - Build the Docker image
   - Install dependencies
   - Run the application
3. Once complete, you'll see a public URL (e.g., `https://tradingagents-prod.up.railway.app`)

### 5. Access the Application

1. Click the **URL** button to open your deployed app
2. The web interface will load
3. Configure and run analyses!

## Application Architecture

### Backend (FastAPI)
- **Port**: 8000 (configurable via PORT env var)
- **Endpoints**:
  - `GET /` - Web UI
  - `GET /api/config` - Configuration options
  - `POST /api/analyze/start` - Start analysis
  - `GET /api/analyze/{id}` - Get status
  - `WS /ws/analyze/{id}` - Real-time updates
  - `GET /health` - Health check

### Frontend (HTML/JS)
- Responsive design (mobile-friendly)
- Real-time WebSocket updates
- Syntax-highlighted code display
- Progress tracking

## Performance Considerations

### Analysis Duration
- Typical analysis: 2-5 minutes (depending on LLM)
- Using reasoning models (GPT-5.5): 3-8 minutes
- Can be monitored via WebSocket

### Memory Usage
- Base: ~500MB
- Per-analysis: ~200-300MB
- Railway's default plan: 512MB RAM should be sufficient for light usage
- For production: Upgrade to 1GB+ RAM plan

### Concurrent Users
- Single Railway instance: ~2-3 concurrent analyses
- For more capacity: Use Railway's auto-scaling or upgrade plan

## Monitoring & Logs

### View Logs in Railway

1. In Railway Dashboard, click your project
2. Click **Logs** tab
3. Select **App Logs** to view application output
4. Filter by date/level as needed

### Common Issues

**Issue: "Module not found" error**
- Solution: Ensure `web/app.py` and `web/static/index.html` are pushed to GitHub

**Issue: API Key not recognized**
- Solution: Check environment variable name matches exactly
- Ensure Railway has been redeployed after adding keys

**Issue: Analysis timeout after 30 minutes**
- Railway: Web requests timeout at 120 seconds by default
- Solution: Use background tasks (included in implementation)

**Issue: Static files (CSS, JS) not loading**
- Solution: Ensure `index.html` is served correctly from `web/static/`
- Check web server logs: `docker logs <container>`

## Production Best Practices

### 1. Resource Limits
```bash
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1  # Reduce for faster analysis
TRADINGAGENTS_TEMPERATURE=0.5      # Lower for consistency
```

### 2. Caching
- Configure Redis for caching (optional):
  ```bash
  REDIS_URL=redis://...
  ```

### 3. Data Persistence
- Create a backup for `~/.tradingagents/memory/trading_memory.md`
- Consider using Railway's PostgreSQL add-on for production

### 4. Monitoring
- Set up alerts for failed analyses
- Monitor API rate limits for each LLM provider
- Track usage costs

## Scaling

### Vertical Scaling (More Powerful Instance)
1. In Railway Dashboard → Settings → Plan
2. Upgrade to higher RAM/CPU tier

### Horizontal Scaling (Multiple Instances)
1. Not recommended for single web server
2. For multi-instance: Use load balancer + database

## Troubleshooting

### Test Local Deployment First
```bash
# Build locally
docker build -t tradingagents-web .

# Run locally
docker run -e OPENAI_API_KEY=sk-... -p 8000:8000 tradingagents-web

# Visit http://localhost:8000
```

### SSH into Railway Container
```bash
railway shell
cd /home/appuser/app
python -m web.app
```

### Check Health
```bash
curl https://your-app.up.railway.app/health
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8000 | Web server port |
| `OPENAI_API_KEY` | - | OpenAI API key (required for GPT models) |
| `ANTHROPIC_API_KEY` | - | Anthropic API key (required for Claude) |
| `GOOGLE_API_KEY` | - | Google API key (required for Gemini) |
| `TRADINGAGENTS_LLM_PROVIDER` | openai | Default LLM provider |
| `TRADINGAGENTS_DEEP_THINK_LLM` | gpt-5.5 | Deep reasoning model |
| `TRADINGAGENTS_QUICK_THINK_LLM` | gpt-5.4 | Quick response model |
| `TRADINGAGENTS_TEMPERATURE` | 0.7 | Sampling temperature (0.0-1.0) |
| `TRADINGAGENTS_MAX_DEBATE_ROUNDS` | 2 | Debate rounds |
| `TRADINGAGENTS_CHECKPOINT_ENABLED` | false | Enable crash recovery |
| `TRADINGAGENTS_OUTPUT_LANGUAGE` | en | Output language |
| `TRADINGAGENTS_CACHE_DIR` | ~/.tradingagents/cache | Data cache directory |
| `TRADINGAGENTS_RESULTS_DIR` | ~/.tradingagents/logs | Results directory |
| `TRADINGAGENTS_MEMORY_LOG_PATH` | ~/.tradingagents/memory/trading_memory.md | Decision log |

## Advanced Configuration

### Custom Backend URL
For enterprise LLM providers:
```bash
TRADINGAGENTS_LLM_BACKEND_URL=https://your-llm-endpoint.com/v1
```

### Multi-Region Deployment
Railway supports multiple regions. For better latency:
1. Select region during project creation
2. Or use Railway's region selector in deployment settings

### Database Integration
Connect a Railway PostgreSQL database for:
- Persistent analysis history
- User authentication
- Team collaboration

```bash
# Railway auto-injects DATABASE_URL
# Update web/app.py to use it for persistent storage
```

## Cost Estimation

**Monthly costs on Railway.com:**
- Base (512MB RAM): ~$5
- LLM API calls: Varies by provider
  - OpenAI GPT-5.5: ~$0.03/analysis
  - Anthropic Claude: ~$0.01/analysis
  - Google Gemini: ~$0.001/analysis

**Example:** 100 analyses/month with GPT-5.5 = $3 API + $5 hosting = ~$8/month

## Support & Resources

- **Railway Docs**: https://docs.railway.app
- **TradingAgents Docs**: See README.md
- **API Reference**: See DEPLOYMENT_RAILWAY.md (this file)
- **GitHub Issues**: Report bugs to the repository

## Next Steps

1. ✅ Deploy to Railway
2. ✅ Test the web interface
3. ✅ Run your first analysis
4. ✅ Monitor performance
5. 📊 Customize for your use case

Happy trading! 🚀
