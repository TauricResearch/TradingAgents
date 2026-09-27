from datetime import datetime, timedelta, timezone

import pytest
import requests

from tradingagents.dataflows.vendors import x_social


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
def test_x_requires_a_bearer_token(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    assert "X_BEARER_TOKEN is not configured" in x_social.fetch_x_posts("TSLA")


@pytest.mark.unit
def test_x_old_window_is_withheld_without_a_request(monkeypatch):
    called = False

    def fake_get(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(x_social.requests, "get", fake_get)
    out = x_social.fetch_x_posts(
        "TSLA",
        start_date="2020-01-01",
        end_date="2020-01-07",
        bearer_token="token",
    )
    assert "only covers the last 7 days" in out
    assert called is False


@pytest.mark.unit
def test_x_formats_posts_and_engagement(monkeypatch):
    now = datetime.now(timezone.utc)
    created = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return _Response(
            {
                "data": [
                    {
                        "id": "p1",
                        "author_id": "u1",
                        "created_at": created,
                        "text": "$TSLA delivery update",
                        "public_metrics": {
                            "like_count": 12,
                            "retweet_count": 3,
                            "reply_count": 2,
                            "quote_count": 1,
                        },
                    }
                ],
                "includes": {"users": [{"id": "u1", "username": "marketwatcher"}]},
            }
        )

    monkeypatch.setattr(x_social.requests, "get", fake_get)
    out = x_social.fetch_x_posts(
        "TSLA",
        start_date=str((now - timedelta(days=1)).date()),
        end_date=str(now.date()),
        bearer_token="secret",
    )
    assert "@marketwatcher" in out
    assert "likes=12" in out
    assert "$TSLA delivery update" in out
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["params"]["query"].startswith("($TSLA OR TSLA)")


@pytest.mark.unit
def test_x_http_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(x_social.requests, "get", lambda *a, **k: _Response({}, 429))
    out = x_social.fetch_x_posts("TSLA", bearer_token="token")
    assert out == "<X unavailable: HTTP 429>"
