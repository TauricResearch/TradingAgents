import json

from scripts.audit_run_quality import audit_run


def test_audit_fails_quality_headers_that_are_not_ok(tmp_path):
    run_dir = tmp_path / "daily" / "2026-04-10" / "run-1"
    market_dir = run_dir / "market"
    market_dir.mkdir(parents=True)

    for filename in (
        "gatekeeper_universe_report.md",
        "geopolitical_report.md",
        "market_movers_report.md",
        "sector_performance_report.md",
        "factor_alignment_report.md",
        "drift_opportunities_report.md",
        "smart_money_report.md",
        "industry_deep_dive_report.md",
    ):
        (market_dir / filename).write_text(
            "[QUALITY: empty | issues=no_output | evidence=0]\n",
            encoding="utf-8",
        )

    for filename in (
        "gatekeeper_summary.md",
        "geopolitical_summary.md",
        "market_movers_summary.md",
        "sector_summary.md",
        "factor_alignment_summary.md",
        "drift_opportunities_summary.md",
        "smart_money_summary.md",
        "industry_deep_dive_summary.md",
    ):
        (market_dir / filename).write_text("[NO_EVIDENCE] test", encoding="utf-8")

    (run_dir / "run_meta.json").write_text(
        json.dumps({"params": {"max_tickers": 10}}),
        encoding="utf-8",
    )

    result = audit_run(run_dir)

    assert result["pass"] is False
    assert len(result["issues"]) == 8
    assert {issue["issue"] for issue in result["issues"]} == {"quality_degraded"}
