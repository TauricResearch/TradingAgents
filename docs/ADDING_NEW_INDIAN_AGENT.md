# Adding A New Indian Agent

1. Add the analyst implementation under `tradingagents/agents/analysts/`.
2. Add tools under `tradingagents/agents/utils/india_market_tools.py` only after dataflow functions are testable.
3. Register the factory in `tradingagents/agents/__init__.py`.
4. Add a node spec in `tradingagents/graph/analyst_execution.py`.
5. Add conditional routing in `tradingagents/graph/conditional_logic.py`.
6. Add a tool node in `TradingAgentsGraph._create_tool_nodes()`.
7. Add state fields in `tradingagents/agents/utils/agent_states.py` and initial values in `tradingagents/graph/propagation.py`.
8. Add offline unit tests.

Keep prompts India-only, data-quality aware, and research-only.
