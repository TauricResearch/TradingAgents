"""Execution agent contract tests using a fake Alpaca client (no network)."""

from __future__ import annotations

import logging

from tradingagents.execution.agent import (
    ExecutionAgent,
    is_live_alpaca_url,
    shares_from_available_cash,
)


class _FakeAlpacaClient:
    def __init__(
        self,
        *,
        cash: float = 2000.0,
        equity: float = 12000.0,
        position: dict | None = None,
        account_id: str = "acct-paper-12345678",
        account_number: str = "PA0001111",
    ) -> None:
        self.cash = cash
        self.equity = equity
        self.position = position
        self.account_id = account_id
        self.account_number = account_number
        self.submitted: list[dict] = []

    def get_account(self) -> dict:
        return {
            "id": self.account_id,
            "account_number": self.account_number,
            "cash": str(self.cash),
            "buying_power": str(self.cash),
            "equity": str(self.equity),
            "portfolio_value": str(self.equity),
            "long_market_value": str(self.equity - self.cash),
            "status": "ACTIVE",
        }

    def get_positions(self) -> list[dict]:
        if self.position is None:
            return []
        return [self.position]

    def submit_order(self, payload: dict) -> dict:
        self.submitted.append(payload)
        return {
            "id": "paper-order-1",
            "status": "accepted",
            "submitted_at": "2026-03-01T14:30:00Z",
            "filled_qty": "0",
            "filled_avg_price": None,
        }


PM_BUY_50_CASH = """
**Rating**: Buy

**Executive Summary**: Buy NVDA at 100 with a stop at 90. Use 50% of available cash.

**Investment Thesis**: Setup is clean.

**Price Target**: 130

**Time Horizon**: 3-6 months
"""

PM_HOLD = """
**Rating**: Hold

**Executive Summary**: Stay put.

**Time Horizon**: 3-6 months
"""

PM_SELL = """
**Rating**: Sell

**Executive Summary**: Exit NVDA.

**Time Horizon**: 3-6 months
"""


def _agent(tmp_path, client, **config):
    base = {
        "execution_enabled": True,
        "execution_journal_path": str(tmp_path / "journal.md"),
        "execution_position_plan_path": str(tmp_path / "plans.json"),
        "execution_fallback_cash_pct": 10.0,
        "alpaca_time_in_force": "gtc",
    }
    base.update(config)
    return ExecutionAgent(base, client=client)


class TestSharesFromCash:
    def test_fifty_percent_of_cash_not_equity(self):
        qty = shares_from_available_cash(cash=2000, cash_pct=50, price=100)
        assert qty == 10
        assert qty * 100 == 1000

    def test_never_exceeds_cash(self):
        qty = shares_from_available_cash(cash=2000, cash_pct=100, price=100)
        assert qty * 100 <= 2000


