import unittest
import pytest
from flight_tracker.search import Flight, _normalize_response


@pytest.mark.unit
class TestNormalizeResponse(unittest.TestCase):
    def _make_item(self, price=980, layovers=None, duration=900, airline="Delta", departs="18:30"):
        return {
            "price": price,
            "layovers": layovers or [],
            "total_duration": duration,
            "flights": [
                {"airline": airline, "departure_airport": {"time": departs}}
            ],
        }

    def test_extracts_flight_fields(self):
        item = self._make_item(price=980, layovers=[{}], duration=900, airline="Delta", departs="18:30")
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(len(flights), 1)
        f = flights[0]
        self.assertEqual(f.price, 980)
        self.assertEqual(f.stops, 1)
        self.assertEqual(f.duration_min, 900)
        self.assertEqual(f.airline, "Delta")
        self.assertEqual(f.departs, "18:30")

    def test_combines_best_and_other_flights(self):
        item1 = self._make_item(price=800)
        item2 = self._make_item(price=1200)
        flights = _normalize_response({"best_flights": [item1], "other_flights": [item2]})
        self.assertEqual(len(flights), 2)

    def test_missing_best_flights_key(self):
        item = self._make_item(price=700)
        flights = _normalize_response({"other_flights": [item]})
        self.assertEqual(len(flights), 1)

    def test_missing_other_flights_key(self):
        item = self._make_item(price=700)
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(len(flights), 1)

    def test_empty_response_returns_empty_list(self):
        self.assertEqual(_normalize_response({}), [])

    def test_skips_items_with_no_price(self):
        item = self._make_item(price=None)
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights, [])

    def test_nonstop_has_zero_stops_empty_list(self):
        item = self._make_item(layovers=[])
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights[0].stops, 0)

    def test_nonstop_has_zero_stops_absent_key(self):
        item = self._make_item(layovers=[])
        del item["layovers"]  # key absent entirely — SerpAPI may omit it for nonstops
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights[0].stops, 0)

    def test_two_stops(self):
        item = self._make_item(layovers=[{}, {}])
        flights = _normalize_response({"best_flights": [item]})
        self.assertEqual(flights[0].stops, 2)

    def test_skips_malformed_item_missing_flights_key(self):
        good = self._make_item(price=800)
        bad = {"price": 500, "layovers": [], "total_duration": 600}  # no "flights" key
        flights = _normalize_response({"best_flights": [bad, good]})
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].price, 800)

    def test_skips_malformed_item_empty_flights_list(self):
        good = self._make_item(price=800)
        bad = {"price": 500, "layovers": [], "total_duration": 600, "flights": []}
        flights = _normalize_response({"best_flights": [bad, good]})
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].price, 800)


if __name__ == "__main__":
    unittest.main()
