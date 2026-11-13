"""The live account's heartbeat (ADR 0010): one GET of the monitoring service's address
within ten seconds, none without an address, never raising, and logging at most the
address's host: whoever has the address can beat in the run's place."""

import logging

import pytest
import requests

from trader.live import heartbeat
from trader.settings import Settings

URL = "https://hc-ping.example/9b1f0c52-private-check"


class Response:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error: Not Found for url: {URL}", response=self)


def raising(exc):
    def get(url, timeout):
        raise exc
    return get


def test_a_beat_is_one_get_of_the_address_within_ten_seconds(caplog):
    caplog.set_level(logging.INFO, logger=heartbeat.__name__)
    gets = []
    assert heartbeat.beat(URL, get=lambda url, timeout: gets.append((url, timeout)) or Response()) is True
    assert gets == [(URL, 10)]
    assert "hc-ping.example" in caplog.text and "9b1f0c52" not in caplog.text


@pytest.mark.parametrize("url", [None, ""])
def test_without_an_address_there_is_no_beat(url):
    assert heartbeat.beat(url, get=lambda url, timeout: pytest.fail("a request was sent")) is False


@pytest.mark.parametrize("get, logged", [
    (lambda url, timeout: Response(404), "HTTPError 404"),
    (raising(requests.ConnectionError(f"Max retries exceeded with url: {URL}")), "ConnectionError"),
    (raising(requests.Timeout(f"Read timed out: {URL}")), "Timeout"),
    (raising(ValueError(f"Invalid URL {URL!r}")), "ValueError"),
])
def test_a_failed_beat_logs_the_host_alone_and_never_raises(get, logged, caplog):
    caplog.set_level(logging.INFO, logger=heartbeat.__name__)
    assert heartbeat.beat(URL, get=get) is False
    assert f"heartbeat to hc-ping.example failed: {logged}" in caplog.text
    assert "9b1f0c52" not in caplog.text and "private-check" not in caplog.text


def test_the_address_comes_from_the_environment_and_stays_out_of_repr(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_LIVE_HEARTBEAT_URL", f"  {URL}  ")
    settings = Settings.from_env()
    assert settings.live_heartbeat_url == URL and "9b1f0c52" not in repr(settings)
    monkeypatch.setenv("TRADER_LIVE_HEARTBEAT_URL", " ")
    assert Settings.from_env().live_heartbeat_url is None
