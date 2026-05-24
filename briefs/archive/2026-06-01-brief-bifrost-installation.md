# Brief: Install and Configure BiFrost for TradingAgents

**Date**: 2026-06-01
**Status**: Draft
**Author**: ses_d63d0c
**Audience**: Corporate IT, developers evaluating AI gateway infrastructure

## Objective

Install and configure [BiFrost](https://github.com/maximhq/bifrost) (Maxim AI Gateway) as the local routing layer for TradingAgents. Demonstrate granular cost control: per-call spend limits, semantic caching, provider failover, and local cost logging for corporate compliance.

## Background

BiFrost is an enterprise AI gateway from Maxim (Apache 2.0, Go) that provides:

- **23+ provider support**: OpenAI, Anthropic, AWS Bedrock, Google Vertex, Azure, Ollama, Groq, Cohere, Mistral, Cerebras, and more
- **OpenAI-compatible API**: drop-in replacement, zero code changes to existing apps
- **Semantic caching**: intelligent response caching based on prompt similarity
- **Automatic failover**: seamless provider switching on errors/latency
- **Budget management**: virtual keys, team budgets, per-model spend limits
- **SSO**: Google and GitHub authentication for team deployments
- **Observability**: Prometheus metrics, distributed tracing, JSONL cost logging
- **Performance**: <11µs overhead at 5k RPS

TradingAgents currently routes directly to OpenRouter with no local cost tracking. BiFrost adds control without replacing the provider.

## Scope

1. Install BiFrost locally (npx or Docker)
2. Configure OpenRouter as the primary provider
3. Configure Ollama as a zero-cost fallback
4. Set up routing policies: logical model names → provider routes
5. Enable cost logging to `~/.tradingagents/bifrost-cost-log.jsonl`
6. Integrate with TradingAgents (`analyze_stream.py`)
7. Verify: run a COP analysis and confirm cost log output

**Out of scope:**
- Production deployment (Kubernetes, secrets management, multi-node)
- SSO configuration for team deployments
- Prometheus/alerting stack
- Cluster mode

---

## Step 1: Install Ollama (Optional — Zero-Cost Routing)

For zero-cost routing of draft/review tasks to local models:

```bash
# macOS
brew install ollama

# Start Ollama in the background
ollama serve &

# Pull cost-effective models for draft tasks
ollama pull deepseek-coder-v2:latest
ollama pull qwen2.5-coder:32b-instruct
```

Verify Ollama is running:
```bash
curl http://localhost:11434/api/tags
```

---

## Step 2: Install BiFrost

**Option A: NPX (fastest, no Docker required)**

```bash
# Start BiFrost on port 8080
npx -y @maximhq/bifrost
```

**Option B: Docker (recommended for reproducibility)**

```bash
docker run -d \
  --name bifrost \
  -p 8080:8080 \
  -v ~/.tradingagents/bifrost-data:/app/data \
  --restart unless-stopped \
  maximhq/bifrost
```

**Option C: Go SDK (for embedded deployment)**

```bash
go get github.com/maximhq/bifrost/core
```

---

## Step 3: Open the Web UI

BiFrost includes a built-in web interface for configuration and monitoring.

```bash
open http://localhost:8080
```

The web UI allows you to:
- Add/manage provider credentials (API keys)
- Configure routing policies
- View real-time request logs and cost analytics
- Set up budget alerts

---

## Step 4: Configure OpenRouter Provider

In the BiFrost web UI:

1. Navigate to **Settings → Providers**
2. Add OpenRouter:
   - **Provider**: OpenRouter
   - **API Key**: `sk-or-v1-...` (your OpenRouter key)
   - **Default**: ✓

Or configure via the config file (`~/.tradingagents/bifrost.yaml`):

```yaml
providers:
  openrouter:
    provider: openrouter
    api_key: ${OPENROUTER_API_KEY}
    models:
      - deepseek/deepseek-v4-flash
      - deepseek/deepseek-r1
      - qwen/qwen3-30b-a3b-thinking-2507
      - openai/gpt-5.4
      - openai/gpt-5.4-mini

  ollama:
    provider: openai
    base_url: http://localhost:11434/v1
    api_key: ollama  # dummy key
    models:
      - deepseek-coder-v2:latest
      - qwen2.5-coder:32b-instruct
```

---

## Step 5: Configure Routing Policies

Map logical model names to provider routes. In BiFrost web UI:

1. Navigate to **Settings → Routing**
2. Create route policies:

| Route Name | Model Pattern | Provider | Max Spend/Call |
|-------------|--------------|----------|----------------|
| `deep_think` | `analysis/*` | openrouter | $0.50 |
| `quick_think` | `fast/*` | openrouter | $0.20 |
| `draft` | `draft/*` | ollama | $0.00 |
| `fallback` | `*` | ollama | $0.00 |

Or via config:

```yaml
routing:
  routes:
    - name: deep_think
      models:
        - deep_think
        - analysis
      provider: openrouter
      model_mapping:
        deep_think: deepseek/deepseek-v4-flash
      max_cost_per_request: 0.50

    - name: quick_think
      models:
        - quick_think
        - fast
      provider: openrouter
      model_mapping:
        quick_think: deepseek/deepseek-v4-flash
      max_cost_per_request: 0.20

    - name: draft
      models:
        - draft
        - review
      provider: ollama
      model_mapping:
        draft: deepseek-coder-v2:latest
      max_cost_per_request: 0.00  # local, no cost

    - name: fallback
      models:
        - "*"
      provider: ollama
      model_mapping:
        fallback: qwen2.5-coder:32b-instruct
      max_cost_per_request: 0.00
```

---

## Step 6: Enable Cost Logging

Configure BiFrost to write request logs locally:

```yaml
logging:
  enabled: true
  format: jsonl
  output: ~/.tradingagents/bifrost-cost-log.jsonl
  fields:
    - timestamp
    - model
    - provider
    - prompt_tokens
    - completion_tokens
    - total_tokens
    - cost_usd
    - latency_ms
    - status
    - cache_hit
```

Restart BiFrost after config changes.

---

## Step 7: Integrate with TradingAgents

Update `scripts/py/analyze_stream.py` to route through BiFrost:

```python
# ── BiFrost Routing Configuration ─────────────────────────────────────────
# BiFrost runs locally on port 8080, presenting an OpenAI-compatible API.
# Logical model names (deep_think, quick_think) are resolved by BiFrost routing
# policies to actual provider models, with cost logging and spend enforcement.

config = DEFAULT_CONFIG.copy()

# Route through BiFrost (OpenAI-compatible endpoint)
config["llm_provider"] = "openai"
config["llm_api_base"] = "http://localhost:8080/v1"   # BiFrost proxy

# Logical model names — resolved by BiFrost routing policies
config["deep_think_llm"] = "deep_think"   # → deepseek/deepseek-v4-flash via openrouter
config["quick_think_llm"] = "quick_think" # → deepseek/deepseek-v4-flash via openrouter

# OPENROUTER_API_KEY is passed through BiFrost to the upstream provider
```

### Environment Variables

```bash
export OPENROUTER_API_KEY=sk-or-v1-...   # Required for OpenRouter routes
export BIFROST_BASE_URL=http://localhost:8080/v1  # Optional, for explicit configuration
```

---

## Step 8: Verification

### 8.1 Health Check

```bash
curl http://localhost:8080/health
# → {"status": "ok", "providers": ["openrouter", "ollama"]}
```

### 8.2 Test Routing

```bash
# Test OpenRouter route through BiFrost
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deep_think",
    "messages": [{"role": "user", "content": "What is the ticker for Apple?"}]
  }'

# Test Ollama route (zero cost)
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "draft",
    "messages": [{"role": "user", "content": "Summarize this: The market fell 2% today."}]
  }'
```

### 8.3 Run TradingAgents Analysis

```bash
cd /Users/petersmith/Dev/GitHub/TradingAgents
PYTHONUNBUFFERED=1 python3 scripts/py/analyze_stream.py COP --debates 1
```

### 8.4 Check Cost Log

```bash
cat ~/.tradingagents/bifrost-cost-log.jsonl | python3 -c "
import json, sys
total = 0.0
for line in sys.stdin:
    row = json.loads(line)
    cost = row.get('cost_usd', 0)
    total += cost
    cache = '(CACHED)' if row.get('cache_hit') else ''
    print(f\"{row['timestamp']} | {row['model']:25s} | \${cost:>6.4f} | {row['provider']:12s} {cache}\")
print(f\"\nTotal cost: \${total:.4f}\")
"
```

Expected output (example):
```
2026-06-01T14:23:01Z | deep_think                | $ 0.0012 | openrouter
2026-06-01T14:23:15Z | quick_think               | $ 0.0008 | openrouter
2026-06-01T14:23:28Z | deep_think                | $ 0.0000 | openrouter     (CACHED)
2026-06-01T14:23:45Z | draft                     | $ 0.0000 | ollama

Total cost: $0.0020
```

### 8.5 Verify Spend Limit Enforcement

Test that BiFrost rejects calls that exceed configured spend limits:

```bash
# Temporarily lower the spend limit in routing config:
#   max_cost_per_request: 0.0001  # $0.0001 per call

curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deep_think",
    "messages": [{"role": "user", "content": "Explain quantum computing in detail..."}]
  }'

# Expected: HTTP 429 with spend limit exceeded error
```

---

## Corporate Compliance Features

BiFrost provides features relevant to corporate environments:

| Feature | Corporate Benefit |
|---------|-------------------|
| **Local cost logging** | Audit trail lives in the organization, not with the provider |
| **Virtual keys** | Segregate API access by team/project with separate billing |
| **Spend limits per key** | Hard caps prevent runaway spend in automated systems |
| **SSO (Google/GitHub)** | Integrate with corporate identity providers |
| **Prometheus metrics** | Wire into existing monitoring infrastructure |
| **Private deployment** | No data leaves the corporate network |
| **Vault integration** | Pull API keys from HashiCorp Vault, not env vars |
| **MCP gateway** | Enable models to use external tools (filesystem, DBs) via Model Context Protocol |

---

## Cost Model

BiFrost doesn't reduce per-token pricing — it adds control:

| Model | Direct OpenRouter | Via BiFrost | Benefit |
|-------|-------------------|-------------|---------|
| `deepseek/deepseek-v4-flash` | $0.0001/1K prompt | $0.0001/1K prompt | Cost log, spend limits |
| `deepseek/deepseek-r1` | $0.0007/1K prompt | $0.0007/1K prompt | Automatic failover |
| Ollama local models | N/A | $0.00 (local) | Zero-cost drafts |
| Cached requests | N/A | $0.00 | Semantic cache hit |
| GPT-5.4 | $0.0025/1K prompt | Routable via policy | Spend caps apply |

---

## Post-Installation Checklist

- [ ] BiFrost running on `localhost:8080`
- [ ] `curl localhost:8080/health` returns `{"status": "ok"}`
- [ ] OpenRouter provider configured in BiFrost web UI
- [ ] Ollama provider configured (if using local models)
- [ ] Routing policies created: `deep_think`, `quick_think`, `draft`, `fallback`
- [ ] Cost logging enabled → `~/.tradingagents/bifrost-cost-log.jsonl` created
- [ ] Test routing: OpenRouter and Ollama routes both work
- [ ] COP analysis completes through BiFrost
- [ ] Cost log has entries with `cost_usd`, `cache_hit`, `latency_ms`
- [ ] Spend limit enforcement verified (optional)

## Success Criteria

- [ ] Full COP analysis generates < $0.01 in OpenRouter costs (via DeepSeek V4 Flash)
- [ ] Cost log shows all model calls with token counts and USD cost
- [ ] Local Ollama models route at zero cost
- [ ] Semantic cache returns `$0.00` for duplicate prompts
- [ ] Spend limit of $0.01 per call causes the analysis to fail gracefully with a clear 429 error

## Next Steps

1. **Install BiFrost and run verification** — test the integration on `feat/code-registry`
2. **Update `analyze_stream.py`** — add `--bifrost` flag to enable BiFrost routing via environment variable
3. **Build a cost dashboard view** — parse `bifrost-cost-log.jsonl` and display per-model spend in the TradingAgents dashboard
4. **Corporate IT playbook** — document steps for locked-down environments (no internet, SSO required, Vault integration)
5. **Test semantic caching** — verify cache hit rate on repeated analyses
6. **Test provider failover** — simulate OpenRouter outage, verify BiFrost falls back to Ollama

## Troubleshooting

**BiFrost won't start:**
```bash
# Check port 8080 is free
lsof -i :8080

# Try a different port
npx -y @maximhq/bifrost --port 8081
```

**"Provider not configured" error:**
- Add OpenRouter API key in the BiFrost web UI → Settings → Providers
- Or set `OPENROUTER_API_KEY` environment variable

**Ollama route returns 500:**
- Ensure Ollama is running: `ollama serve`
- Ensure model is pulled: `ollama list`

**Cost log not writing:**
- Check file permissions: `touch ~/.tradingagents/bifrost-cost-log.jsonl`
- Ensure logging is enabled in config

## References

- **BiFrost GitHub**: https://github.com/maximhq/bifrost
- **BiFrost Docs**: https://docs.getbifrost.ai
- **BiFrost Enterprise**: https://www.getmaxim.ai/bifrost/enterprise
- Decision: `decisions/006-bifrost-local-ai-router.md`
- TradingAgents: `scripts/py/analyze_stream.py`
---

## Working Implementation: TypeScript/Bun Proxy

A production-ready TypeScript proxy is implemented in `scripts/bifrost-proxy.ts`. This was verified end-to-end with a COP TradingAgents analysis on 2026-05-13.

**Verified results:**
- 39 API calls routed through proxy → OpenRouter
- Total cost: $0.00002 (~$0.02 per 1,000 calls via DeepSeek V4 Flash)
- All TradingAgents agents worked: market, news, fundamentals, debate, trader
- Decision: **Hold** (COP)

**Start proxy:**
```bash
OPENROUTER_API_KEY="$(skate get open_api_key)" \
BIFROST_PROVIDER=openrouter \
bun run scripts/bifrost-proxy.ts
```

**Run analysis through proxy:**
```bash
OPENROUTER_API_KEY="$(skate get open_api_key)" \
python3 scripts/py/analyze_stream.py COP --debates 1 \
  --llm-api-base "http://localhost:8080/v1"
```

**Check cost log:**
```bash
curl http://localhost:8080/costs
# → {"total_cost": 0.00002, "total_requests": 39, ...}
```

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/costs` | Cost summary (total, by model) |
| POST | `/v1/chat/completions` | OpenAI Chat Completions proxy |
| POST | `/v1/responses` | OpenAI Responses API proxy |
| GET | `/v1/models` | Model list |

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | Required for OpenRouter routes |
| `BIFROST_PROVIDER` | `openrouter` | `openrouter` \| `ollama` \| `direct` |
| `BIFROST_DRY_RUN` | `0` | Set to `1` to log without forwarding |
| `BIFROST_SPEND_LIMIT` | `1.00` | Max USD per request |
| `BIFROST_COST_LOG` | `~/.tradingagents/bifrost-cost-log.jsonl` | Cost log path |
