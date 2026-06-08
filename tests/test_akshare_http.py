from unittest.mock import MagicMock, patch

import requests

from tradingagents.dataflows.akshare_http import bypass_system_proxy, run_akshare


def test_bypass_system_proxy_forces_no_proxy_and_disables_trust_env():
    seen = {}

    def fake_request(self, method, url, **kwargs):
        seen["proxies"] = kwargs.get("proxies")
        seen["trust_env"] = self.trust_env
        response = MagicMock()
        response.status_code = 200
        return response

    original = requests.Session.request
    with patch.object(requests.Session, "request", fake_request):
        with bypass_system_proxy():
            session = requests.Session()
            session.request("GET", "https://push2his.eastmoney.com/test")

    assert seen["proxies"] == {"http": None, "https": None}
    assert seen["trust_env"] is False


def test_run_akshare_retries_transient_errors():
    calls = {"n": 0}

    def flaky(x):
        calls["n"] += 1
        if calls["n"] < 2:
            raise requests.exceptions.ConnectionError("boom")
        return x + 1

    assert run_akshare(flaky, 1) == 2
    assert calls["n"] == 2
