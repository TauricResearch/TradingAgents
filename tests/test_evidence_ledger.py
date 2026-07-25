import json

from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.evidence import (
    EvidenceStatus,
    evaluate_and_enrich_evidence,
)
from tradingagents.dataflows.evidence_ledger import (
    EVIDENCE_LEDGER_VERSION,
    build_evidence_ledger,
    persist_evidence_ledger,
)
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore


def _profile():
    return {"ticker": "AAPL", "name": "Apple Inc."}


def _assessment():
    return {
        "status": EvidenceStatus.PASS,
        "company_count": 1,
        "mixed_count": 1,
        "reasons": [],
        "items": [
            {
                "title": "Apple reports earnings",
                "url": "https://example.com/apple-earnings",
                "content": "Revenue increased; private analysis must not be copied.",
                "publisher": "Example News",
                "published": "2026-07-20",
                "source": "tavily_enrichment",
                "credibility": "medium",
                "cross_source_tag": "confirmed",
                "provenance_artifact_ids": ["artifact:provider", "artifact:normalized"],
            }
        ],
    }


def test_evidence_ledger_records_claim_evidence_criteria_without_source_prose():
    ledger = build_evidence_ledger(
        profile=_profile(),
        assessment=_assessment(),
        trade_date="2026-07-21",
        enrichment_rounds=1,
    )

    assert ledger["ledger_version"] == EVIDENCE_LEDGER_VERSION
    assert ledger["verification_status"] == "verified"
    assert len(ledger["claims"]) == 1
    assert {criterion["name"] for criterion in ledger["criteria"]} == {
        "identity_match",
        "company_coverage",
        "mixed_coverage",
    }
    evidence = ledger["evidence"][0]
    assert evidence["source_provider"] == "tavily"
    assert evidence["uri"] == "https://example.com/apple-earnings"
    assert evidence["method"] == "evidence_tavily_enrichment"
    assert len(evidence["artifact_hash"]) == 64
    assert evidence["source_artifact_ids"] == ["artifact:provider", "artifact:normalized"]
    assert "private analysis" not in json.dumps(ledger, ensure_ascii=False)
    assert evidence["evidence_id"] in ledger["claims"][0]["evidence_ids"]


def test_evidence_ledger_persists_artifact_and_typed_event_when_observed(tmp_path):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-21")
    store.create_run(snapshot)
    observer = DurableRunObserver(store, snapshot.run_id)
    turn = observer.start_turn(
        actor_id="evidence.steward",
        graph_task_id="task-evidence-ledger",
        graph_step=5,
        turn_index=1,
    )
    ledger = build_evidence_ledger(
        profile=_profile(),
        assessment=_assessment(),
        trade_date="2026-07-21",
        enrichment_rounds=1,
    )

    with observer.invocation_scope(turn, graph_task_id="task-evidence-ledger", graph_step=5):
        artifact_id = persist_evidence_ledger(ledger)

    assert artifact_id is not None
    saved = json.loads(store.read_artifact(snapshot.run_id, artifact_id))
    assert saved["ledger_id"] == ledger["ledger_id"]
    event = next(
        item
        for item in store.read_events(snapshot.run_id)
        if item.type == "evidence.ledger_written"
    )
    assert event.payload["artifact_id"] == artifact_id
    assert event.payload["turn_id"] == turn.turn_id
    assert event.payload["claim_count"] == 1
    assert event.payload["evidence_count"] == 1


def test_evidence_steward_returns_ledger_as_declared_business_data(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.dataflows.evidence.create_llm_from_config",
        lambda: None,
    )
    set_config({"news_min_company_items": 1, "news_min_mixed_items": 1})

    result = evaluate_and_enrich_evidence(
        {
            "company_of_interest": "AAPL",
            "trade_date": "2026-07-21",
            "market_report": "market ok",
            "fundamentals_report": "fundamentals ok",
            "news_report": (
                "### Apple earnings release\n"
                "AAPL reported earnings.\n"
                "Link: https://www.sec.gov/Archives/apple-earnings"
            ),
            "sentiment_report": "",
            "canonical_company_profile": _profile(),
        }
    )

    assert result["evidence_status"] == EvidenceStatus.PASS.value
    assert result["evidence_ledger_artifact_id"] is None
    assert result["evidence_ledger"]["subject"]["ticker"] == "AAPL"
    assert result["evidence_ledger"]["claims"][0]["verification_status"] == "verified"


def test_evidence_ledger_records_direction_score_when_supplied():
    ledger = build_evidence_ledger(
        profile=_profile(),
        assessment=_assessment(),
        trade_date="2026-07-21",
        enrichment_rounds=1,
        direction_scores={"https://example.com/apple-earnings": 0.6},
    )

    assert ledger["evidence"][0]["direction_score"] == 0.6


def test_evidence_ledger_omits_direction_score_when_not_supplied():
    ledger = build_evidence_ledger(
        profile=_profile(),
        assessment=_assessment(),
        trade_date="2026-07-21",
        enrichment_rounds=1,
    )

    assert ledger["evidence"][0]["direction_score"] is None
