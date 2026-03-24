from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.outputs import LLMResult

from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_insider_transactions,
    get_news,
    get_stock_data,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.trading_graph import TradingAgentsGraph


TOOL_REGISTRY = {
    tool.name: tool
    for tool in (
        get_stock_data,
        get_indicators,
        get_fundamentals,
        get_balance_sheet,
        get_cashflow,
        get_income_statement,
        get_news,
        get_global_news,
        get_insider_transactions,
    )
}

def stringify_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def serialize_message(message: Any) -> Dict[str, Any]:
    if isinstance(message, tuple) and len(message) == 2:
        role, content = message
        return {"type": role, "content": stringify_content(content)}

    tool_calls = []
    for tool_call in getattr(message, "tool_calls", []) or []:
        if isinstance(tool_call, dict):
            tool_calls.append(
                {
                    "id": tool_call.get("id"),
                    "name": tool_call.get("name"),
                    "args": tool_call.get("args"),
                }
            )
        else:
            tool_calls.append(
                {
                    "id": getattr(tool_call, "id", None),
                    "name": getattr(tool_call, "name", None),
                    "args": getattr(tool_call, "args", None),
                }
            )

    return {
        "type": message.__class__.__name__,
        "content": stringify_content(getattr(message, "content", "")),
        "tool_calls": tool_calls,
    }


def extract_llm_output(response: LLMResult) -> str:
    try:
        generation = response.generations[0][0]
    except (IndexError, TypeError):
        return ""

    if hasattr(generation, "message"):
        return stringify_content(getattr(generation.message, "content", ""))

    return stringify_content(getattr(generation, "text", ""))


def usage_metadata(response: LLMResult) -> Dict[str, Any]:
    try:
        generation = response.generations[0][0]
    except (IndexError, TypeError):
        return {}

    if hasattr(generation, "message"):
        metadata = getattr(generation.message, "usage_metadata", None)
        if metadata:
            return dict(metadata)

    return {}


class StageTraceCallbackHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        super().__init__()
        self.current_stage: str | None = None
        self.records: Dict[str, List[Dict[str, Any]]] = {}

    def set_stage(self, stage_name: str) -> None:
        self.current_stage = stage_name
        self.records.setdefault(stage_name, [])

    def clear_stage(self) -> None:
        self.current_stage = None

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        **kwargs: Any,
    ) -> None:
        if not self.current_stage:
            return

        rendered_messages = [serialize_message(msg) for msg in messages[0]] if messages else []
        self.records[self.current_stage].append(
            {
                "serialized": serialized,
                "messages": rendered_messages,
                "output": "",
                "usage": {},
            }
        )

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        if not self.current_stage:
            return

        rendered_messages = [{"type": "prompt", "content": prompt} for prompt in prompts]
        self.records[self.current_stage].append(
            {
                "serialized": serialized,
                "messages": rendered_messages,
                "output": "",
                "usage": {},
            }
        )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        if not self.current_stage:
            return

        stage_records = self.records.get(self.current_stage)
        if not stage_records:
            return

        stage_records[-1]["output"] = extract_llm_output(response)
        stage_records[-1]["usage"] = usage_metadata(response)

    def get_stage_records(self, stage_name: str) -> List[Dict[str, Any]]:
        return self.records.get(stage_name, [])


def json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def summarize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "company_of_interest": state.get("company_of_interest"),
        "trade_date": state.get("trade_date"),
        "market_report": state.get("market_report", ""),
        "sentiment_report": state.get("sentiment_report", ""),
        "news_report": state.get("news_report", ""),
        "fundamentals_report": state.get("fundamentals_report", ""),
        "investment_plan": state.get("investment_plan", ""),
        "trader_investment_plan": state.get("trader_investment_plan", ""),
        "investment_debate_state": state.get("investment_debate_state", {}),
        "risk_debate_state": state.get("risk_debate_state", {}),
        "messages": [serialize_message(msg) for msg in state.get("messages", [])],
    }
    return snapshot


def reset_messages(state: Dict[str, Any]) -> None:
    state["messages"] = [HumanMessage(content="Continue")]


