from types import SimpleNamespace

import pandas as pd


class FakeContext:
    def __init__(self):
        self.calls = []
        self.closed = False

    def request_history_kline(self, code, start, end, ktype):
        self.calls.append((code, start, end, ktype))
        return 0, pd.DataFrame(
            {
                "time_key": ["2026-06-03 16:00:00"],
                "open": [100.0],
                "high": [102.0],
                "low": [99.0],
                "close": [101.5],
                "volume": [1500],
            }
        )

    def close(self):
        self.closed = True


def test_futu_symbol_translation():
    from tradingagents.dataflows.futu import translate_symbol

    assert translate_symbol("AAPL") == "US.AAPL"
    assert translate_symbol("0700.HK") == "HK.00700"
    assert translate_symbol("600519.SS") == "SH.600519"
    assert translate_symbol("000001.SZ") == "SZ.000001"


def test_futu_stock_data_formats_ohlcv(monkeypatch):
    import tradingagents.dataflows.futu as futu_mod

    fake_ctx = FakeContext()
    monkeypatch.setattr(futu_mod, "_ctx", lambda: fake_ctx)
    monkeypatch.setattr(futu_mod, "_futu_constants", lambda: SimpleNamespace(K_DAY="K_DAY"))

    text = futu_mod.get_stock_data("AAPL", "2026-06-01", "2026-06-03")

    assert fake_ctx.calls == [("US.AAPL", "2026-06-01", "2026-06-03", "K_DAY")]
    assert fake_ctx.closed is True
    assert "# Stock data for AAPL from 2026-06-01 to 2026-06-03" in text
    assert "101.5" in text


def test_futu_market_snapshot_uses_futu_source(monkeypatch):
    import tradingagents.dataflows.futu as futu_mod

    monkeypatch.setattr(futu_mod, "_ctx", lambda: FakeContext())
    monkeypatch.setattr(futu_mod, "_futu_constants", lambda: SimpleNamespace(K_DAY="K_DAY"))

    text = futu_mod.get_market_snapshot("AAPL", "2026-06-03", lookback_days=2)

    assert "Source: futu" in text
    assert "101.5000" in text
