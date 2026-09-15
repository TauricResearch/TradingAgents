"""Token-usage pricing for backtest cost accounting.

A backtest is the one place where the framework's running cost becomes a
first-class result: two configurations with the same alpha are not equally good
if one costs ten times more to produce it. To report that, token counts have to
be converted to dollars.

Deliberately, **no price table is hardcoded here.** Provider prices change on
their own schedule, a table baked into a release is wrong within weeks, and a
stale table is worse than no table because it produces a confident number
nobody re-checks. Instead prices are supplied by the user and anything not
supplied is reported as unpriced — the scorecard then shows token counts and
omits the dollar figures rather than inventing them.

Supply prices either inline in config::

    config["llm_prices"] = {
        "gpt-5.6":      {"input": 1.25, "output": 10.00},
        "gpt-5.6-luna": {"input": 0.15, "output": 0.60},
    }

or as a JSON file of the same shape, pointed at by
``TRADINGAGENTS_LLM_PRICES``. Values are US dollars per one million tokens,
matching how every major provider publishes them.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

TOKENS_PER_PRICE_UNIT = 1_000_000


def load_price_table(config: dict | None = None) -> dict[str, dict[str, float]]:
    """Build the model price table from config and the environment.

    Inline ``config["llm_prices"]`` entries win over the JSON file, so a
    programmatic caller can override one model without rewriting the file. A
    malformed or unreadable file is logged and skipped rather than raising: a
    bad price file should cost you the cost column, not a backtest that has
    already spent real money producing decisions.
    """
    table: dict[str, dict[str, float]] = {}

    path = os.environ.get("TRADINGAGENTS_LLM_PRICES")
    if path:
        try:
            payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
            table.update(_normalize(payload))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Ignoring TRADINGAGENTS_LLM_PRICES at %s: %s. "
                "Costs will be reported as unpriced.", path, exc,
            )

    inline = (config or {}).get("llm_prices")
    if inline:
        try:
            table.update(_normalize(inline))
        except ValueError as exc:
            logger.warning("Ignoring malformed config['llm_prices']: %s", exc)

    return table


def _normalize(payload: object) -> dict[str, dict[str, float]]:
    """Validate a raw price mapping into ``{model: {input, output}}``."""
    if not isinstance(payload, dict):
        raise ValueError("price table must be a mapping of model id to prices")

    out: dict[str, dict[str, float]] = {}
    for model, prices in payload.items():
        if not isinstance(prices, dict) or "input" not in prices or "output" not in prices:
            raise ValueError(f"model {model!r} needs both 'input' and 'output' prices")
        out[str(model)] = {
            "input": float(prices["input"]),
            "output": float(prices["output"]),
        }
    return out


def estimate_cost(
    tokens_in: int,
    tokens_out: int,
    models: list[str],
    table: dict[str, dict[str, float]],
) -> float | None:
    """Estimate the dollar cost of one decision's token usage.

    A run uses two models (deep and quick) and the callback handler reports a
    single pooled token count, so the split between them is not recoverable.
    Rather than guess, the *most expensive* listed model's rates are applied to
    the whole usage, making the figure a documented upper bound. A cost ceiling
    is a defensible thing to publish; a made-up split is not.

    Returns ``None`` when no model in ``models`` has a price, so the caller can
    report tokens without a dollar figure.
    """
    priced = [table[m] for m in models if m in table]
    if not priced:
        return None

    rate = max(priced, key=lambda p: max(p["input"], p["output"]))
    return (
        tokens_in * rate["input"] + tokens_out * rate["output"]
    ) / TOKENS_PER_PRICE_UNIT
