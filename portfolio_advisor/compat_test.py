"""Smoke test for TradingAgents compatibility.

Run this before every `git pull` on the TradingAgents repository.
Exit code 0 = compatible. Exit code 1 = breaking change detected.

Usage:
    python -m portfolio_advisor.compat_test
"""

from __future__ import annotations

import sys


def _check(label: str, fn) -> bool:
    print(f"  {label}...", end=" ", flush=True)
    try:
        fn()
        print("OK")
        return True
    except Exception as exc:
        print(f"FAILED\n    {exc}")
        return False


def main() -> int:
    print("TradingAgents compatibility check\n")
    passed = True

    def _imports():
        from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: F401
        from tradingagents.default_config import DEFAULT_CONFIG            # noqa: F401
        from tradingagents.agents.utils.rating import parse_rating         # noqa: F401

    passed &= _check("Core imports", _imports)

    def _config_keys():
        from tradingagents.default_config import DEFAULT_CONFIG
        required = {
            "results_dir", "data_cache_dir", "llm_provider",
            "deep_think_llm", "quick_think_llm",
            "max_debate_rounds", "max_risk_discuss_rounds",
        }
        missing = required - set(DEFAULT_CONFIG.keys())
        if missing:
            raise KeyError(f"Missing DEFAULT_CONFIG keys: {missing}")

    passed &= _check("DEFAULT_CONFIG keys", _config_keys)

    def _propagate_signature():
        import inspect
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        params = list(inspect.signature(TradingAgentsGraph.propagate).parameters)
        for expected in ("company_name", "trade_date"):
            if expected not in params:
                raise ValueError(f"propagate() missing param '{expected}'; got {params}")

    passed &= _check("propagate() signature", _propagate_signature)

    def _state_keys():
        import inspect
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        src = inspect.getsource(TradingAgentsGraph._log_state)
        for key in ("final_trade_decision", "risk_debate_state", "investment_plan"):
            if key not in src:
                raise KeyError(f"State key '{key}' missing from _log_state")

    passed &= _check("State keys in _log_state", _state_keys)

    def _rating_parser():
        from tradingagents.agents.utils.rating import parse_rating
        result = parse_rating("**Rating**: Buy")
        if result != "Buy":
            raise ValueError(f"parse_rating returned {result!r}, expected 'Buy'")

    passed &= _check("Rating parser", _rating_parser)

    print()
    if passed:
        print("All checks passed. Safe to upgrade TradingAgents.")
        return 0
    else:
        print("One or more checks failed. Do NOT upgrade until resolved.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