def merge_state(state: Dict[str, Any], update: Dict[str, Any]) -> None:
    for key, value in update.items():
        if key == "messages":
            state.setdefault("messages", [])
            state["messages"].extend(value)
        else:
            state[key] = value


def normalize_tool_call(tool_call: Any) -> Dict[str, Any]:
    if isinstance(tool_call, dict):
        return {
            "id": tool_call.get("id"),
            "name": tool_call.get("name"),
            "args": tool_call.get("args", {}),
        }

    return {
        "id": getattr(tool_call, "id", None),
        "name": getattr(tool_call, "name", None),
        "args": getattr(tool_call, "args", {}),
    }


def save_llm_records(stage_dir: Path, stage_name: str, tracer: StageTraceCallbackHandler) -> None:
    records = tracer.get_stage_records(stage_name)
    json_dump(stage_dir / "llm_calls.json", records)

    markdown_parts: List[str] = []
    for index, record in enumerate(records, start=1):
        markdown_parts.append(f"# LLM Call {index}")
        markdown_parts.append("")
        markdown_parts.append("## Messages")
        markdown_parts.append("")
        for message in record.get("messages", []):
            markdown_parts.append(f"### {message.get('type', 'message')}")
            markdown_parts.append("")
            markdown_parts.append("```text")
            markdown_parts.append(message.get("content", ""))
            markdown_parts.append("```")
            markdown_parts.append("")
        markdown_parts.append("## Output")
        markdown_parts.append("")
        markdown_parts.append("```text")
        markdown_parts.append(record.get("output", ""))
        markdown_parts.append("```")
        markdown_parts.append("")

    write_markdown(stage_dir / "llm_calls.md", "\n".join(markdown_parts).strip() + "\n")


def persist_stage_summary(stage_dir: Path, summary: Dict[str, Any]) -> None:
    json_dump(stage_dir / "stage_summary.json", summary)


def run_tool_backed_stage(
    stage_name: str,
    stage_slug: str,
    node,
    state: Dict[str, Any],
    report_key: str,
    tracer: StageTraceCallbackHandler,
    base_output_dir: Path,
    require_min_tool_chars: int = 200,
) -> Dict[str, Any]:
    stage_dir = base_output_dir / stage_slug
    stage_dir.mkdir(parents=True, exist_ok=True)

    write_markdown(stage_dir / "stage_name.txt", stage_name + "\n")
    json_dump(stage_dir / "input_state.json", summarize_state(state))

    summary = {
        "stage_name": stage_name,
        "report_key": report_key,
        "tool_call_count": 0,
        "tool_output_chars": 0,
        "warnings": [],
    }

    tracer.set_stage(stage_name)

    for iteration in range(1, 13):
        result = node(state)
        merge_state(state, result)

        ai_message = result["messages"][-1]
        iteration_dir = stage_dir / f"iteration_{iteration:02d}"
        iteration_dir.mkdir(exist_ok=True)
        json_dump(iteration_dir / "ai_message.json", serialize_message(ai_message))
        write_markdown(iteration_dir / "ai_message.txt", stringify_content(ai_message.content) + "\n")

        if not getattr(ai_message, "tool_calls", None):
            final_report = stringify_content(result.get(report_key, ""))
            if final_report:
                write_markdown(stage_dir / "final_report.md", final_report)
            else:
                summary["warnings"].append("Stage finished without a final report.")
            break

        for tool_index, raw_tool_call in enumerate(ai_message.tool_calls, start=1):
            tool_call = normalize_tool_call(raw_tool_call)
            tool_name = tool_call["name"]
            tool_args = tool_call["args"] or {}
            tool = TOOL_REGISTRY[tool_name]
            tool_output = tool.invoke(tool_args)
            tool_output_text = stringify_content(tool_output)

            summary["tool_call_count"] += 1
            summary["tool_output_chars"] += len(tool_output_text)

            tool_prefix = f"{iteration:02d}_{tool_index:02d}_{tool_name}"
            json_dump(
                iteration_dir / f"{tool_prefix}_call.json",
                {"name": tool_name, "args": tool_args, "tool_call_id": tool_call["id"]},
            )
            write_markdown(iteration_dir / f"{tool_prefix}_output.md", tool_output_text)

            state["messages"].append(
                ToolMessage(
                    content=tool_output_text,
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                )
            )
    else:
        summary["warnings"].append("Tool-backed stage hit the local safety limit of 12 iterations.")

    if summary["tool_call_count"] == 0:
        summary["warnings"].append("No tool calls were made; the stage may not have gathered external data.")
    elif summary["tool_output_chars"] < require_min_tool_chars:
        summary["warnings"].append("Tool output volume was low; verify the stage gathered enough data.")

    save_llm_records(stage_dir, stage_name, tracer)
    persist_stage_summary(stage_dir, summary)
    tracer.clear_stage()
    return summary


