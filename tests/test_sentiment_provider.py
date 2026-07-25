"""Unit tests for the A-share sentiment provider."""

from __future__ import annotations

import pytest

from tradingagents.dataflows import sentiment_provider
from tradingagents.dataflows.china_data import ChinaDataUnavailableError


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_hot_list_parses(monkeypatch):
    payload = {
        "data": {
            "stock_list": [
                {
                    "order": 1,
                    "code": "000001",
                    "name": "平安银行",
                    "rate": 95,
                    "rise_and_fall": 5.0,
                    "hot_rank_chg": 2,
                    "tag": {"concept_tag": ["银行", "金融"], "popularity_tag": "热门"},
                }
            ]
        }
    }
    monkeypatch.setattr(sentiment_provider.requests, "get", lambda *a, **kw: _FakeResp(payload))

    report = sentiment_provider.get_a_share_hot_list()

    assert "Source: ths" in report
    assert "平安银行" in report
    assert "银行" in report


def test_hot_list_raises_on_empty(monkeypatch):
    monkeypatch.setattr(sentiment_provider.requests, "get", lambda *a, **kw: _FakeResp({"data": {"stock_list": []}}))
    with pytest.raises(ChinaDataUnavailableError, match="no hot-list"):
        sentiment_provider.get_a_share_hot_list()


def test_hot_concept_parses(monkeypatch):
    payload = {"data": [{"conceptName": "银行", "conceptId": "BK0448", "hitCount": 100}]}
    monkeypatch.setattr(sentiment_provider.requests, "post", lambda *a, **kw: _FakeResp(payload))

    report = sentiment_provider.get_a_share_hot_concept("000001")

    assert "Source: eastmoney" in report
    assert "银行" in report


def test_hot_concept_rejects_non_a_share():
    with pytest.raises(ChinaDataUnavailableError, match="not recognized as an A-share"):
        sentiment_provider.get_a_share_hot_concept("AAPL")
