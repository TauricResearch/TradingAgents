import sys
from tradingagents.agents import create_market_analyst, create_technical_analyst, create_quant_analyst, create_options_analyst, create_fundamentals_analyst, create_alternative_data_analyst
from tradingagents.agents.utils.tool_call_recovery import recover_tool_calls
from langchain_core.messages import AIMessage

# Test recovery
msg = AIMessage(content='<tool_call>{"name": "get_verified_market_snapshot", "arguments": {"symbol": "AAPL", "curr_date": "2024-01-01"}}</tool_call>')
class DummyTool:
    name = 'get_verified_market_snapshot'
    def invoke(self, args): return 'success'

new_msg, recovered = recover_tool_calls(msg, [DummyTool()])
print('tool_calls:', new_msg.tool_calls)
print('recovered:', recovered)
print('All analyst imports OK')