class TestExecutionAgent:
    def test_disabled_recommends_without_submitting(self, tmp_path):
        client = _FakeAlpacaClient()
        agent = _agent(tmp_path, client, execution_enabled=False)
        result = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_BUY_50_CASH,
            trade_date="2026-03-01",
        )
        assert result.enabled is False
        assert result.order_submitted is False
        assert result.order_action == "buy"
        assert result.cash_allocation_pct == 50
        assert client.submitted == []
        assert "recommendations only" in result.message
        assert "Recommendation: buy 50% of available cash" in result.message

    def test_enabled_without_alpaca_keys_reports_error(self, tmp_path):
        agent = ExecutionAgent(
            {
                "execution_journal_path": str(tmp_path / "journal.md"),
                "execution_position_plan_path": str(tmp_path / "plans.json"),
            }
        )
        result = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_BUY_50_CASH,
            trade_date="2026-03-01",
        )
        assert result.enabled is True
        assert result.order_submitted is False
        assert "Alpaca API key and secret are required" in result.message

    def test_enabled_buy_uses_cash_not_equity(self, tmp_path):
        client = _FakeAlpacaClient(cash=2000, equity=12000)
        agent = _agent(tmp_path, client)
        result = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_BUY_50_CASH,
            trade_date="2026-03-01",
        )
        assert result.order_submitted is True
        assert result.order_action == "buy"
        assert result.quantity == 10
        assert result.estimated_notional == 1000
        assert client.submitted
        notional = float(client.submitted[0]["qty"]) * float(client.submitted[0]["limit_price"])
        assert notional == 1000
        assert notional != 6000

    def test_order_never_exceeds_cash(self, tmp_path):
        client = _FakeAlpacaClient(cash=2000, equity=12000)
        pm = PM_BUY_50_CASH.replace("50% of available cash", "100% of available cash")
        agent = _agent(tmp_path, client)
        result = agent.run(ticker="NVDA", portfolio_manager_text=pm, trade_date="2026-03-01")
        assert result.order_submitted is True
        assert result.quantity * 100 <= 2000

    def test_hold_does_not_buy(self, tmp_path):
        client = _FakeAlpacaClient(
            position={
                "symbol": "NVDA",
                "qty": "5",
                "current_price": "120",
                "avg_entry_price": "100",
                "market_value": "600",
            }
        )
        agent = _agent(tmp_path, client)
        result = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_HOLD,
            trade_date="2026-03-01",
        )
        assert result.order_action == "hold"
        assert result.order_submitted is False
        assert client.submitted == []

    def test_stop_loss_while_in_horizon_sells(self, tmp_path):
        client = _FakeAlpacaClient()
        agent = _agent(tmp_path, client)
        opened = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_BUY_50_CASH,
            trade_date="2026-01-15",
        )
        assert opened.order_action == "buy"
        assert opened.order_submitted is True

        client.submitted.clear()
        client.position = {
            "symbol": "NVDA",
            "qty": str(opened.quantity),
            "current_price": "85",
            "avg_entry_price": "100",
            "market_value": str(opened.quantity * 85),
        }
        result = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_HOLD,
            trade_date="2026-03-01",
        )
        assert result.order_action == "sell"
        assert result.order_submitted is True
        assert result.quantity == opened.quantity
        assert client.submitted[0]["side"] == "sell"

    def test_horizon_elapsed_and_pm_sell(self, tmp_path):
        client = _FakeAlpacaClient()
        agent = _agent(tmp_path, client)
        opened = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_BUY_50_CASH,
            trade_date="2026-01-15",
        )
        assert opened.order_submitted is True

        client.submitted.clear()
        client.position = {
            "symbol": "NVDA",
            "qty": str(opened.quantity),
            "current_price": "125",
            "avg_entry_price": "100",
            "market_value": str(opened.quantity * 125),
        }
        result = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_SELL,
            trade_date="2026-08-01",
        )
        assert result.order_action == "sell"
        assert result.order_submitted is True
        assert client.submitted[0]["side"] == "sell"

    def test_missing_keys_when_enabled_does_not_crash(self, tmp_path):
        agent = ExecutionAgent(
            {
                "execution_enabled": True,
                "execution_journal_path": str(tmp_path / "journal.md"),
                "execution_position_plan_path": str(tmp_path / "plans.json"),
                "alpaca_api_key": "",
                "alpaca_secret_key": "",
            }
        )
        result = agent.run(
            ticker="NVDA",
            portfolio_manager_text=PM_BUY_50_CASH,
            trade_date="2026-03-01",
        )
        assert result.order_submitted is False
        assert "Alpaca API key" in result.message
        assert result.cash_allocation_pct == 50

    def test_live_url_warning(self, caplog):
        caplog.set_level(logging.WARNING)
        from tradingagents.execution.agent import AlpacaPaperClient

        AlpacaPaperClient(
            api_key="paper-key",
            secret_key="paper-secret",
            base_url="https://api.alpaca.markets",
        )
        assert any("live trading" in rec.message for rec in caplog.records)
        assert is_live_alpaca_url("https://api.alpaca.markets") is True
        assert is_live_alpaca_url("https://paper-api.alpaca.markets") is False
