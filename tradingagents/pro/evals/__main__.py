"""Run the decision evals against a real model:

    python -m tradingagents.pro.evals

Requires provider credentials (e.g. OPENAI_API_KEY) and uses the
ProConfig default model routing. Exits nonzero on failure so CI can gate.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from tradingagents.contracts import AssetClass, ProConfig
from tradingagents.pro.evals.harness import run_decision_evals
from tradingagents.pro.models import bundle_from_config
from tradingagents.pro.observability import CostTrackingLLM


def main() -> int:
    load_dotenv()  # repo-root .env, if present
    from tradingagents.contracts import ModelRouting

    routing = ModelRouting(
        llm_provider=os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "openai"),
        quick_think_llm=os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-5.4-mini"),
        deep_think_llm=os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-5.5"),
    )
    from tradingagents.llm_clients.api_key_env import get_api_key_env

    key_env = get_api_key_env(routing.llm_provider)
    if key_env and not os.environ.get(key_env):
        print(f"{key_env} not set (env or .env); aborting", file=sys.stderr)
        return 2
    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1, models=routing)
    bundle = bundle_from_config(config)
    # track spend on both tiers
    bundle.quick = CostTrackingLLM(bundle.quick)
    deep_tracker = CostTrackingLLM(bundle.deep)
    bundle.deep = deep_tracker if bundle.deep is not bundle.quick else bundle.quick
    report = run_decision_evals(bundle, config, agent_workers=8)
    print(report.summary())
    quick_report = bundle.quick.report
    print(f"\nquick-model calls: {quick_report.calls}, "
          f"est cost ${quick_report.est_cost_usd:.2f}")
    if bundle.deep is not bundle.quick:
        print(f"deep-model calls: {bundle.deep.report.calls}, "
              f"est cost ${bundle.deep.report.est_cost_usd:.2f}")
    total_calls = quick_report.calls + (
        bundle.deep.report.calls if bundle.deep is not bundle.quick else 0
    )
    if total_calls == 0:
        # every stage abstained because the provider never answered — that is
        # a provider/credentials failure, not an eval pass
        print("\nERROR: zero successful model calls (provider outage, bad key, "
              "or insufficient quota); eval results are vacuous", file=sys.stderr)
        return 2
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
