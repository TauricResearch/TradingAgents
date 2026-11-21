"""Subprocess helper for deterministic crash tests.

Exits with code 17 at a requested transaction stage, after the risk gate has written
the named row(s) but before commit. The parent then reopens the SQLite file and
proves that no partial ledger/verdict/outbox state survived.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import (  # noqa: E402
    NOW,
    FixedClock,
    base_evidence_pack,
    base_policy,
    base_portfolio,
    make_proposal,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()

    from egta.risk_gate import RiskGate

    policy = base_policy()
    portfolio = base_portfolio()
    evidence = base_evidence_pack()
    proposal = make_proposal(policy=policy, evidence=evidence, portfolio=portfolio)

    def hook(stage: str) -> None:
        if stage == args.stage:
            os._exit(17)

    gate = RiskGate(
        db_path=Path(args.db),
        policy=policy,
        clock=FixedClock(NOW),
        _fault_hook=hook,
    )
    gate.evaluate_and_commit(proposal, evidence, portfolio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
