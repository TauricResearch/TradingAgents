"""Programmatic example for invoking the Kalshi prediction-market pipeline.

Phase 0 strips the equity flow from this example. Phases 1–4 will populate
the data layer, schema, execution, and CLI surface for daily Kalshi BTC
contracts. Until then this file documents the target call shape.
"""

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

load_dotenv()

# Custom config — paper-only by default, see ``tradingagents/default_config.py``
# for the full set of knobs (LLM provider, debate rounds, Kalshi block).
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 1

# Initialize the pipeline. Phase 1 will populate the analyst tool nodes
# with real crypto/Kalshi data sources; until then the run will execute
# the full graph but tools return placeholder text.
ta = TradingAgentsGraph(debug=True, config=config)

# A Kalshi BTC daily contract id has the shape KXBTCD-<DATE>-T<STRIKE>.
# Example: BTC closes above $100,000 on 2026-05-05.
final_state, decision = ta.propagate("KXBTCD-26MAY05-T100000", "2026-05-05")
print(decision)
