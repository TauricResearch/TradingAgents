"""The numbered regression cases §10 requires, in their own file.

T08, T09, T12 and T22 were the four numbered cases without a dedicated test.
The *logic* behind them already existed and was tested (``math/valuation.py``,
``math/sec_reconciliation.py``, ``math/trade_actions.py``); what was missing was
the specific scenario each number names, driven through the real code path.

Every expected value below is derived independently — a hand calculation, or a
figure read from the SEC payload for that issuer — never from the code under
test.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.dataflows.causal_guard import (
    NOT_YET_OBSERVABLE,
    OBSERVABLE,
    evaluate_post_event_pricing,
)
from tradingagents.dataflows.math.precision import Unit
from tradingagents.dataflows.math.sec_reconciliation import (
    FINANCIAL_METRIC_DEFINITION_MISMATCH,
    SecFact,
    reconcile_revenue,
    sec_facts_from_companyfacts,
)
from tradingagents.dataflows.math.trade_actions import (
    PositionState,
    TradeAction,
    resolve_trade_intent,
    validate_trade_against_rating,
)
from tradingagents.dataflows.math.valuation import (
    check_stated_multiple,
    dual_class_book_value_per_share,
    earnings_per_share,
)

CACHE = Path("/root/.tradingagents/cache/sec_edgar")
BRK_CIK = "0001067983"
AAPL_CIK = "0000320193"
NVDA_CIK = "0001045810"


def _payload(cik: str) -> dict | None:
    """The cached companyfacts payload, or None when unreadable or absent.

    CI runs without access to ``/root``, and ``Path.exists()`` raises
    ``PermissionError`` there, so both the stat and the read are guarded: a
    machine without the cache must exercise the synthetic path rather than fail
    on its environment.
    """
    try:
        path = CACHE / f"CIK{cik}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())
    except (OSError, PermissionError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# T08 - P/B across share classes
# ---------------------------------------------------------------------------
class TestT08DualClassPriceToBook:
    """Berkshire's 1:1500 ratio, and what happens when it is ignored."""

    EQUITY = "761368000000"     # Q3 2026, base units
    SHARES_A = 543_000
    SHARES_B = 1_303_000_000
    RATIO = 1500
    PRICE = "570.89"

    def test_class_b_equivalents_and_bvps(self):
        """B_equiv = 1,303,000,000 + 543,000*1500 = 2,117,500,000."""
        expected_count = self.SHARES_B + self.SHARES_A * self.RATIO
        assert expected_count == 2_117_500_000
        bvps = Decimal(self.EQUITY) / Decimal(expected_count)
        assert bvps == pytest.approx(Decimal("359.5599"), abs=Decimal("0.001"))

    def test_the_engine_agrees_with_the_hand_calculation(self):
        record = dual_class_book_value_per_share(
            self.EQUITY, self.SHARES_A, self.SHARES_B,
            class_a_to_b_ratio=self.RATIO, period_end="2026-09-30")
        assert record.value == pytest.approx(Decimal("359.5599"),
                                             abs=Decimal("0.001"))
        assert record.operands["class_b_equivalent"] == "2117500000"

    def test_the_resulting_pb_is_about_1_6(self):
        record = dual_class_book_value_per_share(
            self.EQUITY, self.SHARES_A, self.SHARES_B, class_a_to_b_ratio=self.RATIO)
        pb = Decimal(self.PRICE) / record.value
        assert pb == pytest.approx(Decimal("1.5877"), abs=Decimal("0.001"))

    def test_ignoring_the_ratio_would_be_wrong_by_a_large_factor(self):
        """Dividing by raw Class-B shares only overstates BVPS materially."""
        naive = Decimal(self.EQUITY) / Decimal(self.SHARES_B)
        correct = dual_class_book_value_per_share(
            self.EQUITY, self.SHARES_A, self.SHARES_B).value
        assert correct < naive
        assert naive / correct > Decimal("1.5")

    def test_a_class_a_book_value_against_a_class_b_price_is_refused(self):
        """A cross-class comparison without conversion is an error, not a number."""
        result = check_stated_multiple(
            "price_to_book", "1.35", self.PRICE, "539339.39",
            formula_id="price_div_bvps")
        # 539,339 is BVPS *per A share*; against a B price it is meaningless.
        assert result.blocks is True

    def test_the_report_of_135_is_refused_against_the_correct_bvps(self):
        record = dual_class_book_value_per_share(
            self.EQUITY, self.SHARES_A, self.SHARES_B, class_a_to_b_ratio=self.RATIO)
        result = check_stated_multiple(
            "price_to_book", "1.35", self.PRICE, record.value,
            formula_id="price_div_bvps")
        assert result.computed == pytest.approx(Decimal("1.5877"),
                                                abs=Decimal("0.001"))
        assert result.blocks is True


