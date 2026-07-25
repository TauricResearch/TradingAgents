"""Read-only chart projection contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradingagents.dataflows.news_layers import FileDeepAnalysisCache, decide_layer2
from tradingagents.observability.events import RunEventDraft
from tradingagents.web.api import create_app
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore

pytestmark = pytest.mark.unit


def _snapshot() -> RunSnapshot:
    return RunSnapshot.create(
        run_id="run_20260723T000000000000Z_1234abcd",
        ticker="600519.SS",
        analysis_date="2026-07-23",
        selected_analysts=("market",),
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        output_language="Chinese",
        llm_provider="openai",
        quick_think_llm="quick",
        deep_think_llm="deep",
        configured_keys={"openai": True},
    )


def _write_artifact(store: RunStore, run_id: str, value: object):
    artifact = store.store_artifact(run_id, kind="data", value=value)
    store.append_event(
        RunEventDraft(
            run_id,
            "artifact.written",
            {
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind,
                "media_type": artifact.media_type,
                "content_sha256": artifact.content_sha256,
                "byte_size": artifact.byte_size,
                "locator": artifact.locator,
            },
        )
    )
    return artifact


def test_market_view_projects_only_persisted_valid_records(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    snapshot = _snapshot()
    store.create_run(snapshot)
    ohlcv = _write_artifact(
        store,
        snapshot.run_id,
        {
            "columns": ["Open", "High", "Low", "Close", "Volume"],
            "index": ["2026-07-21", "2026-07-22"],
            "data": [[1500, 1520, 1492, 1518, 600], [1518, 1535, 1510, 1526, 720]],
        },
    )
    news = _write_artifact(
        store,
        snapshot.run_id,
        {
            "results": [
                {
                    "title": "利润预期上调",
                    "published_date": "2026-07-22T09:30:00+08:00",
                    "url": "https://example.test/news",
                    "publisher": "Example",
                    "sentiment": "Bullish",
                },
                {"title": "missing date is not chartable"},
            ]
        },
    )
    # An invalid row must not become an inferred/guessed price.
    _write_artifact(
        store,
        snapshot.run_id,
        {"bars": [{"date": "2026-07-22", "open": 10, "high": 9, "low": 8, "close": 9}]},
    )
    client = TestClient(create_app(store=store, recover_startup=False))

    response = client.get(f"/api/runs/{snapshot.run_id}/market-view")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=60"
    payload = response.json()
    assert [bar["close"] for bar in payload["bars"]] == [1518.0, 1526.0]
    assert payload["bars"][0]["artifact_id"] == ohlcv.artifact_id
    assert payload["events"] == [
        {
            "timestamp": "2026-07-22T09:30:00+08:00",
            "title": "利润预期上调",
            "artifact_id": news.artifact_id,
            "url": "https://example.test/news",
            "source": "Example",
            "sentiment": "bullish",
        }
    ]
    assert payload["coverage"]["bar_source_artifact_ids"] == [ohlcv.artifact_id]
    assert payload["coverage"]["event_source_artifact_ids"] == [news.artifact_id]
    assert payload["coverage"]["as_of_sequence"] == 3


def test_market_view_degrades_to_empty_when_no_chartable_artifact(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    snapshot = _snapshot()
    store.create_run(snapshot)
    client = TestClient(create_app(store=store, recover_startup=False))

    response = client.get(f"/api/runs/{snapshot.run_id}/market-view")

    assert response.status_code == 200
    assert response.json() == {
        "bars": [],
        "events": [],
        "coverage": {
            "bar_source_artifact_ids": [],
            "event_source_artifact_ids": [],
            "skipped_artifact_count": 0,
            "as_of_sequence": 0,
        },
    }


def test_market_event_layer2_only_reads_a_cached_public_conclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = RunStore(tmp_path / "runs")
    snapshot = _snapshot()
    store.create_run(snapshot)
    news = _write_artifact(
        store,
        snapshot.run_id,
        {
            "results": [
                {
                    "title": "利润预期上调",
                    "published_date": "2026-07-22T09:30:00+08:00",
                    "content": "A persisted public event for the local chart.",
                }
            ]
        },
    )
    cache_dir = tmp_path / "layer2"
    monkeypatch.setattr(
        "tradingagents.web.market_layer2.get_config",
        lambda: {"news_layer2_cache_dir": str(cache_dir)},
    )
    trigger = decide_layer2(
        evidence_status="insufficient",
        subject=f"{snapshot.ticker}:{news.artifact_id}:利润预期上调",
        data_as_of="2026-07-22T09:30:00+08:00",
    )
    assert trigger.cache_key is not None
    FileDeepAnalysisCache(cache_dir).put(
        trigger.cache_key,
        {
            "conclusion": "Check the official guidance update.",
            "evidence_gaps": ["official filing"],
            "material_risks": ["guidance reversal"],
            "source_ids": ["persisted-news"],
            "reasoning": "must never reach the browser",
        },
    )
    client = TestClient(create_app(store=store, recover_startup=False))
    params = {
        "artifact_id": news.artifact_id,
        "timestamp": "2026-07-22T09:30:00+08:00",
        "title": "利润预期上调",
    }

    response = client.get(f"/api/runs/{snapshot.run_id}/market-view/layer2", params=params)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=60"
    assert response.json() == {
        "status": "cached",
        "event": params,
        "trigger": {
            "reasons": ["evidence_thin"],
            "cache_key": trigger.cache_key,
        },
        "cache_configured": True,
        "conclusion": {
            "conclusion": "Check the official guidance update.",
            "evidence_gaps": ["official filing"],
            "material_risks": ["guidance reversal"],
            "source_ids": ["persisted-news"],
        },
    }

    # An event query can never become a free-form deep-analysis endpoint.
    missing = client.get(
        f"/api/runs/{snapshot.run_id}/market-view/layer2",
        params={**params, "title": "not in persisted artifacts"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "market_event_not_found"
