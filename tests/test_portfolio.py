# tests/test_portfolio.py
import json
import os
import pytest


@pytest.fixture
def p():
    from portfolio import Portfolio
    port = Portfolio()
    port.cash = 100_000.0
    port.positions = {}
    port.trades = []
    return port


class TestLoad:
    def test_fresh_portfolio_when_file_absent(self, tmp_path):
        from portfolio import Portfolio
        port = Portfolio()
        port.load(str(tmp_path / "missing.json"))
        assert port.cash == 100_000.0
        assert port.positions == {}
        assert port.trades == []

    def test_loads_existing_file(self, tmp_path):
        from portfolio import Portfolio
        path = tmp_path / "p.json"
        path.write_text(json.dumps({
            "cash": 50000.0,
            "positions": {"NVDA": {"shares": 10.0, "avg_cost": 130.0}},
            "trades": []
        }), encoding="utf-8")
        port = Portfolio()
        port.load(str(path))
        assert port.cash == 50_000.0
        assert port.positions["NVDA"]["shares"] == 10.0


class TestSave:
    def test_round_trip(self, tmp_path, p):
        from portfolio import Portfolio
        path = str(tmp_path / "p.json")
        p.cash = 42_000.0
        p.positions = {"AAPL": {"shares": 5.0, "avg_cost": 180.0}}
        p.save(path)
        p2 = Portfolio()
        p2.load(path)
        assert p2.cash == 42_000.0
        assert p2.positions["AAPL"]["shares"] == 5.0
        assert not os.path.exists(path + ".tmp")


class TestBuy:
    def test_creates_new_position(self, p):
        result = p.buy("NVDA", 1000.0, 100.0)
        assert result["shares"] == pytest.approx(10.0)
        assert result["avg_cost"] == pytest.approx(100.0)
        assert p.cash == pytest.approx(99_000.0)

    def test_weighted_average_cost(self, p):
        p.buy("NVDA", 1000.0, 100.0)   # 10 shares @ 100
        result = p.buy("NVDA", 1000.0, 200.0)   # 5 shares @ 200 → avg 133.33
        assert result["shares"] == pytest.approx(15.0)
        assert result["avg_cost"] == pytest.approx(133.3333, abs=0.001)
        assert p.cash == pytest.approx(98_000.0)

    def test_trade_appended(self, p):
        p.buy("AAPL", 500.0, 50.0)
        assert len(p.trades) == 1
        assert p.trades[0]["side"] == "BUY"
        assert p.trades[0]["ticker"] == "AAPL"
        assert p.trades[0]["shares"] == pytest.approx(10.0)

    def test_fractional_shares(self, p):
        result = p.buy("TSLA", 1000.0, 300.0)
        assert result["shares"] == pytest.approx(3.3333, abs=0.001)


class TestSell:
    def test_full_position_sell(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares
        result = p.sell("NVDA", 1000.0, 100.0)
        assert result["shares_sold"] == pytest.approx(10.0)
        assert "NVDA" not in p.positions
        assert p.cash == pytest.approx(100_000.0)

    def test_partial_sell(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares
        result = p.sell("NVDA", 500.0, 100.0)  # sell 5
        assert result["shares_sold"] == pytest.approx(5.0)
        assert p.positions["NVDA"]["shares"] == pytest.approx(5.0)

    def test_sell_capped_at_full_position(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares = $1000
        result = p.sell("NVDA", 5000.0, 100.0)  # try to sell $5000 worth
        assert result["shares_sold"] == pytest.approx(10.0)   # capped at full position
        assert "NVDA" not in p.positions

    def test_trade_appended(self, p):
        p.buy("NVDA", 1000.0, 100.0)
        p.sell("NVDA", 500.0, 110.0)
        assert len(p.trades) == 2
        assert p.trades[1]["side"] == "SELL"

    def test_sell_nonexistent_raises(self, p):
        with pytest.raises(KeyError):
            p.sell("MISSING", 100.0, 50.0)


class TestGetState:
    def test_empty_portfolio(self, p):
        state = p.get_state({})
        assert state["cash"] == pytest.approx(100_000.0)
        assert state["positions"] == {}
        assert state["total_value"] == pytest.approx(100_000.0)

    def test_unrealised_pnl_positive(self, p):
        p.buy("NVDA", 1000.0, 100.0)  # 10 shares @ 100
        state = p.get_state({"NVDA": 120.0})  # now worth $1200
        pos = state["positions"]["NVDA"]
        assert pos["unrealised_pnl"] == pytest.approx(200.0)
        assert pos["unrealised_pnl_pct"] == pytest.approx(20.0)
        assert state["total_value"] == pytest.approx(100_200.0)

    def test_unrealised_pnl_negative(self, p):
        p.buy("NVDA", 1000.0, 100.0)
        state = p.get_state({"NVDA": 80.0})
        assert state["positions"]["NVDA"]["unrealised_pnl"] == pytest.approx(-200.0)

    def test_fallback_to_avg_cost_when_price_missing(self, p):
        p.buy("NVDA", 1000.0, 100.0)
        state = p.get_state({})  # no price provided
        assert state["positions"]["NVDA"]["unrealised_pnl"] == pytest.approx(0.0)
        assert state["total_value"] == pytest.approx(100_000.0)