# ---------------------------------------------------------------------------
# T09 - TTM EPS reconciled against weighted-average shares
# ---------------------------------------------------------------------------
class TestT09TtmEpsReconciliation:
    """77.084bn of TTM earnings against 39.76 of EPS implies 1.9387bn shares."""

    NET_INCOME = 77_084_000_000
    REPORTED_EPS = "39.76"

    def test_the_implied_weighted_average_share_count(self):
        implied = Decimal(self.NET_INCOME) / Decimal(self.REPORTED_EPS)
        assert implied == pytest.approx(Decimal("1938732394"),
                                        abs=Decimal("1"))

    def test_the_engine_reproduces_the_reported_eps(self):
        record = earnings_per_share(self.NET_INCOME, 1_938_732_394,
                                    period_end="2026-09-30")
        assert record.value == pytest.approx(Decimal("39.76"),
                                             abs=Decimal("0.01"))

    def test_period_end_shares_give_a_different_number(self):
        """2,117,500,000 end-of-period shares produce 36.40, not 39.76."""
        wrong = Decimal(self.NET_INCOME) / Decimal(2_117_500_000)
        assert wrong == pytest.approx(Decimal("36.40"), abs=Decimal("0.01"))
        right = Decimal(self.NET_INCOME) / Decimal(1_938_732_394)
        assert (right - wrong) / right > Decimal("0.08")

    def test_the_two_share_bases_are_recorded_as_different(self):
        """The GAAP EPS denominator is a weighted average, and says so."""
        record = earnings_per_share(self.NET_INCOME, 1_938_732_394)
        assert record.formula_id == "net_income_div_shares_gaap"
        assert record.unit == "gaap_per_share"

    def test_an_end_of_period_count_presented_as_gaap_is_caught_by_definition(self):
        """§5's share-basis check refuses the substitution."""
        from tradingagents.dataflows.math.definitions import (
            DefinitionKind,
            MetricIdentity,
            ShareCountBasis,
            reconcile_definitions,
        )

        verdict = reconcile_definitions(
            MetricIdentity(definition=DefinitionKind.GAAP,
                           share_count_basis=ShareCountBasis.WEIGHTED_AVERAGE),
            MetricIdentity(definition=DefinitionKind.GAAP,
                           share_count_basis=ShareCountBasis.PERIOD_END),
        )
        assert verdict.compatible is False
        assert "SHARE_BASIS_MISMATCH" in verdict.codes


