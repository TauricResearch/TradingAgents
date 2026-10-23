"""Small prices must remain visible in market data served to analysts (#1567)."""

from io import StringIO
from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.vendors.yahoo import market, snapshot


def _rows(scale):
    return pd.DataFrame({
        "Date": pd.to_datetime(["2026-10-20", "2026-10-21"]),
        "Open": [0.0029 * scale, 0.0038 * scale],
        "High": [0.0032 * scale, 0.0042 * scale],
        "Low": [0.0028 * scale, 0.0037 * scale],
        "Close": [0.003 * scale, 0.004 * scale],
        "Volume": [1_000_000, 1_200_000],
    })


@pytest.mark.unit
@pytest.mark.parametrize("scale", [1, 0.000001])
def test_csv_preserves_vendor_price_precision(monkeypatch, scale):
    rows = _rows(scale).set_index("Date")
    original = rows.copy(deep=True)
    monkeypatch.setattr(market.yf, "Ticker", lambda symbol: SimpleNamespace(
        history=lambda **kwargs: rows,
    ))

    text = market.get_YFin_data_online("PENNY", "2026-10-20", "2026-10-21")
    result = pd.read_csv(StringIO(text), comment="#")

    for column in ("Open", "High", "Low", "Close", "Volume"):
        assert result[column].tolist() == pytest.approx(original[column].tolist(), rel=1e-12, abs=0)
    pd.testing.assert_frame_equal(rows, original)


@pytest.mark.unit
@pytest.mark.parametrize("scale", [1, 0.000001])
def test_snapshot_preserves_small_prices_and_indicators(monkeypatch, scale):
    rows = _rows(scale)
    monkeypatch.setattr(snapshot, "load_ohlcv", lambda *args, **kwargs: rows)

    text = snapshot.build_verified_market_snapshot(
        "PENNY", "2026-10-21", look_back_days=2, indicators=["close_10_ema"],
    )
    values = {}
    for line in text.splitlines():
        if line.startswith("| "):
            key, value = line.strip("| ").split(" | ")
            values[key] = value

    for field in ("Open", "High", "Low", "Close"):
        assert float(values[field]) == pytest.approx(rows.iloc[-1][field], rel=1e-6, abs=0)
    assert float(values["2026-10-20"]) == pytest.approx(0.003 * scale, rel=1e-6, abs=0)
    assert float(values["2026-10-21"]) == pytest.approx(0.004 * scale, rel=1e-6, abs=0)
    assert 0.003 * scale < float(values["close_10_ema"]) < 0.004 * scale


@pytest.mark.unit
@pytest.mark.parametrize("value, expected", [
    (-0.000000123456, "-1.23456e-07"),
    (0.004, "0.004"),
    (0.0, "0.00"),
    (123.456, "123.46"),
    (None, "N/A"),
    (float("nan"), "N/A"),
])
def test_snapshot_number_format(value, expected):
    assert snapshot._fmt(value) == expected
