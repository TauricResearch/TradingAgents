"""Volume profile math: known distributions, POC, value area (P2.4)."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tradingagents.contracts import OHLCVBar, Timeframe
from tradingagents.pro.ingestion.profile import volume_profile


def bar(low: float, high: float, volume: float, i: int = 0) -> OHLCVBar:
    return OHLCVBar(
        timeframe=Timeframe.H1, start=BASE_TS + timedelta(hours=i),
        open=low, high=high, low=low, close=high, volume=volume,
    )


class TestVolumeProfile:
    def test_single_bar_spreads_uniformly_over_its_range(self):
        result = volume_profile([bar(100, 110, 1000)], bins=10)
        assert len(result["levels"]) == 10
        for level in result["levels"]:
            assert level["volume"] == pytest.approx(100.0)
        assert result["total_volume"] == 1000

    def test_poc_lands_on_the_heaviest_price(self):
        bars = [
            bar(100, 110, 100, 0),      # background
            bar(104, 106, 5000, 1),     # heavy trade around 105
        ]
        result = volume_profile(bars, bins=10)
        assert result["poc"] == pytest.approx(105.0, abs=1.0)

    def test_value_area_covers_seventy_percent_around_poc(self):
        bars = [bar(100, 110, 100, 0), bar(104, 106, 5000, 1)]
        result = volume_profile(bars, bins=10)
        assert result["value_area_low"] <= result["poc"] <= result["value_area_high"]
        covered = sum(
            level["volume"] for level in result["levels"]
            if result["value_area_low"] <= level["price"] <= result["value_area_high"]
        )
        assert covered >= 0.70 * result["total_volume"]

    def test_degenerate_inputs_return_empty_not_garbage(self):
        assert volume_profile([], bins=10)["levels"] == []
        flat = volume_profile([bar(100, 100, 1000)], bins=10)
        assert flat["levels"] == [] and flat["poc"] is None
        no_volume = volume_profile([bar(100, 110, 0)], bins=10)
        assert no_volume["levels"] == []

    def test_bins_bounds_enforced(self):
        with pytest.raises(ValueError, match="bins"):
            volume_profile([bar(100, 110, 1000)], bins=1)
        with pytest.raises(ValueError, match="bins"):
            volume_profile([bar(100, 110, 1000)], bins=500)
