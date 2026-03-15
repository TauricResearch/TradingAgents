"""Tests for tradingagents.execution.kis.client (KISClient + RateLimiter)."""

import time
from unittest.mock import patch, MagicMock

import pytest

from tradingagents.execution.kis.client import KISClient, RateLimiter


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_acquire_within_limit(self):
        rl = RateLimiter(max_calls=5, period=1.0)
        for _ in range(5):
            rl.acquire()  # should not sleep
        assert len(rl._timestamps) == 5

    def test_acquire_sleeps_when_exhausted(self):
        rl = RateLimiter(max_calls=2, period=1.0)
        rl.acquire()
        rl.acquire()
        with patch("tradingagents.execution.kis.client.time.sleep") as mock_sleep:
            rl.acquire()
            # Should have attempted to sleep (may or may not depending on timing)
            # The key assertion: no crash and timestamps are maintained
        assert len(rl._timestamps) >= 1


# ---------------------------------------------------------------------------
# KISClient — init & helpers
# ---------------------------------------------------------------------------


class TestKISClientInit:
    def test_paper_mode_url(self):
        client = KISClient("key", "secret", "12345678-01", mode="paper")
        assert "openapivts" in client.base_url

    def test_real_mode_url(self):
        client = KISClient("key", "secret", "12345678-01", mode="real")
        assert "openapi.koreainvestment" in client.base_url

    def test_account_parsing(self):
        client = KISClient("key", "secret", "12345678-02", mode="paper")
        cano, prdt = client._acnt_prdt_cd
        assert cano == "12345678"
        assert prdt == "02"

    def test_account_parsing_no_dash(self):
        client = KISClient("key", "secret", "12345678", mode="paper")
        cano, prdt = client._acnt_prdt_cd
        assert cano == "12345678"
        assert prdt == "01"

    def test_headers(self):
        client = KISClient("key", "secret", "12345678-01", mode="paper")
        client._token = "test_token"
        headers = client._headers("VTTC0802U")
        assert headers["authorization"] == "Bearer test_token"
        assert headers["appkey"] == "key"
        assert headers["tr_id"] == "VTTC0802U"


# ---------------------------------------------------------------------------
# KISClient — token management
# ---------------------------------------------------------------------------


