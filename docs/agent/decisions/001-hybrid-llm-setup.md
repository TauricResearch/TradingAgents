---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [llm, infrastructure, ollama, openrouter]
related_files: [tradingagents/default_config.py]
---

## Context

Need cost-effective LLM setup for scanner pipeline with different complexity tiers.

## The Decision

Use hybrid approach:
- **quick_think + mid_think**: `qwen3.5:27b` via Ollama at `http://192.168.50.76:11434` (local, free)
- **deep_think**: `deepseek/deepseek-r1-0528` via OpenRouter (cloud, paid)

Config location: `tradingagents/default_config.py` — per-tier `_llm_provider` and `_backend_url` keys.

## Constraints

- Each tier must have its own `{tier}_llm_provider` set explicitly.
- Top-level `llm_provider` and `backend_url` must always exist as fallbacks.

## Actionable Rules

- Never hardcode `localhost:11434` for Ollama — always use configured `base_url`.
- Per-tier providers fall back to top-level `llm_provider` when `None`.
