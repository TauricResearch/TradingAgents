# Upstream PR Review — TauricResearch/TradingAgents

**Review Date**: 2026-03-23
**Upstream Repository**: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
**Latest Upstream Release**: v0.2.2 (2026-03-22)
**Fork**: aguzererler/TradingAgents

---

## Summary

This document reviews all 60+ open PRs on the upstream TauricResearch/TradingAgents repository, evaluates their relevance to our fork, and provides recommendations for which to consider merging or cherry-picking.

Our fork has significant custom work (AgentOS observability layer, scanner pipeline, portfolio management, 725+ unit tests) that the upstream doesn't have. The upstream has been actively evolving with v0.2.2 bringing a five-tier rating framework, OpenAI Responses API support, and various bug fixes.

### Priority Legend

| Priority | Meaning |
|----------|---------|
| 🔴 **HIGH** | Strongly recommended — fixes bugs or adds capabilities we need |
| 🟡 **MEDIUM** | Worth considering — useful features or improvements |
| 🟢 **LOW** | Nice to have but not urgent |
| ⚪ **SKIP** | Not relevant, too risky, or already addressed in our fork |

---

## Already-Merged Upstream Changes (v0.2.0 → v0.2.2)

These are changes already merged into upstream `main` that our fork should sync with. Review these first before looking at open PRs.

| Commit | Date | Description | Priority | Notes |
|--------|------|-------------|----------|-------|
| `589b351` | 2026-03-22 | TradingAgents v0.2.2 | 🔴 HIGH | Version bump + release |
| `6c9c9ce` | 2026-03-22 | fix: set process-level UTF-8 default | 🔴 HIGH | Cross-platform fix, prevents Windows encoding crashes |
| `b8b2825` | 2026-03-22 | refactor: standardize portfolio manager, five-tier rating scale | 🟡 MEDIUM | New rating scale (Buy/Overweight/Hold/Underweight/Sell) — significant prompt change |
| `318adda` | 2026-03-22 | refactor: five-tier rating scale and streamlined agent prompts | 🟡 MEDIUM | Paired with above |
| `7cca9c9` | 2026-03-22 | fix: add exponential backoff retry for yfinance rate limits | 🔴 HIGH | Directly relevant — we already handle this but their approach may be cleaner |
| `bd9b1e5` | 2026-03-22 | feat: add Anthropic effort level support for Claude models | 🟡 MEDIUM | Useful if using Claude |
| `7775500` | 2026-03-22 | chore: consolidate install, fix CLI portability | 🟡 MEDIUM | Build/install improvements |
| `0b13145` | 2026-03-22 | fix: handle list content when writing report sections | 🔴 HIGH | Bug fix for Gemini list-of-dicts responses |
| `3ff28f3` | 2026-03-22 | fix: use OpenAI Responses API for native models | 🔴 HIGH | Required for GPT-5+ models |
| `08bfe70` | 2026-03-21 | fix: preserve exchange-qualified tickers | 🟡 MEDIUM | International market support (CNC.TO, 7203.T) |
| `64f0767` | 2026-03-15 | fix: add http_client support for SSL cert customization | 🟡 MEDIUM | Corporate proxy environments |
| `551fd7f` | 2026-03-15 | chore: update model lists, bump to v0.2.1 | 🟢 LOW | Model list updates |
| `b0f9d18` | 2026-03-15 | fix: harden stock data parsing against malformed CSV/NaN | 🔴 HIGH | Data integrity fix |
| `9cc283a` | 2026-03-15 | fix: add missing console import to cli/utils.py | 🟢 LOW | Minor CLI fix |
| `fe9c8d5` | 2026-03-15 | fix: handle comma-separated indicators | 🟡 MEDIUM | Bug fix |
| `eec6ca4` | 2026-03-15 | fix: initialize all debate state fields | 🔴 HIGH | Prevents crashes in debate cycle |
| `3642f59` | 2026-03-15 | fix: add explicit UTF-8 encoding to all file open() calls | 🔴 HIGH | Windows compatibility |
| `907bc80` | 2026-03-15 | fix: pass debate round config to ConditionalLogic | 🔴 HIGH | Config was being ignored |
| `8a60662` | 2026-03-15 | chore: remove unused chainlit dependency (CVE-2026-22218) | 🔴 HIGH | Security fix |
| `35856ff` | 2026-02-09 | fix: risk manager fundamental report data source | 🔴 HIGH | Bug fix in risk manager |
| `5fec171` | 2026-02-07 | chore: add build-system config, update to v0.2.0 | 🟡 MEDIUM | Build system |
| `50c82a2` | 2026-02-07 | chore: consolidate deps to pyproject.toml | 🟡 MEDIUM | Cleanup |
| `66a02b3` | 2026-02-05 | security: patch LangGrinch vulnerability in langchain-core | 🔴 HIGH | Security patch |
| `e9470b6` | 2026-02-04 | TradingAgents v0.2.0: Multi-Provider LLM Support | 🔴 HIGH | Major release with multi-provider support |

