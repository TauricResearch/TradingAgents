import json

from tradingagents.memory.news_evidence import NewsEvidenceStore


def _prefetched_payload(article_one_title: str = "Constellium Article 1") -> dict[str, str]:
    company_payload = {
        "feed": [
            {
                "title": article_one_title,
                "source": "Sahm",
                "source_domain": "Sahm",
                "url": "https://example.com/company-1",
                "summary": "Constellium summary 1",
                "time_published": "20260327T201008",
            },
            {
                "title": "Constellium Article 2",
                "source": "StoneX",
                "source_domain": "StoneX",
                "url": "https://example.com/company-2",
                "summary": "Constellium summary 2",
                "time_published": "20260401T203000",
            },
        ]
    }
    macro_payload = {
        "feed": [
            {
                "title": "Macro Article 1",
                "source": "Investing.com",
                "source_domain": "Investing.com",
                "url": "https://example.com/macro-1",
                "summary": "Macro summary 1",
                "time_published": "20260401T210741",
            }
        ]
    }
    return {
        "Company-Specific News (Last 7 Days)": json.dumps(company_payload),
        "Global Macroeconomic News (Last 7 Days)": json.dumps(macro_payload),
    }


def test_ingest_prefetched_sections_persists_run_scoped_records(tmp_path):
    store = NewsEvidenceStore(db_path=tmp_path / "news_evidence.sqlite3")

    records = store.ingest_prefetched_sections(
        run_id="run-001",
        ticker="CSTM",
        trade_date="2026-04-02",
        prefetched=_prefetched_payload(),
    )

    assert len(records) == 3
    assert all(record.run_id == "run-001" for record in records)

    fetched = store.fetch_records(run_id="run-001", ticker="CSTM", trade_date="2026-04-02")
    assert [record.ordinal for record in fetched if "Company-Specific" in record.section_label] == [1, 2]
    assert fetched[0].evidence_id.startswith("art_")
    assert fetched[0].published_at == "2026-03-27"


def test_evidence_ids_are_content_based_and_stable_across_runs(tmp_path):
    store = NewsEvidenceStore(db_path=tmp_path / "news_evidence.sqlite3")

    run_one = store.ingest_prefetched_sections(
        run_id="run-001",
        ticker="CSTM",
        trade_date="2026-04-02",
        prefetched=_prefetched_payload(),
    )
    run_two = store.ingest_prefetched_sections(
        run_id="run-002",
        ticker="CSTM",
        trade_date="2026-04-02",
        prefetched={
            "Company-Specific News (Last 7 Days)": json.dumps(
                {
                    "feed": [
                        {
                            "title": "Constellium Article 2",
                            "source": "StoneX",
                            "source_domain": "StoneX",
                            "url": "https://example.com/company-2",
                            "summary": "Constellium summary 2",
                            "time_published": "20260401T203000",
                        },
                        {
                            "title": "Constellium Article 1",
                            "source": "Sahm",
                            "source_domain": "Sahm",
                            "url": "https://example.com/company-1",
                            "summary": "Constellium summary 1",
                            "time_published": "20260327T201008",
                        },
                    ]
                }
            )
        },
    )

    first_ids = {record.title: record.evidence_id for record in run_one}
    second_ids = {record.title: record.evidence_id for record in run_two}

    assert first_ids["Constellium Article 1"] == second_ids["Constellium Article 1"]
    assert first_ids["Constellium Article 2"] == second_ids["Constellium Article 2"]

    fetched_run_two = store.fetch_records(run_id="run-002", ticker="CSTM")
    assert [record.title for record in fetched_run_two] == [
        "Constellium Article 2",
        "Constellium Article 1",
    ]
    assert [record.ordinal for record in fetched_run_two] == [1, 2]


def test_build_prompt_context_includes_evidence_ids_and_sections(tmp_path):
    store = NewsEvidenceStore(db_path=tmp_path / "news_evidence.sqlite3")
    records = store.ingest_prefetched_sections(
        run_id="run-ctx",
        ticker="CSTM",
        trade_date="2026-04-02",
        prefetched=_prefetched_payload(),
    )

    prompt_context = store.build_prompt_context(records)

    assert "## Evidence Records" in prompt_context
    assert "[Evidence ID:" in prompt_context
    assert "Section: Company-Specific News (Last 7 Days)" in prompt_context
