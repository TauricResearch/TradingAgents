import pandas as pd


def test_polygon_stock_data_formats_aggregates(monkeypatch):
    import tradingagents.dataflows.polygon as polygon

    captured = {}

    def fake_get(path, **params):
        captured["path"] = path
        captured["params"] = params
        return {
            "results": [
                {
                    "t": 1780516800000,
                    "o": 100.0,
                    "h": 103.0,
                    "l": 99.0,
                    "c": 102.0,
                    "v": 10000,
                }
            ]
        }

    monkeypatch.setattr(polygon, "_get", fake_get)

    text = polygon.get_stock_data("AAPL", "2026-06-01", "2026-06-03")

    assert captured["path"] == "/v2/aggs/ticker/AAPL/range/1/day/2026-06-01/2026-06-03"
    assert captured["params"]["adjusted"] == "true"
    assert "# Stock data for AAPL from 2026-06-01 to 2026-06-03" in text
    assert "102.0" in text


def test_polygon_market_snapshot_uses_polygon_source(monkeypatch):
    import tradingagents.dataflows.polygon as polygon

    monkeypatch.setattr(
        polygon,
        "_get",
        lambda path, **params: {
            "results": [
                {
                    "t": 1780516800000,
                    "o": 100.0,
                    "h": 103.0,
                    "l": 99.0,
                    "c": 102.0,
                    "v": 10000,
                }
            ]
        },
    )

    text = polygon.get_market_snapshot("AAPL", "2026-06-03", lookback_days=2)

    assert "Source: polygon" in text
    assert "102.0000" in text


def test_polygon_fetch_ohlcv_frame_exposes_normalized_data(monkeypatch):
    import tradingagents.dataflows.polygon as polygon

    monkeypatch.setattr(
        polygon,
        "_aggs_frame",
        lambda symbol, start_date, end_date: pd.DataFrame(
            {
                "timestamp": ["2026-06-03"],
                "open": [100],
                "high": [103],
                "low": [99],
                "close": [102],
                "volume": [12345],
            }
        ),
    )

    out = polygon.fetch_ohlcv_frame("AAPL", "2026-06-03", "2026-06-03")

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == 102