**Recommendation**: Sync with upstream `main` to get all bug fixes, security patches, and the v0.2.2 release. The biggest changes are the five-tier rating scale (may conflict with our custom prompts), OpenAI Responses API support, and UTF-8 fixes.

---

## Open PRs — HIGH Priority (🔴 Recommended to Review)

### PR #427 — Respect Anthropic proxy base URL
- **Date**: 2026-03-22
- **Author**: lu-zhengda
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/427
- **Size**: +9 lines, 1 file changed
- **Mergeable**: ✅ Clean
- **Assessment**: Tiny, focused fix. Maps Anthropic client's generic `base_url` to LangChain's `anthropic_api_url`. Avoids overriding `ANTHROPIC_BASE_URL` when using default endpoint. Critical for anyone running behind a proxy.
- **Conflicts with our fork**: None expected — touches only `anthropic_client.py`
- **Recommendation**: 🔴 Review and cherry-pick. Small, safe, and useful.

### PR #389 — Warn on unknown models in LLM clients
- **Date**: 2026-03-17
- **Author**: HuYellow
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/389
- **Size**: +133/-8 lines, 6 files
- **Assessment**: Adds warning when using unknown models instead of silently proceeding or crashing. Includes unit tests. Defensive coding improvement.
- **Conflicts with our fork**: Low — touches LLM client files which we've extended
- **Recommendation**: 🔴 Review and adapt. Good defensive practice we should have.

### PR #399 — Optional social sentiment tool for social analyst
- **Date**: 2026-03-19
- **Author**: alexander-schneider
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/399
- **Size**: +326/-17 lines, 6 files
- **Assessment**: Adds optional `get_social_sentiment` tool using Adanos API for Reddit/X/Polymarket sentiment. Only activates when `ADANOS_API_KEY` is set. Addresses a real gap — our social analyst only has access to news data. Includes tests and graceful opt-in.
- **Conflicts with our fork**: Medium — touches `social_media_analyst.py` and `trading_graph.py` which we've modified
- **Recommendation**: 🔴 Review and consider adapting. The design (opt-in via env var, no changes to default flow) is clean.

---

## Open PRs — MEDIUM Priority (🟡 Worth Considering)

### PR #408 — Allow custom OpenRouter model IDs in CLI
- **Date**: 2026-03-21
- **Author**: CadeYu
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/408
- **Size**: +96/-13 lines, 2 files
- **Mergeable**: ✅ Clean
- **Assessment**: Adds "Custom OpenRouter model ID" option to CLI. Unblocks users with paid OpenRouter accounts from being limited to 2 free models. Includes unit tests.
- **Conflicts with our fork**: Low — CLI changes
- **Recommendation**: 🟡 Consider if OpenRouter is used. Nice UX improvement.

### PR #425 — Add popular paid models for OpenRouter
- **Date**: 2026-03-22
- **Author**: ctonneslan
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/425
- **Size**: +25 lines, 1 file
- **Mergeable**: ✅ Clean
- **Assessment**: Adds Claude Sonnet 4, Gemini 2.5, GPT-5 variants to OpenRouter dropdown. Plus custom model ID input. Overlaps with PR #408.
- **Recommendation**: 🟡 Pick one of #408 or #425 — they address the same issue (#337).

### PR #416 — Amazon Bedrock provider
- **Date**: 2026-03-22
- **Author**: cloudbeer
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/416
- **Size**: +63/-1 lines, 4 files
- **Mergeable**: ✅ Clean
- **Assessment**: Adds Amazon Bedrock as LLM provider via boto3 credential chain. Supports IAM Role, AKSK, and Bedrock API Key auth. Clean implementation, tested with multiple models.
- **Conflicts with our fork**: Low — adds new client file
- **Recommendation**: 🟡 Review if AWS deployment is planned. Good addition for enterprise use cases.

