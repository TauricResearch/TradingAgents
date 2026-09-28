"""Deterministic graph double; CLI streaming, journaling and exports stay real."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class RecordingGraph:
    def __init__(self, selected_analysts, config, callbacks=None):
        self.selected = selected_analysts
        self.config = config
        self.callbacks = callbacks or []
        self.graph = self
        self.propagator = self
        self.calls = []
        self._resuming = False
        self.resume = False
        self.failure = None
        self.probe = None
        self.decision = "Hold"
        self.observed = []

    def create_run_state(self, ticker, trade_date, asset_type="stock", portfolio=None):
        self.calls.append(("create", ticker, trade_date, asset_type, portfolio))
        self.ticker, self.date = ticker, trade_date
        return {"company_of_interest": ticker, "trade_date": trade_date, "messages": []}

    def begin_checkpoint(self, *args):
        self.calls.append(("begin",))
        self._resuming = self.resume
        return "checkpoint-thread" if self.config.get("checkpoint_enabled") else None

    def checkpoint_input(self, state):
        return None if self._resuming else state

    def end_checkpoint(self):
        self.calls.append(("end",))
        self._resuming = False

    def get_graph_args(self, callbacks=None):
        return {"stream_mode": "values", "config": {"recursion_limit": 100, "callbacks": callbacks or []}}

    def stream(self, graph_input, **kwargs):
        self.calls.append(("stream", graph_input, kwargs))
        assert kwargs["stream_mode"] == "values"
        self.observed = kwargs["config"].get("callbacks", [])
        for cb in self.observed:
            cb.on_chain_start(None, {}, run_id="root", name="LangGraph")
        state = {"company_of_interest": self.ticker, "trade_date": self.date,
                 "messages": [HumanMessage(content=self.ticker, id="human")],
                 "market_report": "", "sentiment_report": "", "news_report": "", "fundamentals_report": "",
                 "investment_debate_state": {}, "risk_debate_state": {}}
        yield deepcopy(state)
        keys = {"market": ("Market Analyst", "market_report"), "social": ("Sentiment Analyst", "sentiment_report"),
                "news": ("News Analyst", "news_report"), "fundamentals": ("Fundamentals Analyst", "fundamentals_report")}
        for key in self.selected:
            name, report = keys[key]
            for cb in self.observed:
                cb.on_chain_start(None, state, run_id=key, parent_run_id="root", name=name,
                                  metadata={"langgraph_node": name})
                cb.on_chat_model_start({}, [])
            if key == "market":
                state["messages"].append(AIMessage(content="", id="tool-request", tool_calls=[{
                    "id": "call-1", "name": "get_stock_data", "args": {"symbol": self.ticker}, "type": "tool_call",
                }]))
                yield deepcopy(state)
                for cb in self.observed:
                    cb.on_tool_start({"name": "get_stock_data"}, "private-tool-input")
                state["messages"].append(ToolMessage(content="prices", tool_call_id="call-1", id="tool-result"))
            message = AIMessage(content=f"{self.ticker} {report} 中文", id=key,
                                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
            state[report] = message.content
            state["messages"].append(message)
            for cb in self.observed:
                cb.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=message)]]))
                cb.on_chain_end({report: state[report]}, run_id=key)
            yield deepcopy(state)
            yield deepcopy(state)  # Values snapshots repeat older message IDs.
            if self.probe:
                self.probe(self, state)
            if self.failure:
                raise self.failure
        for name, updates in (
            ("Bull Researcher", {"investment_debate_state": {"bull_history": "bull"}}),
            ("Bear Researcher", {"investment_debate_state": {"bull_history": "bull", "bear_history": "bear"}}),
            ("Research Manager", {"investment_debate_state": {"bull_history": "bull", "bear_history": "bear", "judge_decision": "research"}, "investment_plan": "research"}),
            ("Trader", {"trader_investment_plan": "trade"}),
            ("Aggressive Analyst", {"risk_debate_state": {"aggressive_history": "aggressive"}}),
            ("Portfolio Manager", {"risk_debate_state": {"aggressive_history": "aggressive", "conservative_history": "conservative", "neutral_history": "neutral", "judge_decision": self.decision}, "final_trade_decision": self.decision}),
        ):
            for cb in self.observed:
                cb.on_chain_start(None, state, run_id=name, parent_run_id="root", name=name,
                                  metadata={"langgraph_node": name})
            state.update(updates)
            for cb in self.observed:
                cb.on_chain_end(updates, run_id=name)
            yield deepcopy(state)
        for cb in self.observed:
            cb.on_chain_end(state, run_id="root")

    def _log_state(self, trade_date, state):
        self.calls.append(("json",))
        directory = Path(self.config["results_dir"]) / self.ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"full_states_log_{trade_date}.json").write_text(json.dumps(state, default=str), encoding="utf-8")

    def record_decision(self, ticker, trade_date, state):
        self.calls.append(("record", ticker, trade_date, state["final_trade_decision"]))

    def clear_checkpoint_on_success(self, *args):
        self.calls.append(("clear",))

    def process_signal(self, text):
        return text if text in {"Buy", "Hold", "Sell"} else "REVIEW"
