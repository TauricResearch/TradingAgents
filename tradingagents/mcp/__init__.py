"""Local MCP (Model Context Protocol) server for the TradingAgents data layer.

This package exposes the framework's data tools (market, news, fundamentals,
macro, prediction markets) over an MCP ``stdio`` transport so a Claude client
(Claude Code / Claude Desktop) can fetch data while *Claude itself* plays every
analyst/researcher/trader/PM role. The server makes **no LLM calls** — it only
returns data — so running the full pipeline costs zero LLM API spend.
"""
