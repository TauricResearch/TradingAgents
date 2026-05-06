"""Programmatic example for invoking the Kalshi prediction-market pipeline.

Runs the full agent committee on a Kalshi BTC daily contract in paper
mode (default — switch to live by passing ``requested_live=True`` AND
disabling ``paper_mode`` in config AND clearing the
``TRADINGAGENTS_LIVE_DISABLED`` env var).
"""

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.execution.runner import run_contract

load_dotenv()

# Custom config — paper-only by default, see ``tradingagents/default_config.py``
# for the full set of knobs.
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 1

# A Kalshi BTC daily contract id has the shape KXBTCD-<DATE>-T<STRIKE>.
# Example: BTC closes above $100,000 on 2026-05-05.
result = run_contract(
    contract_id="KXBTCD-26MAY05-T100000",
    trade_date="2026-05-05",
    requested_live=False,  # paper by default — flip to True only when ready
    config=config,
)

print(result.final_decision_markdown)
print()
print(f"Mode: {result.mode}")
print(f"Decision id: {result.decision_id}")
if result.stake_plan is not None:
    print(
        f"Stake: {result.stake_plan.contract_count} contracts of "
        f"{result.stake_plan.side.value} at {result.stake_plan.price_cents}c "
        f"= ${result.stake_plan.stake_usd:,.2f}"
    )
print(f"Notes: {result.notes}")
