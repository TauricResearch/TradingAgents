"""Run the decision evals against a real model:

    python -m tradingagents.pro.evals

Requires provider credentials (e.g. OPENAI_API_KEY) and uses the
ProConfig default model routing. Exits nonzero on failure so CI can gate.
"""

from __future__ import annotations

import sys

from tradingagents.contracts import AssetClass, ProConfig
from tradingagents.pro.evals.harness import run_decision_evals
from tradingagents.pro.models import bundle_from_config


def main() -> int:
    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1)
    bundle = bundle_from_config(config)
    report = run_decision_evals(bundle, config)
    print(report.summary())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
