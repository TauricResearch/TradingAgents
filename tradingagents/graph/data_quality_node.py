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


def create_data_quality_check(filings_provider=None, sec_facts_provider=None):
    """Build the node. ``filings_provider`` is injectable for tests.

    The default provider reads the filings known at the trade date from SEC
    EDGAR through the freshness module — point-in-time, no look-ahead. A
    provider that raises yields no filings, which the freshness check
    reports as UNAVAILABLE rather than a pass.

    ``sec_facts_provider`` supplies the raw ``companyfacts`` payload used for
    the §4 semantic reconciliation. It runs here, before synthesis, so a
    figure presented under the wrong accounting concept is refused before any
    analyst can build on it.
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

        # §4 — the SEC concept reconciliation. Reported alongside the
        # freshness verdict so the audit shows whether it actually ran.
        sec_reconciliation = _reconcile_sec_concepts(
            sec_facts_provider, ticker, trade_date,
            state.get("fundamentals_report"),
        )
        sec_blocks = bool(
            sec_reconciliation and sec_reconciliation.get("status") == "BLOCKED"
        )
        sec_codes = tuple(sec_reconciliation.get("findings") and
                          [f["code"] for f in sec_reconciliation["findings"]
                           if f.get("blocks")] or ()) if sec_blocks else ()

        logger.info(
            "Data-quality pre-check for %s on %s: blocks_execution=%s codes=%s",
            ticker, trade_date, precheck.blocks_execution or sec_blocks,
            list(precheck.blocking_codes) + list(sec_codes),
        )
        return {
            "data_quality_precheck": {
                **precheck.summary(),
                "notice": precheck.notice(),
                # §4: a semantic mismatch blocks here, before synthesis, so no
                # analyst builds on a figure presented under the wrong concept.
                "blocks_execution": precheck.blocks_execution or sec_blocks,
                "blocking_codes": list(dict.fromkeys(
                    list(precheck.blocking_codes) + list(sec_codes))),
                "sec_reconciliation": sec_reconciliation,
            },
        }

    return data_quality_check_node


def _reconcile_sec_concepts(provider, ticker: str, trade_date: str,
                            fundamentals_report: str | None) -> dict | None:
    """Reconcile the revenue the report states against the filing's concepts.

    Returns ``None`` when no payload is available: an unattempted check is not
    a pass, and inventing a verdict would be worse than saying nothing ran.
    """
    if provider is None:
        return None
    try:
        payload = provider(ticker, trade_date)
    except Exception:  # noqa: BLE001 — an unavailable source is not a pass
        logger.debug("SEC facts provider failed for %s", ticker, exc_info=True)
        return None
    if not isinstance(payload, dict):
        return None

    from tradingagents.dataflows.math.sec_reconciliation import (
        reconcile_revenue,
        sec_facts_from_companyfacts,
    )

    concepts = (
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SegmentReportingInformationRevenue",
    )
    facts = []
    for concept in concepts:
        facts.extend(sec_facts_from_companyfacts(payload, concept))
    if not facts:
        return None

    reported = _revenue_from_report(fundamentals_report)
    if reported is None:
        return None

    verdict = reconcile_revenue(reported, facts, claimed_as_consolidated=True)
    return verdict.summary()


def _revenue_from_report(report: str | None) -> float | None:
    """The revenue figure a fundamentals report states, in base units.

    Reads only an explicitly labelled revenue line, and converts a stated
    millions/billions scale. A figure without a label is not guessed: an
    unattributable number cannot be reconciled, and pretending otherwise
    would certify something nobody identified.
    """
    if not report:
        return None
    import re

    pattern = re.compile(
        r"(?:total\s+revenue|revenues?)\D{0,24}?(\d[\d,\.]*)\s*"
        r"(million|billion|mn|bn|m|b)?",
        re.IGNORECASE,
    )
    match = pattern.search(report)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    scale = (match.group(2) or "").lower()
    if scale in ("billion", "bn", "b"):
        value *= 1_000_000_000
    elif scale in ("million", "mn", "m"):
        value *= 1_000_000
    return value


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
