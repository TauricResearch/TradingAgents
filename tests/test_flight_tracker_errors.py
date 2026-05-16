import unittest
from unittest.mock import patch
import pytest
from flight_tracker.tracker import _safe_search


@pytest.mark.unit
class TestSafeSearch(unittest.TestCase):
    def test_returns_empty_and_error_on_failure(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("connection error")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertEqual(flights, [])
        self.assertIn("connection error", err)

    def test_quota_429_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("HTTP 429 Too Many Requests")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertEqual(flights, [])
        self.assertTrue(err.startswith("[QUOTA EXCEEDED]"))

    def test_quota_keyword_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("out of credits")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertTrue(err.startswith("[QUOTA EXCEEDED]"))

    def test_quota_serpapi_exceeded_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("Your plan has exceeded its limits.")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertTrue(err.startswith("[QUOTA EXCEEDED]"))

    def test_quota_serpapi_run_out_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("Your account has run out of searches.")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertTrue(err.startswith("[QUOTA EXCEEDED]"))

    def test_non_quota_error_not_prefixed(self):
        with patch("flight_tracker.tracker.search_flights", side_effect=Exception("network timeout")):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertFalse(err.startswith("[QUOTA EXCEEDED]"))
        self.assertIn("network timeout", err)

    def test_success_returns_flights_and_none_error(self):
        from flight_tracker.search import Flight
        mock_flight = Flight(price=980, stops=1, duration_min=900, airline="SAA", departs="18:30")
        with patch("flight_tracker.tracker.search_flights", return_value=[mock_flight]):
            flights, err = _safe_search("JFK", "JNB", "2026-08-20", "key")
        self.assertEqual(flights, [mock_flight])
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
