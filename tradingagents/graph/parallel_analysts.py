"""Parallel execution nodes for TradingAgents.

Provides parallel wrappers for:
- Analyst phase (Market, Social, News, Fundamentals)
- Research debate phase (Bull + Bear)
- Risk debate phase (Aggressive + Conservative + Neutral)
"""

import asyncio
import logging

from langchain_core.messages import HumanMessage, RemoveMessage

logger = logging.getLogger(__name__)


def create_parallel_analyst_node(analyst_fns, tool_nodes, selected_analysts):
    """Create a single LangGraph node that runs all analysts in parallel.

    Each analyst gets its own isolated message state and runs its complete
    tool-calling loop independently. Results are merged at the end.

    Args:
        analyst_fns: dict mapping analyst type (e.g. "market") to node function
        tool_nodes: dict mapping analyst type to ToolNode instance
        selected_analysts: list of analyst types to run
    """

    async def parallel_analysts_node(state):
        """Run all analysts concurrently and merge their reports."""

        async def run_single(analyst_type):
            """Run one analyst through its complete tool-calling loop."""
            fn = analyst_fns[analyst_type]
            tn = tool_nodes[analyst_type]

            # Each analyst gets its own isolated message state
            local_state = {
                "messages": list(state["messages"]),
                "trade_date": state["trade_date"],
                "company_of_interest": state["company_of_interest"],
            }

            result = {}
            for _ in range(10):  # safety limit on tool rounds
                result = await asyncio.to_thread(fn, local_state)
                ai_msg = result["messages"][0]
                local_state["messages"] = local_state["messages"] + [ai_msg]

                if not ai_msg.tool_calls:
                    break

                # Process tool calls
                tool_result = await asyncio.to_thread(tn.invoke, local_state)
                local_state["messages"] = (
                    local_state["messages"] + tool_result["messages"]
                )

            # Return only report fields (not messages)
            return {k: v for k, v in result.items() if k != "messages"}

        # Run all analysts concurrently
        tasks = [run_single(at) for at in selected_analysts if at in analyst_fns]
        results = await asyncio.gather(*tasks)

        # Merge all report fields
        merged = {}
        for r in results:
            merged.update(r)

        # Clear messages and add placeholder (same as Msg Clear nodes)
        messages = state.get("messages", [])
        removal_ops = [
            RemoveMessage(id=m.id)
            for m in messages
            if hasattr(m, "id") and m.id
        ]
        merged["messages"] = removal_ops + [HumanMessage(content="Continue")]

        return merged

    return parallel_analysts_node


def _snapshot_research_state(state):
    """Extract research-relevant fields into a plain dict."""
    return {
        "investment_debate_state": dict(state.get("investment_debate_state", {})),
        "market_report": state.get("market_report", ""),
        "sentiment_report": state.get("sentiment_report", ""),
        "news_report": state.get("news_report", ""),
        "fundamentals_report": state.get("fundamentals_report", ""),
    }


def _snapshot_risk_state(state):
    """Extract risk-relevant fields into a plain dict."""
    return {
        "risk_debate_state": dict(state.get("risk_debate_state", {})),
        "market_report": state.get("market_report", ""),
        "sentiment_report": state.get("sentiment_report", ""),
        "news_report": state.get("news_report", ""),
        "fundamentals_report": state.get("fundamentals_report", ""),
        "trader_investment_plan": state.get("trader_investment_plan", ""),
    }


def create_parallel_research_node(bull_fn, bear_fn):
    """Create a node that runs Bull and Bear researchers in parallel.

    Uses async + asyncio.to_thread + asyncio.gather — the same pattern
    that works for create_parallel_analyst_node.
    """

    async def parallel_research_node(state):
        import time
        import sys

        state_snap = _snapshot_research_state(state)
        t0 = time.time()

        async def run_bull():
            print(f"[PARALLEL] Bull starting at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            result = await asyncio.to_thread(bull_fn, state_snap)
            print(f"[PARALLEL] Bull done at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            return result

        async def run_bear():
            print(f"[PARALLEL] Bear starting at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            result = await asyncio.to_thread(bear_fn, state_snap)
            print(f"[PARALLEL] Bear done at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            return result

        bull_result, bear_result = await asyncio.gather(run_bull(), run_bear())

        print(f"[PARALLEL] Research total: {time.time()-t0:.1f}s", file=sys.stderr, flush=True)

        bull_debate = bull_result["investment_debate_state"]
        bear_debate = bear_result["investment_debate_state"]

        merged_debate = {
            "bull_history": bull_debate.get("bull_history", ""),
            "bear_history": bear_debate.get("bear_history", ""),
            "history": bull_debate.get("bull_history", "")
            + "\n"
            + bear_debate.get("bear_history", ""),
            "current_response": bear_debate.get("current_response", ""),
            "judge_decision": "",
            "count": 2,
        }
        return {"investment_debate_state": merged_debate}

    return parallel_research_node


def create_parallel_risk_node(aggressive_fn, conservative_fn, neutral_fn):
    """Create a node that runs all 3 risk analysts in parallel.

    Uses async + asyncio.to_thread + asyncio.gather — the same pattern
    that works for create_parallel_analyst_node.
    """

    async def parallel_risk_node(state):
        import time
        import sys

        state_snap = _snapshot_risk_state(state)
        t0 = time.time()

        async def run_agg():
            print(f"[PARALLEL] Aggressive starting at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            result = await asyncio.to_thread(aggressive_fn, state_snap)
            print(f"[PARALLEL] Aggressive done at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            return result

        async def run_con():
            print(f"[PARALLEL] Conservative starting at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            result = await asyncio.to_thread(conservative_fn, state_snap)
            print(f"[PARALLEL] Conservative done at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            return result

        async def run_neu():
            print(f"[PARALLEL] Neutral starting at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            result = await asyncio.to_thread(neutral_fn, state_snap)
            print(f"[PARALLEL] Neutral done at +{time.time()-t0:.1f}s", file=sys.stderr, flush=True)
            return result

        agg_result, con_result, neu_result = await asyncio.gather(
            run_agg(), run_con(), run_neu()
        )

        print(f"[PARALLEL] Risk total: {time.time()-t0:.1f}s", file=sys.stderr, flush=True)

        agg_debate = agg_result["risk_debate_state"]
        con_debate = con_result["risk_debate_state"]
        neu_debate = neu_result["risk_debate_state"]

        merged_debate = {
            "aggressive_history": agg_debate.get("aggressive_history", ""),
            "conservative_history": con_debate.get("conservative_history", ""),
            "neutral_history": neu_debate.get("neutral_history", ""),
            "history": agg_debate.get("aggressive_history", "")
            + "\n"
            + con_debate.get("conservative_history", "")
            + "\n"
            + neu_debate.get("neutral_history", ""),
            "latest_speaker": "Neutral",
            "current_aggressive_response": agg_debate.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": con_debate.get(
                "current_conservative_response", ""
            ),
            "current_neutral_response": neu_debate.get(
                "current_neutral_response", ""
            ),
            "judge_decision": "",
            "count": 3,
        }
        return {"risk_debate_state": merged_debate}

    return parallel_risk_node