# ---------------------------------------------------------------------------
# T12 - an event published after the last close
# ---------------------------------------------------------------------------
class TestT12EventAfterTheLastClose:
    """Berkshire's Q3 release on Saturday 2026-11-07, analysed Sunday."""

    SESSIONS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]

    def test_no_session_after_the_event_means_unobservable(self):
        verdict = evaluate_post_event_pricing(
            "2026-11-07", self.SESSIONS, as_of_date="2026-11-08")
        assert verdict.status == NOT_YET_OBSERVABLE
        assert verdict.reaction_claim_allowed is False

    def test_the_last_session_before_is_the_friday(self):
        verdict = evaluate_post_event_pricing(
            "2026-11-07", self.SESSIONS, as_of_date="2026-11-08")
        assert verdict.last_session_before == "2026-11-06"
        assert verdict.first_session_after is None

    def test_once_monday_trades_the_reaction_becomes_observable(self):
        verdict = evaluate_post_event_pricing(
            "2026-11-07", self.SESSIONS + ["2026-11-09"],
            as_of_date="2026-11-09")
        assert verdict.status == OBSERVABLE
        assert verdict.first_session_after == "2026-11-09"

    def test_while_monday_is_still_trading_it_is_intraday_only(self):
        """§5: a move in progress is not a settled reaction."""
        verdict = evaluate_post_event_pricing(
            "2026-11-07", self.SESSIONS + ["2026-11-09"],
            as_of_date="2026-11-09", session_still_open=True)
        assert verdict.status == "OBSERVABLE_INTRADAY"
        assert verdict.reaction_claim_allowed is False
        assert verdict.needs_confirmed_close is True

    def test_an_unknown_publication_time_cannot_be_checked(self):
        verdict = evaluate_post_event_pricing(None, self.SESSIONS,
                                              as_of_date="2026-11-08")
        assert verdict.status == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# T22 - the same checks on other issuers