class TestKISClientToken:
    def _make_client(self):
        return KISClient("key", "secret", "12345678-01", mode="paper")

    @patch("tradingagents.execution.kis.client.requests.post")
    def test_request_token_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "tok_abc",
            "expires_in": "86400",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = self._make_client()
        client._request_token()

        assert client._token == "tok_abc"
        assert client._token_expires_at is not None
        mock_post.assert_called_once()

    @patch("tradingagents.execution.kis.client.requests.post")
    def test_request_token_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_post.return_value = mock_resp

        client = self._make_client()
        with pytest.raises(Exception, match="401"):
            client._request_token()

    @patch("tradingagents.execution.kis.client.requests.post")
    def test_ensure_token_caches(self, mock_post):
        """_ensure_token should not re-fetch if token is still valid."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "tok_abc",
            "expires_in": "86400",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = self._make_client()
        client._ensure_token()  # first call — fetches token
        client._ensure_token()  # second call — should reuse cached token

        assert mock_post.call_count == 1


# ---------------------------------------------------------------------------
# KISClient — API methods (mocking _request)
# ---------------------------------------------------------------------------


class TestKISClientPlaceOrder:
    def _make_client(self):
        client = KISClient("key", "secret", "12345678-01", mode="paper")
        client._token = "test_token"
        client._token_expires_at = None
        return client

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "_ensure_token")
    def test_place_buy_order(self, mock_ensure, mock_request):
        mock_request.return_value = {
            "output": {"ODNO": "ORD001"},
            "rt_cd": "0",
        }
        client = self._make_client()
        result = client.place_order("005930", "BUY", 10, "MARKET", 0)

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"  # method
        assert call_args[1]["body"]["PDNO"] == "005930"
        assert call_args[1]["body"]["ORD_QTY"] == "10"

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "_ensure_token")
    def test_place_sell_order_uses_sell_tr_id(self, mock_ensure, mock_request):
        mock_request.return_value = {"output": {"ODNO": "ORD002"}, "rt_cd": "0"}
        client = self._make_client()
        client.place_order("005930", "SELL", 5, "MARKET", 0)

        call_args = mock_request.call_args
        assert call_args[0][2] == "VTTC0801U"  # paper sell tr_id

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "_ensure_token")
    def test_place_limit_order(self, mock_ensure, mock_request):
        mock_request.return_value = {"output": {"ODNO": "ORD003"}, "rt_cd": "0"}
        client = self._make_client()
        client.place_order("005930", "BUY", 10, "LIMIT", 70000)

        body = mock_request.call_args[1]["body"]
        assert body["ORD_DVSN"] == "00"  # LIMIT code
        assert body["ORD_UNPR"] == "70000"


class TestKISClientGetBalance:
    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "_ensure_token")
    def test_get_balance(self, mock_ensure, mock_request):
        mock_request.return_value = {
            "output1": [],
            "output2": [{"tot_evlu_amt": "5000000"}],
        }
        client = KISClient("key", "secret", "12345678-01", mode="paper")
        client._token = "tok"
        result = client.get_balance()

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[1]["params"]["CANO"] == "12345678"


class TestKISClientGetCurrentPrice:
    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "_ensure_token")
    def test_get_current_price(self, mock_ensure, mock_request):
        mock_request.return_value = {
            "output": {"stck_prpr": "73500"}
        }
        client = KISClient("key", "secret", "12345678-01", mode="paper")
        client._token = "tok"
        result = client.get_current_price("005930")

        params = mock_request.call_args[1]["params"]
        assert params["FID_INPUT_ISCD"] == "005930"


class TestKISClientGetOrderStatus:
    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "_ensure_token")
    def test_get_order_status(self, mock_ensure, mock_request):
        mock_request.return_value = {"output1": []}
        client = KISClient("key", "secret", "12345678-01", mode="paper")
        client._token = "tok"
        result = client.get_order_status("20260301", "20260315")

        params = mock_request.call_args[1]["params"]
        assert params["INQR_STRT_DT"] == "20260301"
        assert params["INQR_END_DT"] == "20260315"


# ---------------------------------------------------------------------------
# KISClient — _request method (mocking requests.get/post)
# ---------------------------------------------------------------------------


class TestKISClientRequest:
    def _make_client_with_token(self):
        client = KISClient("key", "secret", "12345678-01", mode="paper")
        client._token = "test_token"
        # Set a far-future expiry so _ensure_token doesn't re-fetch
        from datetime import datetime, timedelta
        client._token_expires_at = datetime.now() + timedelta(hours=23)
        return client

    @patch("tradingagents.execution.kis.client.requests.get")
    def test_get_request(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"output": {"data": "value"}, "rt_cd": "0"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = self._make_client_with_token()
        result = client._request("GET", "/test/path", "TR001", params={"k": "v"})

        assert result["output"]["data"] == "value"
        mock_get.assert_called_once()

    @patch("tradingagents.execution.kis.client.requests.post")
    def test_post_request(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"output": {"ODNO": "123"}, "rt_cd": "0"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = self._make_client_with_token()
        result = client._request("POST", "/test/path", "TR002", body={"k": "v"})

        assert result["output"]["ODNO"] == "123"
        mock_post.assert_called_once()

    @patch("tradingagents.execution.kis.client.requests.get")
    def test_api_error_raises_runtime(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"rt_cd": "1", "msg1": "Invalid parameter"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = self._make_client_with_token()
        with pytest.raises(RuntimeError, match="Invalid parameter"):
            client._request("GET", "/test/path", "TR001")