### PR #430 — Groq and Kilo Gateway LLM providers
- **Date**: 2026-03-23
- **Author**: deathvadeR-afk
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/430
- **Size**: +98/-32 lines, 7 files
- **Mergeable**: ✅ Clean
- **Assessment**: Adds Groq (fast inference) and Kilo Gateway providers. Both are OpenAI-compatible. Includes Windows UTF-8 fix.
- **Conflicts with our fork**: Low–Medium — touches factory and CLI files
- **Recommendation**: 🟡 Groq is popular for fast inference. Consider for latency-sensitive workflows.

### PR #355 — Azure Foundry support
- **Date**: 2026-03-02
- **Author**: yulinzhang96
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/355
- **Size**: +179/-27 lines, 8 files
- **Assessment**: Adds Azure Foundry as LLM provider. Supports any model in Azure's catalog. Includes Windows file I/O UTF-8 fixes.
- **Conflicts with our fork**: Medium — touches default_config.py and factory
- **Recommendation**: 🟡 Review if Azure deployment is planned.

### PR #359 — Optional factor rule analyst with manual rule injection
- **Date**: 2026-03-06
- **Author**: 69049ed6x
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/359
- **Size**: +959/-76 lines, 24 files, 40 commits
- **Assessment**: Adds an optional "Factor Rule Analyst" that loads user-defined factor rules from JSON and injects them into the bull/bear/research/trader/risk pipeline. Interesting concept for semi-systematic workflows. However: large PR (40 commits), touches many core files, and modifies our heavily-customized graph.
- **Conflicts with our fork**: HIGH — touches setup.py, trading_graph.py, agents, propagation
- **Recommendation**: 🟡 Interesting concept but too invasive to merge directly. Consider extracting the idea and implementing it ourselves in a way that fits our architecture.

### PR #347 — Fix yfinance rate limit/session issues + Windows encoding
- **Date**: 2026-02-14
- **Author**: Hewei603
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/347
- **Size**: +101/-41 lines, 2 files
- **Assessment**: Adds exponential backoff retry for yfinance, removes manual session params. However, upstream already merged a similar fix (`7cca9c9` on 2026-03-22), making this PR partially redundant.
- **Conflicts with our fork**: Medium — we have our own rate limiting
- **Recommendation**: 🟡 Review but likely superseded by upstream's own merge. Check if any unique approach here is better.

### PR #362 — Testing infrastructure and utility modules
- **Date**: 2026-03-07
- **Author**: newwan
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/362
- **Size**: +1750 lines, 20 files
- **Assessment**: Adds pytest, ruff, mypy config. Adds config validation, structured logging, TypedDict definitions. We already have extensive test infrastructure (725+ tests), but the config validation and logging modules could be useful.
- **Conflicts with our fork**: HIGH — we have our own test setup
- **Recommendation**: 🟡 Cherry-pick specific modules (config validation, TypedDict types) rather than the whole PR.

### PR #401 — Multi-LLM routing (stage & role-based)
- **Date**: 2026-03-19
- **Author**: mzamini92
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/401
- **Size**: +410/-214 lines, 5 files
- **Assessment**: Adds flexible LLM routing per pipeline stage/role. We already have 3-tier LLM routing (quick/mid/deep think), but this is more granular (per analyst, per researcher, etc.). Conceptually aligned with our architecture.
- **Conflicts with our fork**: HIGH — modifies default_config.py, trading_graph.py, setup.py
- **Recommendation**: 🟡 Good concept but our 3-tier system + per-tier provider overrides already covers most use cases. Consider for future if fine-grained routing is needed.

### PR #324 — Multi-provider support, retry logic, dynamic model fetching
- **Date**: 2026-01-17
- **Author**: MUmarJ
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/324
- **Size**: +1476/-71 lines, 19 files
- **Mergeable**: ❌ Dirty (conflicts)
- **Assessment**: Large PR with content normalization for Gemini, retry logic with backoff, OpenAI Responses API support, config validation, and dynamic model fetching. Much of this has been incrementally merged into upstream's main already.
- **Conflicts with our fork**: HIGH — large, touches many files, and partially superseded
- **Recommendation**: 🟡 Check if any unique pieces (e.g., the normalize_content utility) haven't been incorporated upstream yet. Likely mostly superseded by v0.2.2.

---

## Open PRs — LOW Priority (🟢 Nice to Have)

