import json
from unittest import mock

import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config


def _metadata(rendered: str) -> dict:
    first_line = rendered.splitlines()[0]
    prefix = "<!-- TA_DATA_PROVENANCE: "
    assert first_line.startswith(prefix)
    return json.loads(first_line[len(prefix):-4])


@pytest.mark.unit
def test_tool_router_adds_source_cutoff_fetch_time_and_fallback_attempts():
    set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})

    def failed(*args, **kwargs):
        raise ValueError("temporary failure")

    patched = {
        "yfinance": failed,
        "alpha_vantage": lambda *args, **kwargs: "CSV_DATA",
    }
    with mock.patch.dict(interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False):
        rendered = interface.route_to_vendor_with_provenance(
            "get_stock_data", "AAPL", "2026-01-01", "2026-01-10"
        )
        legacy = interface.route_to_vendor(
            "get_stock_data", "AAPL", "2026-01-01", "2026-01-10"
        )

    metadata = _metadata(rendered)
    assert metadata["source"] == "alpha_vantage"
    assert metadata["analysis_cutoff"] == "2026-01-10"
    assert metadata["data_as_of"] == "on_or_before:2026-01-10"
    assert metadata["point_in_time"] == "cutoff_enforced"
    assert metadata["attempted_sources"][0] == {
        "source": "yfinance",
        "status": "error",
    }
    assert legacy == "CSV_DATA"


@pytest.mark.unit
def test_historical_live_snapshot_is_excluded_without_calling_provider():
    provider = mock.Mock(return_value="CURRENT OVERVIEW")
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {"get_fundamentals": {"yfinance": provider}},
        clear=False,
    ):
        rendered = interface.route_to_vendor_with_provenance(
            "get_fundamentals", "AAPL", "2020-01-01"
        )
    provider.assert_not_called()
    metadata = _metadata(rendered)
    assert metadata["status"] == "unavailable"
    assert metadata["point_in_time"] == "live_snapshot_only"
    assert "live snapshot only" in rendered


@pytest.mark.unit
def test_financial_statement_discloses_unverified_availability_time():
    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {"get_balance_sheet": {"yfinance": lambda *args: "STATEMENT"}},
        clear=False,
    ):
        rendered = interface.route_to_vendor_with_provenance(
            "get_balance_sheet", "AAPL", "quarterly", "2026-01-10"
        )
    metadata = _metadata(rendered)
    assert metadata["quality"] == "limited"
    assert metadata["point_in_time"] == "period_end_cutoff_requested_availability_unverified"


@pytest.mark.unit
def test_explicit_unavailable_payload_uses_configured_fallback():
    set_config({"data_vendors": {"core_stock_apis": "yfinance,alpha_vantage"}})
    patched = {
        "yfinance": lambda *args: "",
        "alpha_vantage": lambda *args: "FALLBACK_DATA",
    }
    with mock.patch.dict(interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False):
        rendered = interface.route_to_vendor_with_provenance(
            "get_stock_data", "AAPL", "2026-01-01", "2026-01-10"
        )
    metadata = _metadata(rendered)
    assert "FALLBACK_DATA" in rendered
    assert metadata["source"] == "alpha_vantage"
    assert metadata["attempted_sources"][0]["status"] == "unavailable"


@pytest.mark.unit
def test_provenance_redacts_secret_shaped_optional_errors():
    set_config({"data_vendors": {"macro_data": "fred"}})

    def failed(*args, **kwargs):
        raise ValueError("request failed api_key=super-secret")

    with mock.patch.dict(
        interface.VENDOR_METHODS,
        {"get_macro_indicators": {"fred": failed}},
        clear=False,
    ):
        rendered = interface.route_to_vendor_with_provenance(
            "get_macro_indicators", "cpi", "2026-01-10"
        )
    assert "super-secret" not in rendered
    assert "[REDACTED]" in rendered
