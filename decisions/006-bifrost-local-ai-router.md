# Decision: BiFrost as Local AI Router for Cost Control

**Date**: 2026-06-01
**Status**: Active
**Author**: ses_d63d0c

## Context

TradingAgents makes heavy use of LLM calls across multiple agents (market, news, fundamentals, sentiment, trader, risk). Each analysis run generates dozens of API calls via OpenRouter. Currently:

- No local routing layer — all calls go directly to OpenRouter
- Cost visibility is limited to the OpenRouter dashboard (manual, post-hoc)
- No strategic routing — cheap models for drafts, expensive models for final decisions
- No spend limits, caching, or failover at the application layer

**BiFrost** (https://github.com/maximhq/bifrost) is an enterprise AI gateway from Maxim. Key characteristics:
- Go-based, Apache 2.0, <11µs overhead at 5k RPS
- 23+ providers: OpenAI, Anthropic, AWS Bedrock, Google Vertex, Azure, Ollama, Groq, Cohere, Mistral, Cerebras, and more
- Built-in web UI for configuration and monitoring
- Semantic caching, automatic fallbacks, load balancing
- Budget management: virtual keys, team budgets, per-model spend limits
- SSO (Google, GitHub), Prometheus metrics, MCP gateway support

## Decision

**Adopt BiFrost as the local AI routing layer for TradingAgents.**

1. BiFrost runs locally on `localhost:8080` as a drop-in OpenAI-compatible proxy
2. TradingAgents routes LLM calls through BiFrost instead of directly to OpenRouter
3. BiFrost handles provider failover, semantic caching, and spend enforcement
4. Cost logs are written locally for reconciliation
5. OpenRouter remains the primary paid provider; BiFrost provides the control plane

## Architecture

```
┌──────────────────────────────────┐
│  TradingAgents                   │
│  (analyze_stream.py)             │
│  base_url → localhost:8080/v1    │
└──────────────┬───────────────────┘
               │ OpenAI-compatible API
               ▼
┌──────────────────────────────────┐
│  BiFrost (local)                 │
│  localhost:8080                  │
│  ┌─ Web UI (visual config)      │
│  ┌─ Semantic Cache              │
│  ├─ Spend Limits / Budgets       │
│  ├─ Provider Failover           │
│  └─ Cost Logging (JSONL)        │
└──────────────┬───────────────────┘
               │
    ┌──────────┼──────────────────────┐
    ▼          ▼                      ▼
 OpenRouter   Ollama              Direct APIs
 (paid)       (free, local)        (fallback)
```

## Rationale

**For a local router:**
- **Cost visibility**: every call logged with token count, model, provider, cost, latency
- **Strategic routing**: map logical model names → provider routes (cheap for drafts, expensive for analysis)
- **Spend enforcement**: hard caps per call, per model, per budget — circuit breakers, not post-hoc dashboards
- **Semantic caching**: duplicate prompts return cached responses, zero cost
- **Provider failover**: automatic fallback if OpenRouter is slow/down
- **Local model routing**: Ollama models route at zero cost
- **Corporate compliance**: audit trail lives locally, SSO available
- **Observability**: Prometheus metrics, distributed tracing

**Against direct OpenRouter calls:**
- No local cost tracking — spend only visible in OpenRouter dashboard
- No caching — duplicate prompts cost twice
- No spend limits — runaway loops have no circuit breaker
- No failover — single provider, single point of failure

**Against replacing OpenRouter entirely:**
- OpenRouter's provider diversity and automatic routing is non-trivial to replicate
- Tool-calling support varies by provider — OpenRouter handles the routing to capable endpoints
- Maintaining multiple provider credentials is operational overhead
- BiFrost as a proxy preserves OpenRouter while adding control

## Alternatives Considered

| Alternative | Why Not |
|-------------|---------|
| Continue with direct OpenRouter calls | No cost control, no routing strategy, no local observability |
| Replace OpenRouter with provider-direct API keys | Lose provider diversity, tool-calling support, automatic failover |
| LiteLLM (open-source proxy) | Heavier (~50x slower than BiFrost), more complex config |
| Portkey (managed) | SaaS — adds another vendor, cost data leaves environment |
| Helicone (logging only) | No routing, no spend limits, just observability |
| Build a custom proxy | Maintenance burden, no semantic cache, reinventing the wheel |

## Consequences

**What becomes easier:**
- Cost attribution: which model, which analyst, which ticker = which cost
- Strategic model selection: cheap models for drafts, expensive models for final decisions
- Corporate compliance: audit log lives locally, not just with the provider
- Fallback testing: swap in local Ollama models without changing app code
- SSO for team deployments

**What becomes harder:**
- Additional service to run — BiFrost must be up for analyses to run
- Configuration complexity — routing rules, budget hierarchies, provider credentials
- Latency: one more network hop (~1ms locally)
- BiFrost updates and config migrations

**What changes in TradingAgents:**
- `analyze_stream.py` will route LLM calls through BiFrost (`base_url: localhost:8080/v1`)
- Model names in config map to BiFrost virtual routes (e.g., `deep_think` → `openrouter/deepseek-v4-flash`)
- Cost log written to `~/.tradingagents/bifrost-cost-log.jsonl`
- OpenRouter API key passed through BiFrost to upstream providers

## Related

- Brief: `briefs/2026-06-01-brief-bifrost-installation.md`
- BiFrost: https://github.com/maximhq/bifrost
- Docs: https://docs.getbifrost.ai
- Script: `scripts/py/analyze_stream.py` (to be updated)