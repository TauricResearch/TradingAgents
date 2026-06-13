from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from dashboard.report_review import (
    DASHBOARD_DISCLAIMER,
    REPORT_ARTIFACTS,
    UNAVAILABLE_SECTION,
    format_data_quality_markdown,
    list_dates,
    list_symbols,
    read_json_artifact,
    read_text_artifact,
    render_markdown_artifact,
    report_bundle_path,
)


@pytest.mark.unit
def test_dashboard_helpers_list_saved_reports_in_read_only_tree(tmp_path):
    (tmp_path / "RELIANCE.NS" / "2026-06-05").mkdir(parents=True)
    (tmp_path / "RELIANCE.NS" / "2026-06-04").mkdir(parents=True)
    (tmp_path / "README.md").write_text("not a symbol folder", encoding="utf-8")

    assert list_symbols(tmp_path) == ["RELIANCE.NS"]
    assert list_dates(tmp_path, "RELIANCE.NS") == ["2026-06-05", "2026-06-04"]
    assert report_bundle_path(tmp_path, "RELIANCE.NS", "2026-06-05") == (
        tmp_path / "RELIANCE.NS" / "2026-06-05"
    )


@pytest.mark.unit
def test_dashboard_renders_markdown_artifacts_and_companion_files(tmp_path):
    base = tmp_path / "RELIANCE.NS" / "2026-06-05"
    base.mkdir(parents=True)
    (base / "8_risk.md").write_text("# Risk\n\nRisk review", encoding="utf-8")
    (base / "compliance.md").write_text("# Compliance\n\nResearch only", encoding="utf-8")
    (base / "disclaimer.md").write_text("# Disclaimer\n\nNot investment advice", encoding="utf-8")

    risk_artifact = next(artifact for artifact in REPORT_ARTIFACTS if artifact.label == "Risk/Compliance")
    rendered = render_markdown_artifact(base, risk_artifact)

    assert "# Risk" in rendered
    assert "# Compliance" in rendered
    assert "# Disclaimer" in rendered
    assert "Not investment advice" in rendered
    assert read_text_artifact(base / "missing.md") == UNAVAILABLE_SECTION


@pytest.mark.unit
def test_dashboard_formats_data_quality_json_for_saved_report_review(tmp_path):
    data = {
        "symbol": "RELIANCE.NS",
        "market_scope": "india",
        "generated_at": "2026-06-07T00:00:00+00:00",
        "coverage_method": "writer_marker_detection_only",
        "limitations": ["Coverage flags are based on section text markers only."],
        "sections": {
            "India Market Technical": {
                "status": "available",
                "source_coverage_detected": True,
                "data_quality_detected": True,
                "confidence_detected": True,
                "contains_unavailable_marker": False,
                "warnings": [],
            },
            "India Flows & Positioning": {
                "status": "unavailable",
                "source_coverage_detected": False,
                "data_quality_detected": True,
                "confidence_detected": False,
                "contains_unavailable_marker": True,
                "warnings": ["Section was not produced in the current run."],
            },
        },
    }

    rendered = format_data_quality_markdown(data)

    assert "# Data Quality" in rendered
    assert "| India Market Technical | available | Yes | Yes | Yes | No |" in rendered
    assert "| India Flows & Positioning | unavailable | No | Yes | No | Yes |" in rendered
    assert "Coverage flags are based on section text markers only." in rendered
    assert "India Flows & Positioning: Section was not produced in the current run." in rendered
    assert "UNAVAILABLE: data_quality.json was not found" in format_data_quality_markdown({})


@pytest.mark.unit
def test_dashboard_reads_bad_json_as_unavailable_warning(tmp_path):
    bad_json = tmp_path / "data_quality.json"
    bad_json.write_text("{not json", encoding="utf-8")

    result = read_json_artifact(bad_json)

    assert result["status"] == "UNAVAILABLE"
    assert "could not be parsed" in result["warning"]
    assert read_json_artifact(tmp_path / "missing.json") == {}


@pytest.mark.unit
def test_dashboard_app_imports_without_streamlit_and_has_no_live_trading_controls():
    module = importlib.import_module("dashboard.app")

    assert hasattr(module, "main")
    assert "research and education only" in DASHBOARD_DISCLAIMER.lower()
    assert "not investment advice" in DASHBOARD_DISCLAIMER.lower()
    assert "SEBI-registered" in DASHBOARD_DISCLAIMER
    assert "Trader Research View" in [artifact.label for artifact in REPORT_ARTIFACTS]
    assert "Data Quality" in [artifact.label for artifact in REPORT_ARTIFACTS]

    app_source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden_controls = (
        "st.button(",
        "st.form_submit_button(",
        "st.link_button(",
        "st.chat_input(",
        "Zerodha",
        "Upstox",
        "Angel",
        "Groww",
        "ICICI Direct",
    )
    assert not any(control in app_source for control in forbidden_controls)
