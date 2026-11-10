"""P2: SEC concept resolution (F1) and OHLCV finality (F5).

Both defects come from the BRK-B data lineage audit, and both are about the same
thing: a value entering the pipeline without the information that says what it
is. F1 lost the XBRL concept, so a component was presented as the consolidated
total. F5 lost the bar's finality, so a candle still forming was called a
verified close.

Every expected value below is independent of the code: the revenue figures are
read from the live SEC payload for CIK 0001067983, and the intraday fixtures are
the three actual report times converted to New York.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.dataflows.vendors.bar_finality import (
    BarFinality,
    assess_finality,
    describe_series,
)
from tradingagents.dataflows.vendors.concept_resolution import (
    CONCEPT_SCOPES,
    RevenueScope,
    TagProvenance,
    ordered_tags,
    preference_key,
    scope_of,
    select_by_scope,
)

CACHE = Path("/root/.tradingagents/cache/sec_edgar/CIK0001067983.json")
CONTRACT = "RevenueFromContractWithCustomerExcludingAssessedTax"
CONSOLIDATED = "Revenues"

# The three report times of 2026-11-09, in Europe/Rome.
REPORT_1837 = "2026-11-09T18:37:00+01:00"
REPORT_1924 = "2026-11-09T19:24:00+01:00"
REPORT_2101 = "2026-11-09T21:01:00+01:00"


def _payload() -> dict | None:
    """The cached SEC payload, or None when absent or unreadable.

    CI runs without access to /root and ``Path.exists()`` itself raises
    PermissionError there, so both the stat and the read are guarded.
    """
    try:
        if not CACHE.exists():
            return None
        return json.loads(CACHE.read_text())
    except (OSError, PermissionError, json.JSONDecodeError):
        return None


def _fact(filed: str, value: float, *, start: str, form: str = "10-Q",
          accn: str = "0001") -> dict:
    return {"end": filed, "val": value, "filed": filed, "start": start,
            "form": form, "accn": accn}


def _provenance(concept: str) -> TagProvenance:
    return TagProvenance(concept=concept, scope=scope_of(concept))


# ===========================================================================
# §4.1 — consolidated revenue is correct
# ===========================================================================
class TestConsolidatedRevenue:
    def test_the_consolidated_tag_wins_over_the_component(self):
        """§4.1: with both tags present, the whole entity's figure is chosen."""
        facts = {
            CONSOLIDATED: {"units": {"USD": [
                _fact("2026-09-30", 105_647_000_000, start="2026-07-01")]}},
            CONTRACT: {"units": {"USD": [
                _fact("2026-09-30", 74_322_000_000, start="2026-07-01")]}},
        }
        values, _, provenance = sec_edgar._as_of_with_provenance(
            facts, (CONTRACT, CONSOLIDATED), "2026-11-09", ((80, 100),))
        assert values[("2026-09-30", 0)] == 105_647_000_000
        assert provenance[("2026-09-30", 0)].concept == CONSOLIDATED
        assert provenance[("2026-09-30", 0)].scope is RevenueScope.CONSOLIDATED

    def test_the_tag_order_is_irrelevant_to_the_outcome(self):
        """Listing the component first no longer decides the value — that was F1."""
        facts = {
            CONSOLIDATED: {"units": {"USD": [
                _fact("2026-09-30", 105_647_000_000, start="2026-07-01")]}},
            CONTRACT: {"units": {"USD": [
                _fact("2026-09-30", 74_322_000_000, start="2026-07-01")]}},
        }
        for order in ((CONTRACT, CONSOLIDATED), (CONSOLIDATED, CONTRACT)):
            values, _, _ = sec_edgar._as_of_with_provenance(
                facts, order, "2026-11-09", ((80, 100),))
            assert values[("2026-09-30", 0)] == 105_647_000_000

    @pytest.mark.skipif(_payload() is None, reason="no SEC cache on this machine")
    def test_the_real_filing_yields_the_consolidated_total(self):
        """Against Berkshire's actual payload, not a fixture."""
        payload = _payload()
        assert payload is not None
        values, _, provenance = sec_edgar._as_of_with_provenance(
            payload["facts"]["us-gaap"], (CONTRACT, CONSOLIDATED),
            "2026-11-09", ((80, 100),))
        key = ("2026-09-30", 0)
        assert values[key] == 105_647_000_000
        assert provenance[key].scope is RevenueScope.CONSOLIDATED

    @pytest.mark.skipif(_payload() is None, reason="no SEC cache on this machine")
    def test_the_yoy_growth_is_11_24_percent(self):
        """§2's mandatory regression: 105,647 against 94,972."""
        payload = _payload()
        assert payload is not None
        values, _, _ = sec_edgar._as_of_with_provenance(
            payload["facts"]["us-gaap"], (CONSOLIDATED,),
            "2026-11-09", ((80, 100),))
        q3_2026 = values[("2026-09-30", 0)]
        q3_2025 = values[("2025-09-30", 0)]
        assert q3_2026 == 105_647_000_000
        assert q3_2025 == 94_972_000_000
        growth = (Decimal(q3_2026) / Decimal(q3_2025) - 1) * 100
        assert growth == pytest.approx(Decimal("11.24"), abs=Decimal("0.01"))


