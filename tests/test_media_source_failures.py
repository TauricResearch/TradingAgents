"""Collector adapters preserve the difference between empty and unavailable."""

import json
from urllib.error import HTTPError

import pytest

from tradingagents.dataflows import media_sources
from tradingagents.dataflows.errors import (
    ProviderResponseError,
    ProviderTransientError,
)


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


def _raises(exc):
    def fail(*_args, **_kwargs):
        raise exc

    return fail


@pytest.mark.unit
@pytest.mark.parametrize(
    ("fetcher", "payload"),
    [
        (media_sources.fetch_stocktwits, {"messages": []}),
        (media_sources.fetch_bluesky, {"posts": []}),
        (media_sources.fetch_truthsocial, {"statuses": []}),
    ],
)
def test_json_social_fetcher_accepts_explicit_empty_collection(
    monkeypatch, fetcher, payload
):
    monkeypatch.setattr(media_sources, "_get_json", lambda *_args, **_kwargs: payload)

    assert fetcher("NVDA", 1.0) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "fetcher",
    [
        media_sources.fetch_stocktwits,
        media_sources.fetch_bluesky,
        media_sources.fetch_truthsocial,
    ],
)
def test_json_social_fetcher_rejects_ambiguous_empty_envelope(monkeypatch, fetcher):
    monkeypatch.setattr(media_sources, "_get_json", lambda *_args, **_kwargs: {})

    with pytest.raises(ProviderResponseError):
        fetcher("NVDA", 1.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("fetcher", "payload"),
    [
        (
            media_sources.fetch_stocktwits,
            {
                "messages": [{
                    "id": 1,
                    "body": "public view",
                    "created_at": "2026-08-07T12:00:00Z",
                    "user": [],
                    "entities": {"sentiment": None},
                }]
            },
        ),
        (
            media_sources.fetch_bluesky,
            {
                "posts": [{
                    "uri": "at://post/1",
                    "author": {"handle": "public.example"},
                    "record": [],
                }]
            },
        ),
        (
            media_sources.fetch_truthsocial,
            {
                "statuses": [{
                    "id": "1",
                    "created_at": "2026-08-07T12:00:00Z",
                    "content": "public view",
                    "account": [],
                }]
            },
        ),
    ],
)
def test_json_social_fetcher_rejects_malformed_nonempty_item(
    monkeypatch, fetcher, payload
):
    monkeypatch.setattr(media_sources, "_get_json", lambda *_args, **_kwargs: payload)

    with pytest.raises(ProviderResponseError):
        fetcher("NVDA", 1.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("fetcher", "payload", "external_id"),
    [
        (
            media_sources.fetch_stocktwits,
            {
                "messages": [{
                    "id": 1,
                    "body": "public view",
                    "created_at": "2026-08-07T12:00:00Z",
                    "user": {"username": "public_user"},
                    "entities": {"sentiment": {"basic": "Bullish"}},
                }]
            },
            "1",
        ),
        (
            media_sources.fetch_bluesky,
            {
                "posts": [{
                    "uri": "at://post/1",
                    "author": {"handle": "public.example"},
                    "record": {
                        "text": "public view",
                        "createdAt": "2026-08-07T12:00:00Z",
                    },
                }]
            },
            "at://post/1",
        ),
        (
            media_sources.fetch_truthsocial,
            {
                "statuses": [{
                    "id": "1",
                    "created_at": "2026-08-07T12:00:00Z",
                    "content": "<p>public view</p>",
                    "account": {"username": "public_user"},
                }]
            },
            "1",
        ),
    ],
)
def test_json_social_fetcher_accepts_complete_item(
    monkeypatch, fetcher, payload, external_id
):
    monkeypatch.setattr(media_sources, "_get_json", lambda *_args, **_kwargs: payload)

    rows = fetcher("NVDA", 1.0)

    assert len(rows) == 1
    assert rows[0]["external_id"] == external_id
    assert rows[0]["body"] == "public view"


@pytest.mark.unit
def test_json_transport_failure_is_not_returned_as_empty(monkeypatch):
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        _raises(TimeoutError("opaque")),
    )

    with pytest.raises(ProviderTransientError):
        media_sources._get_json("https://example.invalid", {}, 1.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, ProviderResponseError), (429, ProviderTransientError)],
)
def test_json_http_failure_is_not_returned_as_empty(monkeypatch, status, error_type):
    failure = HTTPError("https://example.invalid", status, "opaque", {}, None)
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        _raises(failure),
    )

    with pytest.raises(error_type):
        media_sources._get_json("https://example.invalid", {}, 1.0)


@pytest.mark.unit
def test_json_malformed_response_is_not_returned_as_empty(monkeypatch):
    monkeypatch.setattr(media_sources, "urlopen", lambda *_args, **_kwargs: _Response(b"{"))

    with pytest.raises(ProviderResponseError):
        media_sources._get_json("https://example.invalid", {}, 1.0)


@pytest.mark.unit
def test_reddit_accepts_explicit_empty_feed(monkeypatch):
    body = b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    monkeypatch.setattr(media_sources, "urlopen", lambda *_args, **_kwargs: _Response(body))

    assert media_sources.fetch_reddit(
        "NVDA", 1.0, subreddits=("stocks",), inter_request_delay=0
    ) == []


@pytest.mark.unit
def test_reddit_transport_failure_is_not_returned_as_empty(monkeypatch):
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        _raises(TimeoutError("opaque")),
    )

    with pytest.raises(ProviderTransientError):
        media_sources.fetch_reddit(
            "NVDA", 1.0, subreddits=("stocks",), inter_request_delay=0
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        json.dumps({"items": []}).encode(),
        (
            b'<feed xmlns="http://www.w3.org/2005/Atom">'
            b"<entry><title>public view</title>"
            b"<published>2026-08-07T12:00:00Z</published></entry></feed>"
        ),
    ],
)
def test_reddit_malformed_feed_is_not_returned_as_empty(monkeypatch, body):
    monkeypatch.setattr(
        media_sources,
        "urlopen",
        lambda *_args, **_kwargs: _Response(body),
    )

    with pytest.raises(ProviderResponseError):
        media_sources.fetch_reddit(
            "NVDA", 1.0, subreddits=("stocks",), inter_request_delay=0
        )
