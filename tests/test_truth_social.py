from datetime import datetime, timedelta, timezone

import pytest
import requests

from tradingagents.dataflows.vendors import truth_social


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def json(self):
        return self._payload


@pytest.mark.unit
def test_truth_social_formats_official_timeline(monkeypatch):
    now = datetime.now(timezone.utc)
    post = {
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content": "<p>New tariff policy &amp; auto announcement</p>",
        "url": "https://truthsocial.com/@realDonaldTrump/1",
        "favourites_count": 10,
        "reblogs_count": 4,
        "replies_count": 2,
    }
    monkeypatch.setattr(
        truth_social.requests,
        "get",
        lambda *a, **k: _Response([post]),
    )
    out = truth_social.fetch_trump_truths(
        start_date=str((now - timedelta(days=1)).date()),
        end_date=str(now.date()),
    )
    assert "@realDonaldTrump" in out
    assert "New tariff policy & auto announcement" in out
    assert "retruths=4" in out


@pytest.mark.unit
def test_truth_social_historical_window_does_not_leak_current_posts(monkeypatch):
    now = datetime.now(timezone.utc)
    post = {
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content": "<p>Current post</p>",
    }
    monkeypatch.setattr(
        truth_social.requests,
        "get",
        lambda *a, **k: _Response([post]),
    )
    out = truth_social.fetch_trump_truths(
        start_date="2020-01-01",
        end_date="2020-01-07",
    )
    assert "unavailable" in out
    assert "Current post" not in out


@pytest.mark.unit
def test_truth_social_waf_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        truth_social.requests,
        "get",
        lambda *a, **k: _Response({}, 403),
    )
    out = truth_social.fetch_trump_truths()
    assert out == "<Truth Social unavailable: official public endpoint returned HTTP 403>"