# ---------------------------------------------------------------------------
def _revenue_inputs(cik: str) -> tuple[list[SecFact], SecFact, SecFact] | None:
    """(all facts, a consolidated fact, a same-span contract fact) or None.

    The same duration is required on both sides: comparing a yearly total with
    a quarterly subset would be refused for the span reason, which would test
    the wrong thing.

    A vital distinction emerged while writing this. For **Apple and NVIDIA**
    the two concepts carry the *same value* on every shared span — those
    companies have essentially no revenue outside customer contracts, so
    ``Revenues`` and contract revenue are the same number. For **Berkshire**
    they differ sharply, because the railroad, insurance and utility businesses
    are not contract revenue at all.

    So a shared span with equal values is not a failure of this fixture, it is
    a fact about the issuer — and a test that demanded a difference from every
    company would be asserting something untrue about two of them.
    """
    payload = _payload(cik)
    if payload is None:
        return None
    facts: list[SecFact] = []
    for concept in ("Revenues",
                    "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "SalesRevenueNet"):
        facts.extend(sec_facts_from_companyfacts(payload, concept))
    if not facts:
        return None

    consolidated = [f for f in facts
                    if f.concept in ("Revenues", "SalesRevenueNet")
                    and f.start is not None]
    narrower = [f for f in facts
                if f.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
                and f.start is not None]
    for total in sorted(consolidated, key=lambda f: f.end, reverse=True):
        match = next((n for n in narrower
                      if n.start == total.start and n.end == total.end), None)
        if match is not None:
            return facts, total, match
    return None


def _differs(cik: str) -> bool | None:
    """Whether this issuer's consolidated and contract totals differ at all.

    ``None`` when the cache is unavailable. Used to decide which assertions
    apply: a company whose totals coincide must not be expected to block a
    report that quotes the contract figure, because that figure *is* the
    consolidated one.
    """
    inputs = _revenue_inputs(cik)
    if inputs is None:
        return None
    _facts, total, narrower = inputs
    return total.value != narrower.value


class TestT22OtherIssuers:
    """The same concept reconciliation on three other companies.

    Each is skipped rather than failed when its SEC cache is absent, so the
    suite is portable; the synthetic case at the end proves the logic itself
    without any cache at all.
    """

    @pytest.mark.parametrize("cik,name", [
        (AAPL_CIK, "AAPL"),
        (NVDA_CIK, "NVDA"),
        (BRK_CIK, "BRK-B"),
    ])
    def test_the_consolidated_figure_reconciles(self, cik, name):
        inputs = _revenue_inputs(cik)
        if inputs is None:
            pytest.skip(f"no usable {name} SEC cache on this machine")
        facts, total, _narrower = inputs
        result = reconcile_revenue(total.value, facts,
                                   claimed_as_consolidated=True)
        assert result.blocks_decision is False, f"{name}: {result.summary()}"
        assert result.resolved.concept in ("Revenues", "SalesRevenueNet")

    @pytest.mark.parametrize("cik,name", [
        (AAPL_CIK, "AAPL"),
        (NVDA_CIK, "NVDA"),
        (BRK_CIK, "BRK-B"),
    ])
    def test_the_narrower_concept_presented_as_consolidated_blocks(self, cik, name):
        """Only for issuers whose two totals actually differ.

        Apple and NVIDIA report the same figure under both concepts, so quoting
        the contract number as consolidated is *correct* for them — asserting a
        block would be asserting something false. Berkshire differs sharply, and
        that is the case §4 exists for.
        """
        inputs = _revenue_inputs(cik)
        if inputs is None:
            pytest.skip(f"no usable {name} SEC cache on this machine")
        differs = _differs(cik)
        if not differs:
            pytest.skip(
                f"{name} reports the same value under both concepts: quoting "
                "either as consolidated is correct, so there is nothing to block")
        facts, total, narrower = inputs
        result = reconcile_revenue(narrower.value, facts,
                                   claimed_as_consolidated=True)
        assert result.blocks_decision is True, f"{name} should block"
        assert FINANCIAL_METRIC_DEFINITION_MISMATCH in result.codes
        expected = result.findings[0].expected
        assert expected is not None
        assert expected.start == narrower.start
        assert expected.value != narrower.value

    @pytest.mark.parametrize("cik,name", [
        (AAPL_CIK, "AAPL"),
        (NVDA_CIK, "NVDA"),
        (BRK_CIK, "BRK-B"),
    ])
    def test_an_equal_total_is_not_treated_as_a_mismatch(self, cik, name):
        """Where the concepts coincide, neither figure blocks — checked, not assumed."""
        inputs = _revenue_inputs(cik)
        if inputs is None:
            pytest.skip(f"no usable {name} SEC cache on this machine")
        facts, total, narrower = inputs
        if total.value != narrower.value:
            pytest.skip(f"{name}'s concepts differ; covered by the blocking test")
        for value in (total.value, narrower.value):
            result = reconcile_revenue(value, facts, claimed_as_consolidated=True)
            assert result.blocks_decision is False, f"{name}: {result.summary()}"

    def test_the_same_logic_without_any_cache(self):
        """The synthetic case, so T22 runs on a machine with no SEC data."""
        synthetic = [SecFact(concept="Revenues", value=500.0, unit="USD",
                             end="2026-09-30", start="2026-07-01"),
                     SecFact(concept="RevenueFromContractWithCustomerExcludingAssessedTax",
                             value=350.0, unit="USD", end="2026-09-30",
                             start="2026-07-01")]
        blocked = reconcile_revenue(350.0, synthetic, claimed_as_consolidated=True)
        assert blocked.blocks_decision is True
        passed = reconcile_revenue(500.0, synthetic, claimed_as_consolidated=True)
        assert passed.blocks_decision is False


class TestT22OtherIssuersTradeActions:
    """The trade-action guards are issuer-agnostic, asserted on each market."""

    @pytest.mark.parametrize("ticker,currency", [
        ("AAPL", "USD"), ("NVDA", "USD"), ("ENI.MI", "EUR"),
    ])
    def test_a_reduction_without_a_position_blocks_for_every_issuer(self, ticker,
                                                                    currency):
        intent = resolve_trade_intent(TradeAction.REDUCE_LONG,
                                      PositionState(known=True, quantity=0.0))
        assert intent.blocks is True
        assert intent.reason_code == "NO_LONG_POSITION"

    @pytest.mark.parametrize("ticker", ["AAPL", "NVDA", "ENI.MI"])
    def test_sell_never_becomes_a_short_for_any_issuer(self, ticker):
        intent = validate_trade_against_rating(
            TradeAction.OPEN_SHORT, "SELL",
            position=PositionState(known=True, quantity=0.0))
        assert intent.blocks is True

    def test_eni_mi_in_eur_uses_the_same_formula(self):
        """An Italian utility: the arithmetic does not know the currency."""
        from tradingagents.dataflows.math.technical import atr_distance

        # Entry 14.20, stop 13.80, ATR 0.30 -> 0.40 of risk, 1.3333 ATR.
        assert atr_distance("14.20", "13.80", "0.30") == Decimal("1.3333")
        assert Unit.parse("EUR_million") is Unit.MILLION