# ===========================================================================
# §4.2 — contract revenue is preserved, not renamed
# ===========================================================================
class TestContractRevenuePreserved:
    def test_the_component_keeps_its_own_identity(self):
        """§4.2: 74,322 is still identifiable, as contract revenue."""
        selection = select_by_scope(
            [(74_322_000_000.0, _provenance(CONTRACT))], RevenueScope.CONTRACT)
        assert selection.available is True
        assert selection.value == 74_322_000_000
        assert selection.provenance is not None
        assert selection.provenance.scope is RevenueScope.CONTRACT
        assert selection.provenance.is_consolidated is False

    def test_the_two_scopes_are_distinct_values(self):
        candidates = [
            (105_647_000_000.0, _provenance(CONSOLIDATED)),
            (74_322_000_000.0, _provenance(CONTRACT)),
        ]
        consolidated = select_by_scope(candidates, RevenueScope.CONSOLIDATED)
        contract = select_by_scope(candidates, RevenueScope.CONTRACT)
        assert consolidated.value == 105_647_000_000
        assert contract.value == 74_322_000_000
        assert consolidated.value != contract.value

    def test_scope_classification_covers_the_task_vocabulary(self):
        """§2 asks for five explicit categories."""
        assert scope_of("Revenues") is RevenueScope.CONSOLIDATED
        assert scope_of(CONTRACT) is RevenueScope.CONTRACT
        assert scope_of("SegmentReportingInformationRevenue") is RevenueScope.SEGMENT
        assert scope_of("RevenueNotFromContractWithCustomer") is RevenueScope.COMPONENT
        assert scope_of("SomethingUnseen") is RevenueScope.UNKNOWN


# ===========================================================================
# §4.3 — a missing tag
# ===========================================================================
class TestMissingTag:
    def test_a_consolidated_request_with_only_a_component_is_missing(self):
        """§4.3 and §2's rule: never substitute a subset for the total."""
        selection = select_by_scope(
            [(74_322_000_000.0, _provenance(CONTRACT))],
            RevenueScope.CONSOLIDATED)
        assert selection.available is False
        assert selection.value is None
        assert len(selection.rejected) == 1
        assert selection.rejected[0].scope is RevenueScope.CONTRACT

    def test_no_candidates_at_all_is_missing_not_zero(self):
        selection = select_by_scope([], RevenueScope.CONSOLIDATED)
        assert selection.available is False
        assert selection.value is None

    def test_a_dimensioned_fact_does_not_answer_a_headline_request(self):
        """`Revenues` for one segment is still a slice."""
        dimensioned = TagProvenance(
            concept=CONSOLIDATED, scope=RevenueScope.CONSOLIDATED,
            dimensions=(("us-gaap:StatementBusinessSegmentsAxis", "Railroad"),))
        selection = select_by_scope([(50_000_000_000.0, dimensioned)],
                                    RevenueScope.CONSOLIDATED)
        assert selection.available is False
        assert dimensioned.is_consolidated is True
        assert dimensioned.is_dimensioned is True


# ===========================================================================
# §4.4 — an older or stale filing
# ===========================================================================
class TestStaleFiling:
    def test_a_filing_after_the_analysis_date_is_not_known(self):
        """Point-in-time: a run dated earlier never sees a later filing."""
        facts = {CONSOLIDATED: {"units": {"USD": [
            _fact("2026-09-30", 105_647_000_000, start="2026-07-01")]}}}
        values, _, _ = sec_edgar._as_of_with_provenance(
            facts, (CONSOLIDATED,), "2026-06-01", ((80, 100),))
        assert values == {}

    def test_an_amendment_counts_from_the_day_it_was_filed(self):
        restated = _fact("2026-09-30", 100.0, start="2026-07-01", accn="orig")
        amended = _fact("2026-09-30", 105.0, start="2026-07-01", accn="amend")
        amended["filed"] = "2026-11-01"
        restated["filed"] = "2026-10-15"
        facts = {CONSOLIDATED: {"units": {"USD": [restated, amended]}}}
        before, _, _ = sec_edgar._as_of_with_provenance(
            facts, (CONSOLIDATED,), "2026-10-20", ((80, 100),))
        after, _, _ = sec_edgar._as_of_with_provenance(
            facts, (CONSOLIDATED,), "2026-11-05", ((80, 100),))
        assert before[("2026-09-30", 0)] == 100.0
        assert after[("2026-09-30", 0)] == 105.0


