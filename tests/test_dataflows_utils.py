import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows.utils import (
    _sanitize_ticker,
    decorate_all_methods,
    get_current_date,
    get_next_weekday,
    safe_ticker_component,
    save_output,
)


@pytest.mark.unit
class SanitizeTickerTests(unittest.TestCase):
    def test_extracts_a_share_ticker_from_polluted_text(self):
        result = _sanitize_ticker("极速查询到的证券代码为 601899.SS")
        self.assertEqual(result, "601899.SS")

    def test_extracts_generic_suffix_ticker(self):
        result = _sanitize_ticker("Ticker is AAPL.SS for Shanghai listing")
        self.assertEqual(result, "AAPL.SS")

    def test_returns_none_for_clean_input(self):
        result = _sanitize_ticker("AAPL")
        self.assertIsNone(result)

    def test_returns_none_for_unrelated_text(self):
        result = _sanitize_ticker("no ticker here")
        self.assertIsNone(result)


@pytest.mark.unit
class SafeTickerComponentTests(unittest.TestCase):
    def test_accepts_valid_ticker(self):
        self.assertEqual(safe_ticker_component("AAPL"), "AAPL")

    def test_accepts_dotted_ticker(self):
        self.assertEqual(safe_ticker_component("600519.SS"), "600519.SS")

    def test_accepts_index_symbol(self):
        self.assertEqual(safe_ticker_component("^GSPC"), "^GSPC")

    def test_accepts_futures_symbol(self):
        self.assertEqual(safe_ticker_component("GC=F"), "GC=F")

    def test_rejects_empty_string(self):
        with self.assertRaises(ValueError):
            safe_ticker_component("")

    def test_rejects_non_string(self):
        with self.assertRaises(ValueError):
            safe_ticker_component(123)

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            safe_ticker_component("../../../etc/passwd")

    def test_cleans_llm_hallucinated_text(self):
        result = safe_ticker_component("极速查询到的证券代码为 601899.SS")
        self.assertEqual(result, "601899.SS")

    def test_rejects_overly_long_value(self):
        with self.assertRaises(ValueError):
            safe_ticker_component("A" * 100)

    def test_rejects_dot_only_value(self):
        with self.assertRaises(ValueError):
            safe_ticker_component("...")


@pytest.mark.unit
class SaveOutputTests(unittest.TestCase):
    @patch("tradingagents.dataflows.utils.print")
    def test_saves_csv_when_path_provided(self, mock_print):
        df = pd.DataFrame({"a": [1, 2]})
        save_output(df, "test", save_path="/tmp/test.csv")
        mock_print.assert_called_once()

    def test_does_nothing_when_no_path(self):
        df = pd.DataFrame({"a": [1, 2]})
        save_output(df, "test")


@pytest.mark.unit
class GetCurrentDateTests(unittest.TestCase):
    def test_returns_formatted_date(self):
        result = get_current_date()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}$")


@pytest.mark.unit
class DecorateAllMethodsTests(unittest.TestCase):
    def test_decorates_callable_methods(self):
        def double(fn):
            def wrapper(*args, **kwargs):
                return fn(*args, **kwargs) * 2
            return wrapper

        @decorate_all_methods(double)
        class MyClass:
            def add(self, a, b):
                return a + b

        obj = MyClass()
        self.assertEqual(obj.add(3, 4), 14)

    def test_skips_non_callable_attributes(self):
        def identity(fn):
            return fn

        @decorate_all_methods(identity)
        class MyClass:
            x = 42
            def method(self):
                return 1

        self.assertEqual(MyClass.method(None), 1)
        self.assertEqual(MyClass.x, 42)


@pytest.mark.unit
class GetNextWeekdayTests(unittest.TestCase):
    def test_saturday_returns_monday(self):
        sat = datetime(2026, 6, 20)  # Saturday
        result = get_next_weekday(sat)
        self.assertEqual(result.weekday(), 0)  # Monday

    def test_sunday_returns_monday(self):
        sun = datetime(2026, 6, 21)
        result = get_next_weekday(sun)
        self.assertEqual(result.weekday(), 0)

    def test_weekday_returns_same(self):
        mon = datetime(2026, 6, 22)
        result = get_next_weekday(mon)
        self.assertEqual(result, mon)

    def test_accepts_date_string(self):
        result = get_next_weekday("2026-06-20")
        self.assertEqual(result.weekday(), 0)


if __name__ == "__main__":
    unittest.main()
