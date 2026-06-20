"""Tests for akshare utility modules — akshare_realtime, akshare_common (symbol
helpers, money/number formatting), and ticker resolution."""

from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.dataflows.akshare_common import (
    AShareSymbolError,
    format_money_cn,
    is_a_share_ticker,
    safe_float,
    to_akshare_symbol,
    to_yuan,
)


# ---------------------------------------------------------------------------
# akshare_realtime — fetch_realtime_snapshot
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRealtimeSnapshot:
    def test_returns_canonical_dict(self):
        from tradingagents.dataflows.akshare_realtime import fetch_realtime_snapshot

        spot_df = pd.DataFrame({
            "item": ["最新", "总市值", "市盈率(TTM)", "市净率"],
            "value": [1680.5, 2_108_000_000_000.0, 25.3, 8.7],
        })
        info_df = pd.DataFrame({
            "item": ["股票简称", "总市值"],
            "value": ["贵州茅台", 2_108_000_000_000.0],
        })
        with patch("tradingagents.dataflows.akshare_realtime.ak") as mock_ak:
            mock_ak.stock_individual_spot_xq.return_value = spot_df
            mock_ak.stock_individual_info_em.return_value = info_df
            snap = fetch_realtime_snapshot("600519.SS", xq_token="dummy")

        assert snap["ticker"] == "600519.SS"
        assert snap["company_name"] == "贵州茅台"
        assert snap["price"] == pytest.approx(1680.5)
        assert snap["pe_ttm"] == pytest.approx(25.3)
        assert snap["pb"] == pytest.approx(8.7)
        assert snap["market_cap_yi"] == pytest.approx(21080.0, rel=1e-3)

    def test_non_a_share_returns_none(self):
        from tradingagents.dataflows.akshare_realtime import fetch_realtime_snapshot

        assert fetch_realtime_snapshot("AAPL") is None

    def test_works_without_xueqiu_token(self):
        from tradingagents.dataflows.akshare_realtime import fetch_realtime_snapshot

        info_df = pd.DataFrame({
            "item": ["股票简称", "总市值"],
            "value": ["贵州茅台", 2_108_000_000_000.0],
        })
        with patch("tradingagents.dataflows.akshare_realtime.ak") as mock_ak:
            mock_ak.stock_individual_info_em.return_value = info_df
            snap = fetch_realtime_snapshot("600519.SS", xq_token=None)
        assert snap is not None
        assert snap["company_name"] == "贵州茅台"
        assert snap["market_cap_yi"] == pytest.approx(21080.0, rel=1e-3)
        assert snap["price"] is None


# ---------------------------------------------------------------------------
# akshare_common — to_akshare_symbol
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToAkshareSymbol:
    def test_shanghai_bare(self):
        assert to_akshare_symbol("600519.SS", "bare") == "600519"

    def test_shenzhen_bare(self):
        assert to_akshare_symbol("000001.SZ", "bare") == "000001"

    def test_beijing_bare(self):
        assert to_akshare_symbol("832000.BJ", "bare") == "832000"

    def test_shanghai_upper_prefix(self):
        assert to_akshare_symbol("600519.SS", "upper_prefix") == "SH600519"

    def test_shenzhen_upper_prefix(self):
        assert to_akshare_symbol("000001.SZ", "upper_prefix") == "SZ000001"

    def test_shanghai_lower_prefix(self):
        assert to_akshare_symbol("600519.SS", "lower_prefix") == "sh600519"

    def test_case_insensitive(self):
        assert to_akshare_symbol("600519.ss", "bare") == "600519"

    def test_non_a_share_raises(self):
        with pytest.raises(AShareSymbolError):
            to_akshare_symbol("AAPL", "bare")

    def test_unknown_style_raises(self):
        with pytest.raises(ValueError):
            to_akshare_symbol("600519.SS", "weird")


# ---------------------------------------------------------------------------
# akshare_common — is_a_share_ticker
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIsAShareTicker:
    @pytest.mark.parametrize("t", ["600519.SS", "000001.SZ", "832000.BJ", "600519.ss"])
    def test_yes(self, t):
        assert is_a_share_ticker(t) is True

    @pytest.mark.parametrize("t", ["AAPL", "9988.HK", "TSM", "", "600519"])
    def test_no(self, t):
        assert is_a_share_ticker(t) is False


# ---------------------------------------------------------------------------
# akshare_common — to_yuan
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToYuan:
    def test_passthrough_yuan(self):
        assert to_yuan(5_540_000_000, "yuan") == 5_540_000_000.0

    def test_from_wan(self):
        assert to_yuan(55_400, "wan") == 554_000_000.0

    def test_from_yi(self):
        assert to_yuan(5.54, "yi") == 554_000_000.0

    def test_none_returns_none(self):
        assert to_yuan(None, "yuan") is None

    def test_nan_returns_none(self):
        assert to_yuan(float("nan"), "yuan") is None

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError):
            to_yuan(100, "dollars")


# ---------------------------------------------------------------------------
# akshare_common — format_money_cn
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormatMoneyCN:
    def test_yi_scale(self):
        assert format_money_cn(5_540_000_000) == "55.40亿"

    def test_wan_scale(self):
        assert format_money_cn(1_234_567) == "123.46万"

    def test_below_wan(self):
        assert format_money_cn(5000) == "5000.00"

    def test_none(self):
        assert format_money_cn(None) == "N/A"

    def test_negative_yi(self):
        assert format_money_cn(-5_540_000_000) == "-55.40亿"


# ---------------------------------------------------------------------------
# akshare_common — safe_float
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSafeFloat:
    def test_str(self):
        assert safe_float("12.5") == 12.5

    def test_none(self):
        assert safe_float(None) is None

    def test_nan(self):
        assert safe_float(float("nan")) is None

    def test_bad_str(self):
        assert safe_float("--") is None