def run_direct_stage(
    stage_name: str,
    stage_slug: str,
    node,
    state: Dict[str, Any],
    update_key: str,
    tracer: StageTraceCallbackHandler,
    base_output_dir: Path,
) -> Dict[str, Any]:
    stage_dir = base_output_dir / stage_slug
    stage_dir.mkdir(parents=True, exist_ok=True)

    write_markdown(stage_dir / "stage_name.txt", stage_name + "\n")
    json_dump(stage_dir / "input_state.json", summarize_state(state))

    tracer.set_stage(stage_name)
    result = node(state)
    merge_state(state, result)

    output_text = stringify_content(result.get(update_key, ""))
    if not output_text and update_key.endswith("_state"):
        output_text = json.dumps(state.get(update_key, {}), indent=2, ensure_ascii=False)
    elif not output_text:
        output_text = json.dumps(result, indent=2, ensure_ascii=False, default=str)

    write_markdown(stage_dir / "final_output.md", output_text + "\n")
    save_llm_records(stage_dir, stage_name, tracer)

    summary = {
        "stage_name": stage_name,
        "update_key": update_key,
        "warnings": [],
    }
    persist_stage_summary(stage_dir, summary)
    tracer.clear_stage()
    return summary


def build_config(args: argparse.Namespace) -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openai"
    config["quick_think_llm"] = args.quick_model or DEFAULT_CONFIG["quick_think_llm"]
    config["deep_think_llm"] = args.deep_model or DEFAULT_CONFIG["deep_think_llm"]
    config["openai_reasoning_effort"] = args.reasoning_effort
    config["max_debate_rounds"] = args.max_debate_rounds
    config["max_risk_discuss_rounds"] = args.max_risk_rounds
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TradingAgents stages sequentially and save per-analyst traces."
    )
    parser.add_argument("--ticker", required=True, help="Ticker to analyze, for example NVDA.")
    parser.add_argument("--date", required=True, help="Trade date in YYYY-MM-DD format.")
    parser.add_argument(
        "--output-dir",
        default="analyst_access_runs",
        help="Directory where audit artifacts will be written.",
    )
    parser.add_argument("--quick-model", default=None, help="Override the quick model.")
    parser.add_argument("--deep-model", default=None, help="Override the deep model.")
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_CONFIG.get("openai_reasoning_effort"),
        choices=["low", "medium", "high"],
        help="OpenAI reasoning effort.",
    )
    parser.add_argument("--max-debate-rounds", type=int, default=1)
    parser.add_argument("--max-risk-rounds", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    config = build_config(args)

    tracer = StageTraceCallbackHandler()
    graph = TradingAgentsGraph(
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config=config,
        callbacks=[tracer],
    )

    state = graph.propagator.create_initial_state(args.ticker.upper(), args.date)
    conditional_logic = ConditionalLogic(
        max_debate_rounds=config["max_debate_rounds"],
        max_risk_discuss_rounds=config["max_risk_discuss_rounds"],
    )

    run_root = (
        Path(args.output_dir)
        / args.ticker.upper()
        / args.date
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    run_root.mkdir(parents=True, exist_ok=True)

    json_dump(run_root / "config.json", config)

    market_node = create_market_analyst(graph.quick_thinking_llm)
    social_node = create_social_media_analyst(graph.quick_thinking_llm)
    news_node = create_news_analyst(graph.quick_thinking_llm)
    fundamentals_node = create_fundamentals_analyst(graph.quick_thinking_llm)
    bull_node = create_bull_researcher(graph.quick_thinking_llm, graph.bull_memory)
    bear_node = create_bear_researcher(graph.quick_thinking_llm, graph.bear_memory)
    research_manager_node = create_research_manager(
        graph.deep_thinking_llm, graph.invest_judge_memory
    )
    trader_node = create_trader(graph.quick_thinking_llm, graph.trader_memory)
    aggressive_node = create_aggressive_debator(graph.quick_thinking_llm)
    conservative_node = create_conservative_debator(graph.quick_thinking_llm)
    neutral_node = create_neutral_debator(graph.quick_thinking_llm)
    portfolio_manager_node = create_portfolio_manager(
        graph.deep_thinking_llm, graph.portfolio_manager_memory
    )

    summaries: List[Dict[str, Any]] = []

    summaries.append(
        run_tool_backed_stage(
            "Market Analyst",
            "01_market_analyst",
            market_node,
            state,
            "market_report",
            tracer,
            run_root,
        )
    )
    reset_messages(state)

    summaries.append(
        run_tool_backed_stage(
            "Social Media Analyst",
            "02_social_media_analyst",
            social_node,
            state,
            "sentiment_report",
            tracer,
            run_root,
        )
    )
    reset_messages(state)

    summaries.append(
        run_tool_backed_stage(
            "News Analyst",
            "03_news_analyst",
            news_node,
            state,
            "news_report",
            tracer,
            run_root,
        )
    )
    reset_messages(state)

    summaries.append(
        run_tool_backed_stage(
            "Fundamentals Analyst",
            "04_fundamentals_analyst",
            fundamentals_node,
            state,
            "fundamentals_report",
            tracer,
            run_root,
        )
    )
    reset_messages(state)

    research_stage_map = {
        "Bull Researcher": ("05_bull_researcher", bull_node),
        "Bear Researcher": ("06_bear_researcher", bear_node),
    }

    while True:
        next_stage = conditional_logic.should_continue_debate(state)
        if next_stage == "Research Manager":
            break

        slug, node = research_stage_map[next_stage]
        summaries.append(
            run_direct_stage(
                next_stage,
                slug,
                node,
                state,
                "investment_debate_state",
                tracer,
                run_root,
            )
        )

    summaries.append(
        run_direct_stage(
            "Research Manager",
            "07_research_manager",
            research_manager_node,
            state,
            "investment_plan",
            tracer,
            run_root,
        )
    )

    summaries.append(
        run_direct_stage(
            "Trader",
            "08_trader",
            trader_node,
            state,
            "trader_investment_plan",
            tracer,
            run_root,
        )
    )

    risk_stage_map = {
        "Aggressive Analyst": ("09_aggressive_risk_analyst", aggressive_node),
        "Conservative Analyst": ("10_conservative_risk_analyst", conservative_node),
        "Neutral Analyst": ("11_neutral_risk_analyst", neutral_node),
    }

    while True:
        next_stage = conditional_logic.should_continue_risk_analysis(state)
        if next_stage == "Portfolio Manager":
            break

        slug, node = risk_stage_map[next_stage]
        summaries.append(
            run_direct_stage(
                next_stage,
                slug,
                node,
                state,
                "risk_debate_state",
                tracer,
                run_root,
            )
        )

    summaries.append(
        run_direct_stage(
            "Portfolio Manager",
            "12_portfolio_manager",
            portfolio_manager_node,
            state,
            "final_trade_decision",
            tracer,
            run_root,
        )
    )

    write_markdown(
        run_root / "processed_signal.txt",
        graph.process_signal(state["final_trade_decision"]).strip() + "\n",
    )
    json_dump(run_root / "final_state.json", summarize_state(state))
    json_dump(run_root / "run_summary.json", summaries)

    print(f"Analyst access artifacts written to: {run_root}")


if __name__ == "__main__":
    main()
