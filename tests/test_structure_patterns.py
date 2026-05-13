import pandas as pd

from tradingagents.agents.managers.portfolio_state_manager import _format_short_term_market_anchors
from tradingagents.agents.utils.structure_patterns import (
    analyze_ohlcv_structure,
    format_structure_analysis_for_prompt,
)


def _hammer_after_decline_frame() -> pd.DataFrame:
    rows = []
    close = 100.0
    for i in range(24):
        open_price = close
        close = close - 1.0
        rows.append({
            "Date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
            "Open": open_price,
            "High": open_price + 0.4,
            "Low": close - 0.4,
            "Close": close,
            "Volume": 1_000_000,
        })

    prior_support = min(row["Low"] for row in rows[-10:])
    rows.append({
        "Date": pd.Timestamp("2024-01-25"),
        "Open": close - 0.1,
        "High": close + 0.9,
        "Low": prior_support - 1.0,
        "Close": close + 0.7,
        "Volume": 1_800_000,
    })
    return pd.DataFrame(rows)


def test_structure_analyzer_detects_hammer_and_liquidity_sweep():
    analysis = analyze_ohlcv_structure(
        _hammer_after_decline_frame(),
        ticker="TEST",
        as_of_date="2024-01-25",
    )

    pattern_names = {pattern["name"] for pattern in analysis["detected_patterns"]}

    assert analysis["schema_version"] == "structure_v1"
    assert "Hammer" in pattern_names
    assert "Liquidity Sweep" in pattern_names
    assert analysis["short_term_structure"]["support"] is not None
    assert analysis["short_term_structure"]["volume_confirmation"] in {
        "normal",
        "expanding",
        "unavailable",
    }


def test_structure_prompt_format_is_embedded_in_market_anchor_text():
    analysis = analyze_ohlcv_structure(
        _hammer_after_decline_frame(),
        ticker="TEST",
        as_of_date="2024-01-25",
    )
    anchors = {
        "as_of_close_date": "2024-01-25",
        "current_price": 77.7,
        "atr5": 2.0,
        "atr14": 1.5,
        "atr14_pct": 1.93,
        "ema5": 78.0,
        "ema10": 80.0,
        "ema20": 85.0,
        "sma5": 78.0,
        "sma10": 80.0,
        "sma20": 85.0,
        "sma50": None,
        "recent_high_5d": 82.0,
        "recent_low_5d": 74.0,
        "recent_high_10d": 88.0,
        "recent_low_10d": 74.0,
        "nearest_resistance": 82.0,
        "nearest_support": 74.0,
        "latest_volume": 1_800_000,
        "volume_20_sma": 1_040_000,
        "volume_ratio": 1.73,
        "volume_ratio_3d": [1.0, 1.0, 1.73],
        "structure_analysis": analysis,
    }

    prompt_block = _format_short_term_market_anchors(anchors)
    standalone_block = format_structure_analysis_for_prompt(analysis)

    assert "Deterministic structure analysis" in prompt_block
    assert "Python-only hard anchor" in prompt_block
    assert "Hammer" in prompt_block
    assert standalone_block in prompt_block
