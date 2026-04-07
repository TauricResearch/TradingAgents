from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents import *
from tradingagents.llm_clients import create_llm_client

from dotenv import load_dotenv
config = DEFAULT_CONFIG.copy()

deep_client = create_llm_client(
    provider=config["llm_provider"],
    model=config["deep_think_llm"],
    base_url=config.get("backend_url"),
    **llm_kwargs,
)
quick_client = create_llm_client(
    provider=config["llm_provider"],
    model=config["quick_think_llm"],
    base_url=config.get("backend_url"),
    **llm_kwargs,
)

quick_thinking_llm = quick_client.get_llm()

fundamental_analyst = create_market_analyst(
                quick_thinking_llm
            )
fundamental_analyst.invoke({"messages": [{"role": "user", "content": "Hello"}]})