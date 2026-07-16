"""Calendar hygiene: dedup, run-collapse, agency times (review P1.1)."""

from datetime import datetime, timezone

from tradingagents.pro.ingestion.econ_calendar import (
    enrich_calendar,
    next_major_event,
)


def row(release: str, day: str, major: bool = True) -> dict:
    return {"date": day, "release": release, "release_id": 1, "major": major}


class TestEnrichCalendar:
    def test_consecutive_day_run_collapses_to_first(self):
        # the review's live finding: FOMC Press Release listed 7 days straight
        rows = [row("FOMC Press Release", f"2026-07-{d}") for d in range(16, 23)]
        out = enrich_calendar(rows)
        assert [r["date"] for r in out] == ["2026-07-16"]

    def test_weekly_cadence_survives(self):
        rows = [
            row("Unemployment Insurance Weekly Claims Report", "2026-07-16"),
            row("Unemployment Insurance Weekly Claims Report", "2026-07-23"),
        ]
        out = enrich_calendar(rows)
        assert [r["date"] for r in out] == ["2026-07-16", "2026-07-23"]

    def test_exact_duplicates_dedupe(self):
        rows = [row("GDPNow", "2026-07-16"), row("GDPNow", "2026-07-16")]
        assert len(enrich_calendar(rows)) == 1

    def test_agency_times_attach_with_dst_aware_utc(self):
        out = enrich_calendar([
            row("FOMC Press Release", "2026-07-16"),
            row("Consumer Price Index", "2026-07-16"),
            row("GDPNow", "2026-07-16"),  # no fixed agency time
        ])
        by_name = {r["release"]: r for r in out}
        fomc = by_name["FOMC Press Release"]
        assert fomc["time_et"] == "14:00"
        assert fomc["ts_utc"] == "2026-07-16T18:00:00+00:00"  # EDT = UTC-4
        cpi = by_name["Consumer Price Index"]
        assert cpi["time_et"] == "08:30"
        assert cpi["ts_utc"] == "2026-07-16T12:30:00+00:00"
        gdpnow = by_name["GDPNow"]
        assert gdpnow["time_et"] is None and gdpnow["ts_utc"] is None

    def test_winter_dates_use_est(self):
        (cpi,) = enrich_calendar([row("Consumer Price Index", "2026-01-13")])
        assert cpi["ts_utc"] == "2026-01-13T13:30:00+00:00"  # EST = UTC-5

    def test_majors_sort_first_within_a_date(self):
        out = enrich_calendar([
            row("Some Minor Series", "2026-07-16", major=False),
            row("Consumer Price Index", "2026-07-16"),
        ])
        assert out[0]["release"] == "Consumer Price Index"


class TestNextMajorEvent:
    NOW = datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc)

    def test_countdown_to_nearest_upcoming_major(self):
        releases = enrich_calendar([
            row("Consumer Price Index", "2026-07-16"),   # 12:30Z — upcoming
            row("FOMC Press Release", "2026-07-16"),     # 18:00Z — later
            row("Some Minor Series", "2026-07-16", major=False),
        ])
        nxt = next_major_event(releases, self.NOW)
        assert nxt is not None
        assert nxt["release"] == "Consumer Price Index"
        assert nxt["seconds_until"] == int(2.5 * 3600)

    def test_past_events_are_skipped(self):
        releases = enrich_calendar([row("Consumer Price Index", "2026-07-15")])
        assert next_major_event(releases, self.NOW) is None

    def test_unknown_time_counts_from_end_of_day(self):
        releases = enrich_calendar([row("GDPNow", "2026-07-16")])
        nxt = next_major_event(releases, self.NOW)
        assert nxt is not None and nxt["seconds_until"] > 0
