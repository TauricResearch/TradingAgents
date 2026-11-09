import pandas as pd
import pytest

pytest.importorskip("plotly")

from tests.test_surge_engine import pattern_bars
from tradingagents.surge.chart import zone_chart
from tradingagents.surge.engine import detect_zones


def test_chart_draws_only_known_zones_and_starts_at_confirmation():
    bars = pattern_bars()
    zones = detect_zones(bars, "SPY.US")
    figure = zone_chart(bars, zones)
    rectangle = figure.layout.shapes[0]
    assert pd.Timestamp(rectangle.x0) == pd.Timestamp(zones[0].confirmed_at)
    assert rectangle.y0 == zones[0].distal
    assert len(figure.data) == 3  # candles, confirmation, leg in
    earlier = zone_chart(bars.iloc[:-1], zones)
    assert not earlier.layout.shapes
