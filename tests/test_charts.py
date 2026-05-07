
import pandas as pd

from tradingagents.charts import (
    add_core_indicators,
    normalize_ohlcv,
    render_technical_chart,
)


def _sample_ohlcv(rows: int = 240) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=rows, freq="D")
    close = pd.Series([100 + (idx * 0.5) for idx in range(rows)])
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": [1_000_000 + (idx * 1000) for idx in range(rows)],
        }
    )


def test_normalize_ohlcv_sorts_dates_and_coerces_numeric_values():
    data = pd.DataFrame(
        {
            "Date": ["2025-01-03", "bad-date", "2025-01-01", "2025-01-02"],
            "Open": ["102", "101", "100", "101"],
            "High": ["103", "102", "101", "102"],
            "Low": ["101", "100", "99", "100"],
            "Close": ["102", "101", "100", None],
            "Volume": ["1200", "1100", "1000", "bad-volume"],
        }
    )

    result = normalize_ohlcv(data)

    assert list(result["Date"].dt.strftime("%Y-%m-%d")) == ["2025-01-01", "2025-01-03"]
    assert result["Close"].tolist() == [100, 102]
    assert pd.api.types.is_numeric_dtype(result["Volume"])


def test_add_core_indicators_adds_trend_momentum_volatility_columns():
    result = add_core_indicators(_sample_ohlcv())

    expected_columns = {
        "SMA_50",
        "SMA_200",
        "BB_MID",
        "BB_UPPER",
        "BB_LOWER",
        "MACD",
        "MACD_SIGNAL",
        "MACD_HIST",
        "RSI_14",
    }
    assert expected_columns.issubset(result.columns)
    assert result["SMA_50"].notna().any()
    assert result["SMA_200"].notna().any()
    assert result["MACD_HIST"].notna().any()
    assert result["RSI_14"].dropna().between(0, 100).all()


def test_render_technical_chart_writes_png_artifact(tmp_path):
    output_path = tmp_path / "technical-analysis.png"

    artifact = render_technical_chart("SPY", _sample_ohlcv(), output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert artifact.path == output_path
    assert artifact.title == "SPY Technical Analysis"
    assert "price" in artifact.description.lower()
    assert "volume" in artifact.description.lower()
    assert "macd" in artifact.description.lower()
    assert "bollinger" in artifact.description.lower()
    assert "rsi" in artifact.description.lower()
