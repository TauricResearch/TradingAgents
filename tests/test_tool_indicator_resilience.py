"""`get_indicators` 的逐项容错：一个指标失败不连坐同批其余指标，也不掀掉整个 turn。

路由对核心类别（technical_indicators）在全链路真实失败时原样上抛终局错误——那不是
ValueError，工具的 `except ValueError` 接不住，ToolNode 的默认 handler 会把它 re-raise
出去，整个 analyst turn 报废。和其他错误一样转成文本回传给模型（#1593 的同一哲学）。
"""

from __future__ import annotations

from unittest import mock

import pytest

from tradingagents.agents import tools

TRADE_DATE = "2026-08-14"


@pytest.mark.unit
def test_a_failed_indicator_does_not_sink_its_batch():
    with mock.patch.object(tools, "route_to_vendor", side_effect=_flaky_router):
        out = tools.get_indicators.func(
            symbol="AAPL", indicator="rsi, macd", curr_date=TRADE_DATE, look_back_days=5, trade_date=TRADE_DATE,
        )
    assert "rsi: network down" in out      # 失败项转成文本回传
    assert "macd-data" in out              # 同批其余项照常拿到数据


@pytest.mark.unit
def test_a_failed_indicator_returns_text_instead_of_raising():
    with mock.patch.object(tools, "route_to_vendor", side_effect=RuntimeError("network down")):
        out = tools.get_indicators.func(
            symbol="AAPL", indicator="rsi", curr_date=TRADE_DATE, look_back_days=5, trade_date=TRADE_DATE,
        )
    assert "network down" in out


@pytest.mark.unit
def test_unknown_indicator_still_reports_the_vocabulary():
    with mock.patch.object(tools, "route_to_vendor", side_effect=_flaky_router):
        out = tools.get_indicators.func(
            symbol="AAPL", indicator="rsii", curr_date=TRADE_DATE, look_back_days=5, trade_date=TRADE_DATE,
        )
    assert "not supported" in out          # 既有 ValueError 行为逐字保留


def _flaky_router(method, symbol, indicator, curr_date, look_back_days):
    if indicator == "rsi":
        raise RuntimeError("network down")   # 路由终局上抛的非 ValueError
    if indicator == "rsii":
        raise ValueError("Indicator rsii is not supported. Please choose from: [...]")
    return "macd-data"
