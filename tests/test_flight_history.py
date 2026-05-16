import csv
import unittest
import pytest
from flight_tracker.search import Flight
from flight_tracker.tracker import _build_row, _update_history


def make_flight(price=980, stops=1, duration_min=980, airline="SAA", departs="18:30"):
    return Flight(price=price, stops=stops, duration_min=duration_min, airline=airline, departs=departs)


@pytest.mark.unit
class TestBuildRow(unittest.TestCase):
    def test_row_has_schema_version_1(self):
        row = _build_row("2026-05-16", (None, None), (None, None))
        self.assertEqual(row["schema_version"], "1")

    def test_row_has_correct_date(self):
        row = _build_row("2026-05-16", (None, None), (None, None))
        self.assertEqual(row["date"], "2026-05-16")

    def test_row_empty_when_no_picks(self):
        row = _build_row("2026-05-16", (None, None), (None, None))
        self.assertEqual(row["outbound_fewest_stops_price"], "")
        self.assertEqual(row["return_cheapest_airline"], "")

    def test_row_populated_with_picks(self):
        f = make_flight(price=980, stops=1, duration_min=900, airline="SAA")
        row = _build_row("2026-05-16", (f, f), (f, f))
        self.assertEqual(row["outbound_fewest_stops_price"], "980")
        self.assertEqual(row["outbound_fewest_stops_airline"], "SAA")
        self.assertEqual(row["outbound_fewest_stops_stops"], "1")
        self.assertEqual(row["outbound_fewest_stops_duration"], "900")


@pytest.mark.unit
class TestUpdateHistory(unittest.TestCase):
    HEADER = [
        "schema_version", "date",
        "outbound_fewest_stops_price", "outbound_fewest_stops_airline",
        "outbound_fewest_stops_stops", "outbound_fewest_stops_duration",
        "outbound_cheapest_price", "outbound_cheapest_airline",
        "outbound_cheapest_stops", "outbound_cheapest_duration",
        "return_fewest_stops_price", "return_fewest_stops_airline",
        "return_fewest_stops_stops", "return_fewest_stops_duration",
        "return_cheapest_price", "return_cheapest_airline",
        "return_cheapest_stops", "return_cheapest_duration",
    ]

    def _read_csv(self, path):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))

    def test_appends_new_date(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            csv_path = f.name
            writer = csv.DictWriter(f, fieldnames=self.HEADER)
            writer.writeheader()
        try:
            _update_history("2026-05-16", (None, None), (None, None), csv_path)
            rows = self._read_csv(csv_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2026-05-16")
        finally:
            os.unlink(csv_path)

    def test_overwrites_existing_date(self):
        import tempfile, os
        f_pick = make_flight(price=999)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            csv_path = f.name
            writer = csv.DictWriter(f, fieldnames=self.HEADER)
            writer.writeheader()
            writer.writerow({"schema_version": "1", "date": "2026-05-16",
                             **{k: "" for k in self.HEADER if k not in ("schema_version", "date")}})
        try:
            _update_history("2026-05-16", (f_pick, f_pick), (f_pick, f_pick), csv_path)
            rows = self._read_csv(csv_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["outbound_fewest_stops_price"], "999")
        finally:
            os.unlink(csv_path)

    def test_preserves_other_dates(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            csv_path = f.name
            writer = csv.DictWriter(f, fieldnames=self.HEADER)
            writer.writeheader()
            writer.writerow({"schema_version": "1", "date": "2026-05-15",
                             **{k: "" for k in self.HEADER if k not in ("schema_version", "date")}})
        try:
            _update_history("2026-05-16", (None, None), (None, None), csv_path)
            rows = self._read_csv(csv_path)
            self.assertEqual(len(rows), 2)
            dates = {r["date"] for r in rows}
            self.assertEqual(dates, {"2026-05-15", "2026-05-16"})
        finally:
            os.unlink(csv_path)


if __name__ == "__main__":
    unittest.main()
