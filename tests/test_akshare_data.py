import pytest
from tradingagents.dataflows.akshare_data import (
    _normalize_akshare_ticker,
    _is_chinese_name,
)


class TestNormalizeAkshareTicker:
    @pytest.mark.unit
    def test_plain_shanghai_code(self):
        code, exchange = _normalize_akshare_ticker("600000")
        assert code == "600000"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_plain_shenzhen_code_starting_0(self):
        code, exchange = _normalize_akshare_ticker("000001")
        assert code == "000001"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_plain_shenzhen_code_starting_3(self):
        code, exchange = _normalize_akshare_ticker("300750")
        assert code == "300750"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_suffixed_shanghai(self):
        code, exchange = _normalize_akshare_ticker("600000.SS")
        assert code == "600000"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_suffixed_shenzhen(self):
        code, exchange = _normalize_akshare_ticker("000001.SZ")
        assert code == "000001"
        assert exchange == "shenzhen"

    @pytest.mark.unit
    def test_suffixed_hk(self):
        code, exchange = _normalize_akshare_ticker("0700.HK")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_plain_hk_code(self):
        code, exchange = _normalize_akshare_ticker("00700")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_hk_pads_to_5_digits(self):
        code, exchange = _normalize_akshare_ticker("700.HK")
        assert code == "00700"
        assert exchange == "hongkong"

    @pytest.mark.unit
    def test_star_market_shanghai(self):
        code, exchange = _normalize_akshare_ticker("688001")
        assert code == "688001"
        assert exchange == "shanghai"

    @pytest.mark.unit
    def test_beijing_exchange(self):
        code, exchange = _normalize_akshare_ticker("830799")
        assert code == "830799"
        assert exchange == "shenzhen"


class TestIsChineseName:
    @pytest.mark.unit
    def test_chinese_name_detected(self):
        assert _is_chinese_name("贵州茅台") is True

    @pytest.mark.unit
    def test_english_ticker_not_chinese(self):
        assert _is_chinese_name("600000.SS") is False

    @pytest.mark.unit
    def test_mixed_is_chinese(self):
        assert _is_chinese_name("平安银行") is True
