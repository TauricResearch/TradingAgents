import pytest
from datetime import date


@pytest.mark.unit
@pytest.mark.parametrize("module_name,class_name,source_name", [
    ("tradingagents.backtest.sources.polygon_source", "PolygonSource", "polygon"),
    ("tradingagents.backtest.sources.alpha_vantage_source", "AlphaVantageSource", "alpha_vantage"),
    ("tradingagents.backtest.sources.futu_source", "FutuSource", "futu"),
])
def test_stub_source_metadata(module_name, class_name, source_name):
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    inst = cls()
    assert inst.name == source_name
    # Stubs declare DAILY support so the fallback chain considers them;
    # they raise NotImplementedError when called.
    from tradingagents.backtest.prices import Resolution
    assert Resolution.DAILY in inst.supports


@pytest.mark.unit
@pytest.mark.parametrize("module_name,class_name", [
    ("tradingagents.backtest.sources.polygon_source", "PolygonSource"),
    ("tradingagents.backtest.sources.alpha_vantage_source", "AlphaVantageSource"),
    ("tradingagents.backtest.sources.futu_source", "FutuSource"),
])
def test_stub_source_raises_on_get_bars(module_name, class_name):
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    inst = cls()
    from tradingagents.backtest.prices import Resolution
    with pytest.raises(NotImplementedError):
        inst.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                       Resolution.DAILY)
