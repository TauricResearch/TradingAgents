import unittest
import pytest
from flight_tracker.search import Flight
from flight_tracker.email_report import build_html, build_subject


def make_flight(price=980, stops=1, duration_min=980, airline="SAA", departs="18:30"):
    return Flight(price=price, stops=stops, duration_min=duration_min, airline=airline, departs=departs)


@pytest.mark.unit
class TestBuildSubject(unittest.TestCase):
    def test_subject_includes_prices_and_date(self):
        outbound = (make_flight(price=1240, stops=1), make_flight(price=980, stops=2))
        ret = (make_flight(price=900, stops=0), make_flight(price=850, stops=1))
        subject = build_subject(outbound, ret, "2026-05-16", "JFK", "JNB")
        self.assertIn("JFK", subject)
        self.assertIn("JNB", subject)
        self.assertIn("$1,240", subject)
        self.assertIn("$980", subject)
        self.assertIn("2026-05-16", subject)

    def test_subject_na_when_no_outbound_picks(self):
        subject = build_subject((None, None), (None, None), "2026-05-16", "JFK", "JNB")
        self.assertIn("N/A", subject)


@pytest.mark.unit
class TestBuildHtml(unittest.TestCase):
    def test_html_contains_flight_data(self):
        fewest = make_flight(price=1240, stops=1, duration_min=980, airline="SAA", departs="18:30")
        cheapest = make_flight(price=980, stops=2, duration_min=1365, airline="Ethiopian", departs="21:00")
        html = build_html((fewest, cheapest), (None, None), "2026-05-16")
        self.assertIn("SAA", html)
        self.assertIn("Ethiopian", html)
        self.assertIn("$1,240", html)
        self.assertIn("$980", html)
        self.assertIn("16h 20m", html)  # 980 min

    def test_html_shows_na_for_missing_leg(self):
        html = build_html((None, None), (None, None), "2026-05-16")
        self.assertIn("N/A", html)

    def test_html_contains_footer(self):
        html = build_html((None, None), (None, None), "2026-05-16")
        self.assertIn("SerpAPI", html)
        self.assertIn("history.csv", html)

    def test_duration_format_zero_minutes(self):
        f = make_flight(duration_min=0)
        html = build_html((f, f), (f, f), "2026-05-16")
        self.assertIn("0h 0m", html)

    def test_duration_format_exact_hour(self):
        f = make_flight(duration_min=120)
        html = build_html((f, f), (f, f), "2026-05-16")
        self.assertIn("2h 0m", html)

    def test_html_escapes_airline_name(self):
        f = make_flight(airline='<script>alert("xss")</script>')
        html = build_html((f, f), (f, f), "2026-05-16")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
