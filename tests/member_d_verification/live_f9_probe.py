"""Opt-in real-model F9 diagnostics using synthetic evidence, never a formal PASS.

Run: python tests/member_d_verification/live_f9_probe.py --live
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow real provider calls")
    args = parser.parse_args()
    if not args.live:
        parser.error("Explicit --live is required")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
    from tradingagents.agents.trader.trader import create_trader
    from tradingagents.dataflows.config import run_config
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients import create_tier_client
    from tradingagents.portfolio import PortfolioContext
    from tradingagents.runapi.execution import _prompt_hash, _source_revision
    from tradingagents.runapi.redact import Redactor

    config = dict(DEFAULT_CONFIG)
    # Short, controlled prompts; no vendor tools or actual market data are used.
    config.update(context_cap_tokens=3000, compaction_threshold_tokens=2500)
    llm = create_tier_client(config, "deep").get_llm()
    redactor = Redactor()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / ".local-review" / f"f9-diagnostic-{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    metadata = {"kind": "diagnostic", "formal_gate_pass": False,
                "source_revision": _source_revision(), "prompt_hash": _prompt_hash([]),
                "provider": config.get("llm_provider"), "model": config.get("deep_think_llm"),
                "context_cap_tokens": 3000, "compaction_threshold_tokens": 2500,
                "started": 0, "completed": 0, "records": records}
    cases = [
        ("no-portfolio", None), ("explicit-empty", {"positions": []}),
        ("other-ticker", {"positions": [{"ticker": "MSFT", "quantity": 5}]}),
        ("held-target-unknown-cash", {"positions": [{"ticker": "AAPL", "quantity": 10}]}),
        ("explicit-empty-known-cash", {"positions": [], "cash": 1000}),
    ]
    for case_id, payload in cases:
        row = {"case_id": case_id, "outcome": "INCOMPLETE", "synthetic_inputs": True}
        records.append(row)
        metadata["started"] += 1
        output.write_text(json.dumps(redactor.scrub(metadata), indent=2), encoding="utf-8")
        try:
            portfolio = PortfolioContext.model_validate(payload) if payload is not None else None
            state = {"company_of_interest": "AAPL", "market_report": "Synthetic diagnostic only. No verified market prices.",
                     "portfolio_context": portfolio.render("AAPL") if portfolio is not None else "",
                     "investment_plan": "Synthetic bearish thesis. Upstream draft says reduce existing exposure; verify that ownership assumption against the supplied snapshot.",
                     "risk_debate_state": dict.fromkeys(["history", "aggressive_history", "conservative_history", "neutral_history",
                         "current_aggressive_response", "current_conservative_response", "current_neutral_response"], "Synthetic evidence is thin. Do not invent missing facts.")}
            state["risk_debate_state"].update(count=1, latest_speaker="Neutral")
            with run_config(config):
                trader = create_trader(llm)(state)
                state.update(trader)
                row["trader"] = trader["trader_investment_plan"]
                pm = create_portfolio_manager(llm)(state)
                row["portfolio_manager"] = pm["final_trade_decision"]
                row["rating"] = pm["final_rating"]
            row["outcome"] = "COMPLETED"
            metadata["completed"] += 1
        except Exception as exc:
            row["error"] = redactor.diagnostic(exc)
        output.write_text(json.dumps(redactor.scrub(metadata), indent=2), encoding="utf-8")
        print(f"{case_id}: {row['outcome']}", flush=True)
    print(f"Diagnostic evidence: {output}", flush=True)
    return 0 if metadata["started"] == metadata["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
