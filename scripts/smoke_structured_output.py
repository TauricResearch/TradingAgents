"""
End-to-end smoke for structured-output agents against a real LLM provider.

New feature added:
1. JSON report export with --save-report
2. Per-stage execution timing
3. Optional quiet mode (--quiet)

Usage:
    OPENAI_API_KEY=... python scripts/smoke_structured_output.py openai
    python scripts/smoke_structured_output.py openai --save-report report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.trader.trader import create_trader
from tradingagents.graph.signal_processing import SignalProcessor
from tradingagents.llm_clients import create_llm_client


PROVIDER_DEFAULTS = {
    "openai": ("gpt-5.4-mini", None),
    "google": ("gemini-2.5-flash", None),
    "anthropic": ("claude-sonnet-4-6", None),
    "deepseek": ("deepseek-chat", None),
    "qwen": ("qwen-plus", None),
    "glm": ("glm-5", None),
    "xai": ("grok-4", None),
}

DEBATE_HISTORY = """
Bull Analyst: NVDA's data-center revenue grew 60% YoY last quarter, driven by
Blackwell ramp; sovereign AI deals with multiple governments add a $40B+
multi-year tailwind. Margins remain above peer average.

Bear Analyst: Concentration risk is real — top three customers are >40% of
revenue. Any pause in hyperscaler capex would compress the multiple. China
export restrictions still cap a meaningful portion of demand.
"""


def make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": DEBATE_HISTORY,
            "bull_history": "Bull Analyst: NVDA's data-center revenue grew 60% YoY...",
            "bear_history": "Bear Analyst: Concentration risk is real...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def make_trader_state(investment_plan: str):
    return {
        "company_of_interest": "NVDA",
        "investment_plan": investment_plan,
    }


def make_pm_state(investment_plan: str, trader_plan: str):
    return {
        "company_of_interest": "NVDA",
        "past_context": "",
        "risk_debate_state": {
            "history": "Aggressive: lean in. Conservative: trim. Neutral: balanced sizing.",
            "aggressive_history": "Aggressive: ...",
            "conservative_history": "Conservative: ...",
            "neutral_history": "Neutral: ...",
            "judge_decision": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 1,
        },
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "investment_plan": investment_plan,
        "trader_investment_plan": trader_plan,
    }


def section(title: str, content: str, quiet: bool):
    if quiet:
        return
    line = "=" * 70
    print(f"\n{line}\n{title}\n{line}\n{content}")


def timed_call(fn, *args, **kwargs):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    end = time.perf_counter()
    return result, round(end - start, 3)


def validate(outputs):
    required = {
        "Research Manager": ["**Recommendation**:"],
        "Trader": ["**Action**:", "FINAL TRANSACTION PROPOSAL:"],
        "Portfolio Manager": [
            "**Rating**:",
            "**Executive Summary**:",
            "**Investment Thesis**:",
        ],
    }

    failures = []

    for name, text in outputs.items():
        for marker in required[name]:
            if marker not in text:
                failures.append(f"{name} missing {marker}")

    return failures


def save_json(path: str, data: dict):
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Structured Output Smoke Test")
    parser.add_argument("provider", choices=PROVIDER_DEFAULTS.keys())
    parser.add_argument("--deep-model", default=None)
    parser.add_argument("--quick-model", default=None)
    parser.add_argument("--save-report", default=None, help="Save JSON report")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    default_model, _ = PROVIDER_DEFAULTS[args.provider]
    deep_model = args.deep_model or default_model
    quick_model = args.quick_model or default_model

    if not args.quiet:
        print("Provider:", args.provider)
        print("Deep model:", deep_model)
        print("Quick model:", quick_model)

    deep_client = create_llm_client(provider=args.provider, model=deep_model)
    quick_client = create_llm_client(provider=args.provider, model=quick_model)

    deep_llm = deep_client.get_llm()
    quick_llm = quick_client.get_llm()

    rm = create_research_manager(deep_llm)
    trader = create_trader(quick_llm)
    pm = create_portfolio_manager(deep_llm)
    sp = SignalProcessor()

    rm_result, t1 = timed_call(rm, make_rm_state())
    investment_plan = rm_result["investment_plan"]
    section("[1] Research Manager", investment_plan, args.quiet)

    trader_result, t2 = timed_call(trader, make_trader_state(investment_plan))
    trader_plan = trader_result["trader_investment_plan"]
    section("[2] Trader", trader_plan, args.quiet)

    pm_result, t3 = timed_call(pm, make_pm_state(investment_plan, trader_plan))
    final_decision = pm_result["final_trade_decision"]
    section("[3] Portfolio Manager", final_decision, args.quiet)

    rating, t4 = timed_call(sp.process_signal, final_decision)
    section("[4] SignalProcessor", rating, args.quiet)

    outputs = {
        "Research Manager": investment_plan,
        "Trader": trader_plan,
        "Portfolio Manager": final_decision,
    }

    failures = validate(outputs)

    if not args.quiet:
        print("\n" + "=" * 70)
        print("Timing Summary")
        print("=" * 70)
        print(f"Research Manager : {t1}s")
        print(f"Trader           : {t2}s")
        print(f"Portfolio Manager: {t3}s")
        print(f"SignalProcessor  : {t4}s")

    report = {
        "provider": args.provider,
        "deep_model": deep_model,
        "quick_model": quick_model,
        "rating": rating,
        "timings": {
            "research_manager": t1,
            "trader": t2,
            "portfolio_manager": t3,
            "signal_processor": t4,
        },
        "status": "PASSED" if not failures else "FAILED",
        "failures": failures,
    }

    if args.save_report:
        save_json(args.save_report, report)
        print(f"\nReport saved to {args.save_report}")

    if failures:
        print("\nSmoke FAILED")
        for item in failures:
            print("-", item)
        return 1

    print(f"\nSmoke PASSED for {args.provider}")
    return 0


if __name__ == "__main__":
    sys.exit(main())    "anthropic": ("claude-sonnet-4-6", None),
    "deepseek": ("deepseek-chat", None),
    "qwen": ("qwen-plus", None),
    "glm": ("glm-5", None),
    "xai": ("grok-4", None),
}


# Minimal but realistic state for the three agents.
DEBATE_HISTORY = """
Bull Analyst: NVDA's data-center revenue grew 60% YoY last quarter, driven by
Blackwell ramp; sovereign AI deals with multiple governments add a $40B+
multi-year tailwind. Margins remain above peer average.

