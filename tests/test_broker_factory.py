"""Tests for tradingagents.execution factory and KISBroker."""

import os
from unittest.mock import patch, MagicMock

import pytest

from tradingagents.execution import create_broker
from tradingagents.execution.kis.broker import KISBroker
from tradingagents.execution.models import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    AccountBalance,
    PortfolioSnapshot,
)


class TestCreateBroker:
    def test_kis_provider(self):
        config = {
            "broker": {
                "provider": "kis",
                "mode": "paper",
                "kis_app_key": "test_key",
                "kis_app_secret": "test_secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = create_broker(config)
        assert isinstance(broker, KISBroker)

    def test_default_provider_is_kis(self):
        config = {
            "broker": {
                "kis_app_key": "test_key",
                "kis_app_secret": "test_secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = create_broker(config)
        assert isinstance(broker, KISBroker)

    def test_unsupported_provider(self):
        config = {"broker": {"provider": "unknown"}}
        with pytest.raises(ValueError, match="Unsupported broker"):
            create_broker(config)


class TestKISBrokerInit:
    def test_missing_credentials_raises(self):
        config = {"broker": {"mode": "paper"}}
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="KIS_APP_KEY"):
                KISBroker(config)

    def test_env_fallback(self):
        config = {"broker": {"mode": "paper"}}
        env = {
            "KIS_APP_KEY": "env_key",
            "KIS_APP_SECRET": "env_secret",
            "KIS_ACCOUNT_NO": "99999999-01",
        }
        with patch.dict(os.environ, env, clear=False):
            broker = KISBroker(config)
            assert broker.broker_name == "KIS (한국투자증권)"
            assert broker.is_paper_trading is True

    def test_config_overrides_env(self):
        config = {
            "broker": {
                "mode": "real",
                "kis_app_key": "config_key",
                "kis_app_secret": "config_secret",
                "kis_account_no": "11111111-02",
            }
        }
        broker = KISBroker(config)
        assert broker.is_paper_trading is False


class TestKISBrokerProperties:
    def _make_broker(self, mode="paper"):
        config = {
            "broker": {
                "mode": mode,
                "kis_app_key": "test_key",
                "kis_app_secret": "test_secret",
                "kis_account_no": "12345678-01",
            }
        }
        return KISBroker(config)

    def test_broker_name(self):
        broker = self._make_broker()
        assert "KIS" in broker.broker_name
        assert "한국투자증권" in broker.broker_name

    def test_paper_mode(self):
        broker = self._make_broker(mode="paper")
        assert broker.is_paper_trading is True

    def test_real_mode(self):
        broker = self._make_broker(mode="real")
        assert broker.is_paper_trading is False

    def test_not_connected_initially(self):
        broker = self._make_broker()
        assert broker.is_connected() is False


class TestKISBrokerPlaceOrder:
    def test_place_order_success(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.place_order.return_value = {
            "output": {"ODNO": "ORD12345"},
            "rt_cd": "0",
        }

        order = OrderRequest(
            ticker="005930", side=OrderSide.BUY, quantity=10
        )
        result = broker.place_order(order)
        assert result.success is True
        assert result.order_id == "ORD12345"
        assert result.status == OrderStatus.FILLED

    def test_place_order_failure(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.place_order.side_effect = RuntimeError("API error")

        order = OrderRequest(
            ticker="005930", side=OrderSide.BUY, quantity=10
        )
        result = broker.place_order(order)
        assert result.success is False
        assert result.status == OrderStatus.REJECTED


class TestKISBrokerGetPortfolio:
    def test_parse_portfolio(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.account_no = "12345678-01"
        broker._client.get_balance.return_value = {
            "output1": [
                {
                    "pdno": "005930",
                    "prdt_name": "삼성전자",
                    "hldg_qty": "100",
                    "pchs_avg_pric": "70000",
                    "prpr": "73500",
                    "evlu_pfls_amt": "350000",
                    "evlu_pfls_rt": "5.0",
                    "evlu_amt": "7350000",
                },
                {
                    "pdno": "000660",
                    "prdt_name": "SK하이닉스",
                    "hldg_qty": "0",  # zero quantity — should be filtered
                    "pchs_avg_pric": "150000",
                    "prpr": "160000",
                    "evlu_pfls_amt": "0",
                    "evlu_pfls_rt": "0",
                    "evlu_amt": "0",
                },
            ],
            "output2": [
                {
                    "tot_evlu_amt": "17350000",
                    "dnca_tot_amt": "10000000",
                    "nass_amt": "10000000",
                    "evlu_pfls_smtl_amt": "350000",
                }
            ],
        }

        snapshot = broker.get_portfolio()
        assert snapshot.account_no == "12345678-01"
        assert snapshot.balance.total_equity == 17350000
        assert snapshot.balance.cash_balance == 10000000
        assert snapshot.balance.total_unrealized_pnl == 350000
        assert len(snapshot.positions) == 1  # zero-qty filtered out
        assert snapshot.positions[0].ticker == "005930"
        assert snapshot.positions[0].name == "삼성전자"
        assert snapshot.positions[0].quantity == 100

    def test_empty_portfolio(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.account_no = "12345678-01"
        broker._client.get_balance.return_value = {
            "output1": [],
            "output2": [
                {
                    "tot_evlu_amt": "5000000",
                    "dnca_tot_amt": "5000000",
                    "nass_amt": "5000000",
                    "evlu_pfls_smtl_amt": "0",
                }
            ],
        }

        snapshot = broker.get_portfolio()
        assert len(snapshot.positions) == 0
        assert snapshot.balance.total_equity == 5000000


class TestKISBrokerGetCurrentPrice:
    def test_get_current_price(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.get_current_price.return_value = {
            "output": {"stck_prpr": "73500"}
        }

        price = broker.get_current_price("005930")
        assert price == 73500.0


class TestKISBrokerOrderStatus:
    def test_order_filled(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.get_order_status.return_value = {
            "output1": [
                {
                    "odno": "ORD001",
                    "tot_ccld_qty": "10",
                    "ord_qty": "10",
                    "avg_prvs": "70000",
                }
            ]
        }

        result = broker.get_order_status("ORD001")
        assert result.success is True
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == 10

    def test_order_partially_filled(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.get_order_status.return_value = {
            "output1": [
                {
                    "odno": "ORD001",
                    "tot_ccld_qty": "5",
                    "ord_qty": "10",
                    "avg_prvs": "70000",
                }
            ]
        }

        result = broker.get_order_status("ORD001")
        assert result.status == OrderStatus.PARTIALLY_FILLED

    def test_order_not_found(self):
        config = {
            "broker": {
                "mode": "paper",
                "kis_app_key": "key",
                "kis_app_secret": "secret",
                "kis_account_no": "12345678-01",
            }
        }
        broker = KISBroker(config)
        broker._client = MagicMock()
        broker._client.get_order_status.return_value = {"output1": []}

        result = broker.get_order_status("MISSING")
        assert result.success is False
        assert "not found" in result.message