### PR #432 — Polymarket prediction market analysis module
- **Date**: 2026-03-23
- **Author**: InjayTseng
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/432
- **Size**: +7618/-31 lines, 53 files
- **Mergeable**: ✅ Clean
- **Assessment**: Adds an entire parallel module for Polymarket binary prediction market analysis. 4 specialized analysts, YES/NO debate, Kelly Criterion sizing. Impressive scope but large and unrelated to stock analysis. No external dependencies added. Analysis-only (no order placement).
- **Recommendation**: 🟢 Interesting expansion but out of scope for our current focus. Monitor — if upstream merges it, we can pick it up later.

### PR #394 — Multi-market support (Vietnam stock market)
- **Date**: 2026-03-18
- **Author**: VONUHAU
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/394
- **Size**: +1705/-51 lines, 15 files
- **Mergeable**: ❌ Dirty (conflicts)
- **Assessment**: Adds pluggable `MarketRegistry` + `MarketProvider` abstraction, with Vietnam as first non-US market. Good architecture for multi-market but has conflicts and adds `vnstock` dependency.
- **Recommendation**: 🟢 The `MarketRegistry` abstraction pattern is worth noting for future multi-market expansion. Not urgent now.

### PR #372 — Swing trading pipeline with auto stock screening
- **Date**: 2026-03-11
- **Author**: hyejwon
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/372
- **Size**: +5278/-1217 lines, 49 files
- **Assessment**: Removes debate/risk stages, simplifies to Screening→Analysts→Trader. Adds Korean market support. Very different philosophy from our approach. Destructive changes (removes core features).
- **Recommendation**: 🟢 Interesting alternative architecture but incompatible with our fork's approach. Skip for merging, but review screening pipeline ideas.

### PR #339 — Cross-Asset Correlation Engine
- **Date**: 2026-02-07
- **Author**: Insider77Circle
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/339
- **Size**: +1583 lines, 6 files
- **Assessment**: Adds correlation analysis module (Pearson, Spearman, DCC-GARCH, wavelet coherence, regime detection). Adds scipy, scikit-learn, PyWavelets, networkx dependencies. Standalone module.
- **Recommendation**: 🟢 Potentially useful for market analysis but adds heavy dependencies. Consider as a standalone research tool.

### PR #419 — Chinese translation for README
- **Date**: 2026-03-22
- **Author**: JasonYeYuhe
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/419
- **Assessment**: Adds README.zh.md with Chinese translation.
- **Recommendation**: 🟢 Skip — documentation only, not relevant to our fork.

### PR #410 — llama.cpp local LLM support
- **Date**: 2026-03-21
- **Author**: TPTBusiness
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/410
- **Assessment**: Adds 'llamacpp' provider for running fully offline with local llama-server.
- **Recommendation**: 🟢 We already support Ollama for local inference. Consider if llama.cpp direct support adds value.

### PR #407 — Z.AI glm-5 provider support
- **Date**: 2026-03-21
- **Author**: tanyudii
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/407
- **Assessment**: Adds Z.AI as LLM provider for stock research.
- **Recommendation**: 🟢 Niche provider. Skip unless needed.

### PR #395 — MiniMax as LLM provider
- **Date**: 2026-03-18
- **Author**: octo-patch
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/395
- **Assessment**: Adds MiniMax (OpenAI-compatible API) with M2.7 models.
- **Recommendation**: 🟢 Niche provider. Skip unless needed.

### PR #344 — Streamlit UI for Hugging Face Spaces
- **Date**: 2026-02-11
- **Author**: rajeshthangaraj1
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/344
- **Assessment**: Adds Streamlit web UI. We have AgentOS (React+FastAPI) which is far more capable.
- **Recommendation**: 🟢 Skip — we have a superior UI solution.

### PR #340 — Top 10 OpenRouter models in CLI
- **Date**: 2026-02-08
- **Author**: treasuraid
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/340
- **Assessment**: Adds top OpenRouter models to selection. Overlaps with #408 and #425.
- **Recommendation**: 🟢 Superseded by #408/#425.

---

## Open PRs — SKIP (⚪ Not Recommended)

### PR #435 — CLI change to correct files reading
- **Date**: 2026-03-23
- **Author**: BranJ2106
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/435
- **Size**: +4851/-16 lines, 31 files
- **Assessment**: Description in Spanish, unclear scope, 4851 lines added across 31 files for what's described as file reading and report generation fixes. Disproportionate change size for described fix.
- **Recommendation**: ⚪ Skip — unclear quality and scope.