Bear Analyst: Concentration risk is real — top three customers are >40% of
revenue. Any pause in hyperscaler capex would compress the multiple. China
export restrictions still cap a meaningful portion of demand.
"""


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": DEBATE_HISTORY,
            "bull_history": "Bull Analyst: NVDA's data-center revenue grew 60% YoY...",
            "bear_history": "Bear Analyst: Concentration risk is real...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _make_trader_state(investment_plan: str):
    return {
        "company_of_interest": "NVDA",
        "investment_plan": investment_plan,
    }


def _make_pm_state(investment_plan: str, trader_plan: str):
    return {
        "company_of_interest": "NVDA",
        "past_context": "",
        "risk_debate_state": {
            "history": "Aggressive: lean in. Conservative: trim. Neutral: balanced sizing.",
            "aggressive_history": "Aggressive: ...",
            "conservative_history": "Conservative: ...",
            "neutral_history": "Neutral: ...",
            "judge_decision": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 1,
        },
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "investment_plan": investment_plan,
        "trader_investment_plan": trader_plan,
    }


def _print_section(title: str, content: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n{title}\n{bar}\n{content}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=list(PROVIDER_DEFAULTS.keys()))
    parser.add_argument("--deep-model", default=None, help="Override deep_think_llm")
    parser.add_argument("--quick-model", default=None, help="Override quick_think_llm")
    args = parser.parse_args()

    default_model, _ = PROVIDER_DEFAULTS[args.provider]
    deep_model = args.deep_model or default_model
    quick_model = args.quick_model or default_model

    print(f"Provider: {args.provider}")
    print(f"Deep model:  {deep_model}")
    print(f"Quick model: {quick_model}")

    # Build the LLM clients via the framework's factory.
    deep_client = create_llm_client(provider=args.provider, model=deep_model)
    quick_client = create_llm_client(provider=args.provider, model=quick_model)
    deep_llm = deep_client.get_llm()
    quick_llm = quick_client.get_llm()

    # 1) Research Manager
    rm = create_research_manager(deep_llm)
    rm_result = rm(_make_rm_state())
    investment_plan = rm_result["investment_plan"]
    _print_section("[1] Research Manager — investment_plan", investment_plan)

    # 2) Trader (consumes RM's plan)
    trader = create_trader(quick_llm)
    trader_result = trader(_make_trader_state(investment_plan))
    trader_plan = trader_result["trader_investment_plan"]
    _print_section("[2] Trader — trader_investment_plan", trader_plan)

    # 3) Portfolio Manager (consumes both)
    pm = create_portfolio_manager(deep_llm)
    pm_result = pm(_make_pm_state(investment_plan, trader_plan))
    final_decision = pm_result["final_trade_decision"]
    _print_section("[3] Portfolio Manager — final_trade_decision", final_decision)

    # 4) SignalProcessor extracts the rating with zero LLM calls.
    sp = SignalProcessor()
    rating = sp.process_signal(final_decision)
    _print_section("[4] SignalProcessor → rating", rating)

    # 5) Lightweight checks: each rendered output should carry the expected
    #    section headers so downstream consumers (memory log, CLI display,
    #    saved reports) keep working.
    checks = [
        ("Research Manager", investment_plan, ["**Recommendation**:"]),
        ("Trader",           trader_plan,     ["**Action**:", "FINAL TRANSACTION PROPOSAL:"]),
        ("Portfolio Manager", final_decision, ["**Rating**:", "**Executive Summary**:", "**Investment Thesis**:"]),
    ]
    print("\n" + "=" * 70 + "\nStructure checks\n" + "=" * 70)
    failures = 0
    for name, text, required in checks:
        for marker in required:
            ok = marker in text
            print(f"  {'PASS' if ok else 'FAIL'}  {name}: contains {marker!r}")
            failures += int(not ok)

    print()
    if failures:
        print(f"Smoke FAILED: {failures} structure check(s) missing.")
        return 1
    print("Smoke PASSED: structured output → rendered markdown chain works for", args.provider)
    return 0


if __name__ == "__main__":
    sys.exit(main())
