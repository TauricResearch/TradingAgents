---
name: trading-agent
description: Skill for Copilot to assist with the TradingAgents framework, especially trading agent development, financial analysis, risk management, and CLI workflows.
---

Use the `/trading-agent` skill when asked to develop, debug, or extend the TradingAgents framework and its trading agent workflows. When applying this skill:

- Follow the repository's existing architecture and conventions in `tradingagents/`, `main.py`, and the CLI entrypoints.
- Keep financial analysis grounded in data, and avoid presenting trading suggestions as investment advice.
- Prioritize reproducibility, safe environment configuration, and clear guidance on using `.env.example` or `.env.enterprise.example`.
- Help with multi-agent reasoning, risk management, backtesting, and provider configuration for OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen, GLM, MiniMax, Ollama, and Bedrock.
- Suggest documentation updates or examples only when they improve clarity for developers using or extending TradingAgents.