### PR #431 — "Kim"
- **Date**: 2026-03-23
- **Author**: Kim-254-de
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/431
- **Assessment**: Empty body, title is just "Kim". No description of changes.
- **Recommendation**: ⚪ Skip — no description, likely test PR.

### PR #376 — ChatGPT OAuth login (codex_oauth)
- **Date**: 2026-03-14
- **Author**: CaiJichang212
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/376
- **Assessment**: Adds OAuth login via ChatGPT Plus/Pro to bypass API keys. Security concern — relies on browser OAuth flow scraping.
- **Recommendation**: ⚪ Skip — security concern, unofficial API access pattern.

### PR #374 — Feature/phase2 execution
- **Date**: 2026-03-11
- **Author**: BrunoNatalicio
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/374
- **Assessment**: Empty body, no description.
- **Recommendation**: ⚪ Skip — no description.

### PR #373 — Dex data layer
- **Date**: 2026-03-11
- **Author**: BrunoNatalicio
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/373
- **Assessment**: Empty body, no description. Likely DeFi/DEX data layer.
- **Recommendation**: ⚪ Skip — no description, unclear scope.

### PR #371 — Simplified Chinese option for reports
- **Date**: 2026-03-10
- **Author**: divingken
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/371
- **Assessment**: Adds Chinese language option for reports. Localization.
- **Recommendation**: ⚪ Skip — not relevant to our fork's needs.

### PR #370 — Fix SSL certificate error and ASCII bug
- **Date**: 2026-03-09
- **Author**: iamhenryhuang
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/370
- **Assessment**: SSL and ASCII fixes. Likely superseded by upstream's UTF-8 and SSL fixes already merged.
- **Recommendation**: ⚪ Skip — likely superseded.

### PR #368 — Add vLLM provider
- **Date**: 2026-03-09
- **Author**: flutist
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/368
- **Assessment**: Adds vLLM provider.
- **Recommendation**: ⚪ Skip — niche, and there's also a duplicate PR #358 (draft).

### PR #367 — Traditional Chinese output support
- **Date**: 2026-03-09
- **Author**: Jack0630
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/367
- **Assessment**: Adds Traditional Chinese instructions to all agent prompts.
- **Recommendation**: ⚪ Skip — localization, not relevant.

### PR #366 — System R external risk validation example
- **Date**: 2026-03-08
- **Author**: ashimnandi-trika
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/366
- **Assessment**: Adds example showing integration with System R risk validation API. Example file only.
- **Recommendation**: ⚪ Skip — example/integration with external product.

### PR #363 — Add Ollama cloud provider
- **Date**: 2026-03-07
- **Author**: simodev25
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/363
- **Assessment**: Adds Ollama Cloud support. We already have Ollama support configured per our architecture.
- **Recommendation**: ⚪ Skip — we already handle Ollama.

### PR #360 — Add DeepSeek support
- **Date**: 2026-03-06
- **Author**: null0NULL123
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/360
- **Assessment**: Adds DeepSeek provider. DeepSeek is OpenAI-compatible and works via OpenRouter in our setup.
- **Recommendation**: ⚪ Skip — already works via OpenRouter or direct OpenAI-compatible config.

### PR #358 — Add vLLM support (Draft)
- **Date**: 2026-03-06
- **Author**: flutist
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/358
- **Assessment**: Draft PR, duplicate of #368.
- **Recommendation**: ⚪ Skip — draft, duplicate.

### PR #333 — Azure OpenAI support
- **Date**: 2026-02-04
- **Author**: kazuma-424
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/333
- **Assessment**: Adds Azure OpenAI support. Overlaps with #355 (Azure Foundry).
- **Recommendation**: ⚪ Skip — #355 (Azure Foundry) is more comprehensive.

### PR #329 — Settings UI, Pipeline Visualization & Documentation (Nifty50)
- **Date**: 2026-01-31
- **Author**: hemangjoshi37a
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/329
- **Assessment**: Nifty50-specific dashboard. We have AgentOS.
- **Recommendation**: ⚪ Skip — we have a superior UI.

### PR #328 — New UI
- **Date**: 2026-01-30
- **Author**: qq173681019
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/328
- **Assessment**: Empty body. Alternative UI implementation.
- **Recommendation**: ⚪ Skip — no description, we have AgentOS.

