"""The graph's deterministic data-quality node.

Placed between the analysts and the research debate, this node runs the
same checks the Execution Gate applies at the end of the run — but early
enough that the Research Manager and Portfolio Manager see the findings
before they conclude. Without it, a report built on a stale filing and a
contradicted percentage is debated in full and only its *order* is blocked
at the end: the analysis stays wrong, and a repeated run reproduces the
same wrong conclusion.

The node is pure: no LLM, no network. It reads the analysts' reports from
the state, computes the verdicts, and returns both the verdicts (for the
gate to reuse, so the two stages cannot disagree) and a plain-text notice
for the managers' prompts.
"""

from __future__ import annotations

import logging

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.data_gate import precheck_data_quality
from tradingagents.dataflows.filing_freshness import used_period_end_from_report

logger = logging.getLogger(__name__)


def create_data_quality_check(filings_provider=None):
    """Build the node. ``filings_provider`` is injectable for tests.

    The default provider reads the filings known at the trade date from SEC
    EDGAR through the freshness module — point-in-time, no look-ahead. A
    provider that raises yields no filings, which the freshness check
    reports as UNAVAILABLE rather than a pass.
    """

    def data_quality_check_node(state) -> dict:
        ticker = state.get("company_of_interest", "")
        trade_date = str(state.get("trade_date", ""))

        config = get_config()
        filings = None
        if config.get("fundamentals_freshness_gate", True):
            filings = _resolve_filings(filings_provider, ticker, trade_date)

        used_end = used_period_end_from_report(state.get("fundamentals_report"))

        precheck = precheck_data_quality(
            trade_date=trade_date,
            filings=filings,
            used_fundamentals_period_end=used_end,
        )

        logger.info(
            "Data-quality pre-check for %s on %s: blocks_execution=%s codes=%s",
            ticker, trade_date, precheck.blocks_execution,
            list(precheck.blocking_codes),
        )
        return {
            "data_quality_precheck": {
                **precheck.summary(),
                "notice": precheck.notice(),
            },
        }

    return data_quality_check_node


def _resolve_filings(provider, ticker: str, trade_date: str):
    """The filings known at the trade date, or None when unavailable."""
    if provider is not None:
        try:
            return provider(ticker, trade_date)
        except Exception:  # noqa: BLE001 — an unavailable source is not a pass
            logger.debug("Filings provider failed for %s", ticker, exc_info=True)
            return []
    try:
        from tradingagents.dataflows.filing_freshness import filings_from_sec_edgar

        return filings_from_sec_edgar(ticker, trade_date)
    except Exception:  # noqa: BLE001 — same rule as above
        logger.debug("SEC extraction failed for %s", ticker, exc_info=True)
        return []
