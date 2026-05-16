import unittest
import pytest
from flight_tracker.search import Flight
from flight_tracker.select import select_picks


def make_flight(price, stops, duration_min=600, airline="AA", departs="08:00"):
    return Flight(price=price, stops=stops, duration_min=duration_min, airline=airline, departs=departs)


@pytest.mark.unit
class TestSelectPicks(unittest.TestCase):
    def test_empty_list_returns_none_none(self):
        fewest, cheapest = select_picks([])
        self.assertIsNone(fewest)
        self.assertIsNone(cheapest)

    def test_single_flight_is_both_picks(self):
        f = make_flight(price=980, stops=1)
        fewest, cheapest = select_picks([f])
        self.assertEqual(fewest, f)
        self.assertEqual(cheapest, f)

    def test_fewest_stops_wins_over_price(self):
        nonstop = make_flight(price=1500, stops=0)
        one_stop_cheap = make_flight(price=800, stops=1)
        fewest, cheapest = select_picks([nonstop, one_stop_cheap])
        self.assertEqual(fewest, nonstop)
        self.assertEqual(cheapest, one_stop_cheap)

    def test_cheapest_is_lowest_price_regardless_of_stops(self):
        a = make_flight(price=1200, stops=0)
        b = make_flight(price=700, stops=3)
        _, cheapest = select_picks([a, b])
        self.assertEqual(cheapest, b)

    def test_fewest_stops_uses_price_as_tiebreaker(self):
        f1 = make_flight(price=900, stops=0)
        f2 = make_flight(price=800, stops=0)
        fewest, _ = select_picks([f1, f2])
        self.assertEqual(fewest, f2)  # same stops, lower price wins

    def test_fewest_stops_falls_back_when_no_nonstop(self):
        f1 = make_flight(price=900, stops=2)
        f2 = make_flight(price=1100, stops=1)
        fewest, _ = select_picks([f1, f2])
        self.assertEqual(fewest, f2)  # 1 stop < 2 stops

    def test_multiple_flights_same_cheapest(self):
        a = make_flight(price=500, stops=2)
        b = make_flight(price=500, stops=1)
        c = make_flight(price=900, stops=0)
        _, cheapest = select_picks([a, b, c])
        self.assertEqual(cheapest.price, 500)


if __name__ == "__main__":
    unittest.main()