# ===========================================================================
# §4.5 — an incompatible fiscal period
# ===========================================================================
class TestIncompatiblePeriod:
    def test_a_year_to_date_figure_does_not_fill_a_quarter(self):
        """§4.5: a 272-day span is a different figure, not the quarter's."""
        facts = {CONSOLIDATED: {"units": {"USD": [
            _fact("2026-09-30", 301_130_000_000, start="2026-01-01")]}}}
        quarter_only, _, _ = sec_edgar._as_of_with_provenance(
            facts, (CONSOLIDATED,), "2026-11-09", ((80, 100),))
        assert quarter_only == {}
        wider, _, _ = sec_edgar._as_of_with_provenance(
            facts, (CONSOLIDATED,), "2026-11-09", ((260, 280),))
        assert wider[("2026-09-30", 0)] == 301_130_000_000

    def test_the_quarter_and_the_year_to_date_coexist(self):
        facts = {CONSOLIDATED: {"units": {"USD": [
            _fact("2026-09-30", 301_130_000_000, start="2026-01-01"),
            _fact("2026-09-30", 105_647_000_000, start="2026-07-01")]}}}
        values, _, _ = sec_edgar._as_of_with_provenance(
            facts, (CONSOLIDATED,), "2026-11-09",
            ((80, 100), (260, 280)))
        assert values[("2026-09-30", 0)] == 105_647_000_000   # quarter
        assert values[("2026-09-30", 1)] == 301_130_000_000   # year to date


# ===========================================================================
# §4.6-4.7 — intraday versus confirmed
# ===========================================================================
class TestBarFinality:
    def test_a_bar_during_the_session_is_partial(self):
        """§4.6: all three report times fall inside the NYSE session."""
        for stamp in (REPORT_1837, REPORT_1924, REPORT_2101):
            bar = assess_finality(stamp)
            assert bar.finality is BarFinality.INTRADAY_PARTIAL, stamp
            assert bar.usable_for_eod is False
            assert bar.usable_for_intraday is True

    def test_a_bar_after_the_settlement_grace_is_confirmed(self):
        """§4.7: 22:30 Rome is 16:30 New York, past the close and the grace."""
        bar = assess_finality("2026-11-09T22:30:00+01:00")
        assert bar.finality is BarFinality.EOD_CONFIRMED
        assert bar.usable_for_eod is True

    def test_the_grace_period_separates_pending_from_confirmed(self):
        just_closed = assess_finality("2026-11-09T16:02:00-05:00")
        settled = assess_finality("2026-11-09T16:30:00-05:00")
        assert just_closed.finality is BarFinality.EOD_PENDING_CONFIRMATION
        assert settled.finality is BarFinality.EOD_CONFIRMED

    def test_the_three_report_times_map_to_new_york_correctly(self):
        """12:37 / 13:24 / 15:01 ET, all before the 16:00 close."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        for stamp, expected in ((REPORT_1837, "12:37"), (REPORT_1924, "13:24"),
                                (REPORT_2101, "15:01")):
            local = datetime.fromisoformat(stamp).astimezone(
                ZoneInfo("America/New_York"))
            assert local.strftime("%H:%M") == expected
            assert assess_finality(stamp).finality is BarFinality.INTRADAY_PARTIAL

    def test_a_provisional_bar_carries_every_required_field(self):
        """§3: session date, timezone, timestamps, finality, source, calendar."""
        bar = assess_finality(REPORT_2101)
        payload = bar.summary()
        for field in ("session_date", "exchange_timezone",
                      "observation_timestamp", "source_timestamp", "finality",
                      "last_confirmed_close", "source", "session_calendar"):
            assert field in payload

    def test_a_bar_without_a_timestamp_is_unknown(self):
        bar = assess_finality(None)
        assert bar.finality is BarFinality.UNKNOWN
        assert bar.usable_for_eod is False


# ===========================================================================
# §4.8-4.9 — early closes and holidays
# ===========================================================================
class TestEarlyCloseAndHoliday:
    def test_a_bar_at_noon_on_an_early_close_day_is_partial(self):
        """§4.8: 2026-11-27 closes at 13:00, so 12:00 is still trading."""
        bar = assess_finality("2026-11-27T12:00:00-05:00")
        assert bar.finality is BarFinality.INTRADAY_PARTIAL

    def test_a_bar_after_an_early_close_is_confirmed(self):
        bar = assess_finality("2026-11-27T13:30:00-05:00")
        assert bar.finality is BarFinality.EOD_CONFIRMED

    def test_a_bar_on_a_holiday_cannot_be_a_close(self):
        """§4.9: no session, so no close — whatever the timestamp says."""
        bar = assess_finality("2026-11-26T12:00:00-05:00")
        assert bar.finality is BarFinality.UNKNOWN
        assert "not a trading day" in bar.reason


# ===========================================================================
# §4.10 — time zones and DST
# ===========================================================================
class TestTimeZonesAndDst:
    def test_the_same_rome_clock_time_shifts_with_dst(self):
        """After the US fall-back, 21:00 Rome is 15:00 ET; in summer it is 15:00 too
        only because both zones shift — the *offset* is what must be honoured."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        winter = datetime.fromisoformat("2026-11-09T21:00:00+01:00").astimezone(
            ZoneInfo("America/New_York"))
        summer = datetime.fromisoformat("2026-07-09T21:00:00+02:00").astimezone(
            ZoneInfo("America/New_York"))
        assert winter.strftime("%H:%M") == "15:00"
        assert summer.strftime("%H:%M") == "15:00"

    def test_a_winter_morning_is_before_the_open(self):
        bar = assess_finality("2026-11-09T13:00:00+01:00")  # 07:00 ET
        assert bar.finality is BarFinality.INTRADAY_PARTIAL
        assert bar.usable_for_eod is False