### PR #320 — Physical URL verification for Fact Checker
- **Date**: 2026-01-04
- **Author**: jiwoomap
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/320
- **Assessment**: Adds URL verification to fact checker, checks if cited URLs actually exist.
- **Recommendation**: ⚪ Skip for now — interesting concept but adds network calls during analysis.

### PR #302 — ACE (Agentic Context Engineer)
- **Date**: 2025-12-25
- **Author**: EduardGilM
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/302
- **Assessment**: Integrates ACE framework for autonomous agent improvement through reflection. External dependency.
- **Recommendation**: ⚪ Skip — adds external framework dependency.

### PR #286 — Fix OpenRouter embeddings
- **Date**: 2025-11-20
- **Author**: 00make
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/286
- **Assessment**: OpenRouter embeddings fix. Empty body.
- **Recommendation**: ⚪ Skip — no description, old PR.

### PR #282 — Turns off upload files, addresses conflicts
- **Date**: 2025-11-19
- **Author**: jackspace
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/282
- **Assessment**: Cleanup PR related to #281. Empty body.
- **Recommendation**: ⚪ Skip — related to #281 which we're also skipping.

### PR #281 — Production-Ready Platform (Multi-LLM, Paper Trading, Web UI, Docker)
- **Date**: 2025-11-19
- **Author**: jackspace
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/281
- **Size**: +40032/-45 lines, 113 files
- **Mergeable**: ❌ Dirty (conflicts)
- **Assessment**: Massive PR (40k+ lines) that adds LLM factory, Alpaca paper trading, Chainlit web UI, Docker. Very ambitious but: enormous scope, 5 months old, has merge conflicts, and our fork already has AgentOS + portfolio management.
- **Recommendation**: ⚪ Skip — too large, too old, and our fork has surpassed many of these features.

### PR #278 — Add openai_compatible mode
- **Date**: 2025-11-15
- **Author**: grandgen
- **URL**: https://github.com/TauricResearch/TradingAgents/pull/278
- **Assessment**: Adds generic OpenAI-compatible provider mode. Our fork already supports this pattern.
- **Recommendation**: ⚪ Skip — already addressed.

### Older PRs (#146, #145, #144, #135, #134, #128, #125, #120, #117, #116, #115, #110, #105, #103, #101, #94, #61, #56, #48)
- **Date range**: 2025-06 to 2025-07
- **Assessment**: These PRs are 8–9 months old, target an older codebase, and many of their features have been addressed either by upstream's v0.2.x releases or by our fork's custom work.
- **Recommendation**: ⚪ Skip all — stale, likely superseded.

---

## Action Items — Recommended Review Order

### Phase 1: Sync with upstream main (🔴 Critical)
1. **Merge/rebase upstream v0.2.2 changes** into our fork. Key changes:
   - Security: LangGrinch vulnerability patch, chainlit CVE removal
   - Bug fixes: debate state init, debate round config, UTF-8 encoding, stock data parsing
   - Features: OpenAI Responses API, five-tier rating scale, yfinance retry
   - **⚠️ Potential conflicts**: Our custom prompts, graph setup, and CLI may need manual resolution

### Phase 2: Cherry-pick high-value PRs (🔴 High Priority)
2. **PR #427** — Anthropic proxy base URL fix (tiny, safe)
3. **PR #389** — Unknown model warnings (small, defensive)
4. **PR #399** — Social sentiment tool (medium, fills a real gap)

### Phase 3: Evaluate medium-priority PRs (🟡)
5. **PR #408 or #425** — OpenRouter model expansion (pick one)
6. **PR #416** — Bedrock provider (if AWS is planned)
7. **PR #430** — Groq provider (if fast inference is needed)

### Phase 4: Future consideration (🟢)
8. **PR #432** — Polymarket module (monitor if upstream merges)
9. **PR #394** — Multi-market architecture (note the MarketRegistry pattern)
10. **PR #339** — Cross-asset correlation (standalone research tool)

---

## Notes for Next Review

- The upstream is actively maintained by @Yijia-Xiao with frequent merges
- Our fork has diverged significantly with AgentOS, scanner pipeline, and 725+ unit tests
- The five-tier rating scale in v0.2.2 is a significant prompt change — test thoroughly before adopting
- Many community PRs are LLM provider additions — most are OpenAI-compatible and work via OpenRouter anyway
- Watch for v0.2.3+ releases — the upstream is shipping fast
