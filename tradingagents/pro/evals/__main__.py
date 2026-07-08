"""Run the decision evals against a real model:

    python -m tradingagents.pro.evals [--samples N] [--tag TAG] [--limit K]

Requires provider credentials (env or repo-root .env). Provider/model via
TRADINGAGENTS_LLM_PROVIDER / _QUICK_THINK_LLM / _DEEP_THINK_LLM. Exits
nonzero on failure or when the provider never answered, so CI can gate.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from tradingagents.contracts import AssetClass, ModelRouting, ProConfig
from tradingagents.pro.evals.golden import golden_cases
from tradingagents.pro.evals.harness import run_decision_evals
from tradingagents.pro.models import bundle_from_config
from tradingagents.pro.observability import CostTrackingLLM, price_for

EST_COST_PER_CASE_RUN = 0.20  # measured on the first live runs (gpt-5.4-mini/gpt-5.5)


def main() -> int:
    parser = argparse.ArgumentParser(prog="tradingagents.pro.evals")
    parser.add_argument("--samples", type=int, default=1,
                        help="runs per case (default 1)")
    parser.add_argument("--tag", default=None,
                        help="only cases with this tag (direction/ambiguous/"
                             "injection/intraday/gap)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of cases")
    parser.add_argument("--list", action="store_true", help="list cases and exit")
    args = parser.parse_args()

    cases = golden_cases()
    if args.tag:
        cases = [c for c in cases if args.tag in c.tags]
    if args.limit:
        cases = cases[: args.limit]
    if args.list:
        for case in cases:
            print(f"{case.name}  tags={','.join(case.tags)}  {case.notes}")
        return 0

    load_dotenv()  # repo-root .env, if present
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

    n_runs = len(cases) * args.samples
    price_scale = price_for(routing.llm_provider).input_per_mtok / 3.0
    est = n_runs * EST_COST_PER_CASE_RUN * price_scale
    print(f"running {len(cases)} cases x {args.samples} samples = {n_runs} "
          f"pipeline runs (~${est:.2f} estimated at {routing.llm_provider} rates)\n")

    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1, models=routing)
    # low temperature for eval comparability across runs; note reasoning
    # models may ignore it and no setting makes runs bit-identical (see the
    # base README's reproducibility section) — N-sample stats are the fix
    bundle = bundle_from_config(config, temperature=0.2)
    price = price_for(routing.llm_provider)
    bundle.quick = CostTrackingLLM(bundle.quick, price=price)
    deep_tracker = CostTrackingLLM(bundle.deep, price=price)
    bundle.deep = deep_tracker if bundle.deep is not bundle.quick else bundle.quick

    report = run_decision_evals(bundle, config, cases=cases,
                                samples=args.samples, agent_workers=8)
    print(report.summary())
    quick_report = bundle.quick.report
    print(f"\nquick-model calls: {quick_report.calls}, "
          f"est cost ${quick_report.est_cost_usd:.2f}")
    total_calls = quick_report.calls
    if bundle.deep is not bundle.quick:
        print(f"deep-model calls: {bundle.deep.report.calls}, "
              f"est cost ${bundle.deep.report.est_cost_usd:.2f}")
        total_calls += bundle.deep.report.calls
    if total_calls == 0:
        # every stage abstained because the provider never answered — that is
        # a provider/credentials failure, not an eval pass
        print("\nERROR: zero successful model calls (provider outage, bad key, "
              "or insufficient quota); eval results are vacuous", file=sys.stderr)
        return 2
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
