"""Default configuration for TradingAgents.

`DEFAULT_CONFIG` is kept as a plain dict for full backward compatibility with
all existing code.  It is now generated from `TradingAgentsConfig` so that
env-var overrides, type validation, and the typed model stay in sync — there
is a single source of truth.

New code should prefer importing `TradingAgentsConfig` directly:

    from tradingagents.config import TradingAgentsConfig
    cfg = TradingAgentsConfig(llm_provider="anthropic")
    ta = TradingAgentsGraph(config=cfg)

The legacy dict form continues to work unchanged:

    from tradingagents.default_config import DEFAULT_CONFIG
    ta = TradingAgentsGraph(config=DEFAULT_CONFIG)
"""
from tradingagents.config import TradingAgentsConfig

# Construct from env vars + defaults, then expose as a dict.
# All TRADINGAGENTS_* env var overrides are applied by TradingAgentsConfig.
DEFAULT_CONFIG: dict = TradingAgentsConfig().to_dict()