# ===========================================================================
# §4.11-4.12 — indicators over complete and provisional bars
# ===========================================================================
class TestIndicatorDeclaration:
    def test_a_series_of_confirmed_bars_declares_no_partial(self):
        """§4.11: a gap-free series of settled sessions."""
        finalities = [BarFinality.EOD_CONFIRMED] * 19
        described = describe_series(finalities)
        assert described["includes_partial_bar"] is False
        assert described["includes_unconfirmed_bar"] is False
        assert described["bars_confirmed"] == 19

    def test_a_series_ending_intraday_declares_it(self):
        """§4.12: an indicator over a forming bar must say so."""
        finalities = [BarFinality.EOD_CONFIRMED] * 19 + [
            BarFinality.INTRADAY_PARTIAL]
        described = describe_series(finalities)
        assert described["includes_partial_bar"] is True
        assert described["bars_confirmed"] == 19
        assert described["last_bar_finality"] == "INTRADAY_PARTIAL"


# ===========================================================================
# §4.13 — an event after the last close
# ===========================================================================
class TestEventAfterLastClose:
    def test_an_intraday_reaction_is_not_a_settled_one(self):
        """§4.13: the causal guard distinguishes the two."""
        from tradingagents.dataflows.causal_guard import (
            OBSERVABLE,
            OBSERVABLE_INTRADAY,
            evaluate_post_event_pricing,
        )

        sessions = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
                    "2026-11-09"]
        settled = evaluate_post_event_pricing(
            "2026-11-07", sessions, as_of_date="2026-11-09")
        intraday = evaluate_post_event_pricing(
            "2026-11-07", sessions, as_of_date="2026-11-09",
            session_still_open=True)
        assert settled.status == OBSERVABLE
        assert intraday.status == OBSERVABLE_INTRADAY
        assert intraday.reaction_claim_allowed is False


# ===========================================================================
# §4.14 — no partial bar is ever promoted to EOD
# ===========================================================================
class TestNoAutomaticPromotion:
    def test_no_intraday_time_yields_an_eod_state(self):
        """§4.14: sweeping every minute of a session, none is a confirmed close."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        start = datetime(2026, 11, 9, 9, 30, tzinfo=ZoneInfo("America/New_York"))
        for minutes in range(0, 390, 10):
            stamp = (start + timedelta(minutes=minutes)).isoformat()
            assert assess_finality(stamp).finality is not BarFinality.EOD_CONFIRMED

    def test_only_a_settled_session_produces_a_confirmed_close(self):
        bar = assess_finality("2026-11-09T16:10:00-05:00")
        assert bar.finality is BarFinality.EOD_CONFIRMED
        assert bar.last_confirmed_close == "2026-11-09"

    def test_concept_ordering_is_by_meaning_not_by_list_position(self):
        """The regression that caused F1, stated as a property."""
        ordered = ordered_tags((CONTRACT, CONSOLIDATED))
        assert ordered[0] == CONSOLIDATED
        assert preference_key(CONSOLIDATED) < preference_key(CONTRACT)
        # And every consolidated tag outranks every non-consolidated one.
        for concept, scope in CONCEPT_SCOPES.items():
            if scope is RevenueScope.CONSOLIDATED:
                assert preference_key(concept)[0] == 0
            else:
                assert preference_key(concept)[0] > 0
