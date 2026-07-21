"""TW Market Data vendor.

Covers the router contract every vendor must honour — typed errors, no-data
signalling — and the two things specific to this vendor: Taiwan symbol handling
and publication-date look-ahead filtering on statements and monthly revenue.

No network. The twmd client is faked at the module boundary, so these run in the
same keyless CI as the rest of the suite.
"""
import types

import pandas as pd
import pytest

import tradingagents.dataflows.twmd as twmd
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)


# --- fakes matching the twmd client surface the vendor actually uses ----------

class _FakeAuthError(Exception):
    error_code = "missing_api_key"


class _FakePaymentError(Exception):
    error_code = "payment_required"


class _FakeRateLimit(Exception):
    pass


def _install_fake_twmd(monkeypatch, *, frames=None, raises=None, record=None):
    """Install a fake ``twmd`` module so ``from twmd import ...`` resolves.

    ``frames`` maps dataset name -> DataFrame to return; ``raises`` maps dataset
    name -> exception instance to raise. ``record`` (a dict) captures the kwargs
    the client was constructed with, so a test can assert the source marker.
    """
    frames = frames or {}
    raises = raises or {}

    class FakeClient:
        def __init__(self, **kwargs):
            if record is not None:
                record.update(kwargs)

        def get_dataset(self, dataset, **kwargs):
            if dataset in raises:
                raise raises[dataset]
            return frames.get(dataset, pd.DataFrame())

    fake = types.ModuleType("twmd")
    fake.Client = FakeClient
    fake.TwmdAuthError = _FakeAuthError
    fake.TwmdPaymentRequired = _FakePaymentError
    fake.TwmdRateLimitError = _FakeRateLimit
    monkeypatch.setitem(__import__("sys").modules, "twmd", fake)
    return fake


def _price_frame():
    df = pd.DataFrame(
        [
            {"symbol": "2330", "date": "2026-07-16", "open": 100.0, "close": 101.0},
            {"symbol": "2330", "date": "2026-07-17", "open": 101.0, "close": 100.0},
        ]
    )
    df.attrs["data_as_of"] = "2026-07-17"
    df.attrs["lineage"] = {"provider": "TWSE", "not_investment_advice": True}
    return df


def _revenue_frame():
    return pd.DataFrame(
        [
            {"symbol": "2330", "month": "2026-04", "revenue": 410.0,
             "mom": -1.08, "yoy": 17.5, "announcement_date": "2026-05-17"},
            {"symbol": "2330", "month": "2026-05", "revenue": 420.0,
             "mom": 2.4, "yoy": 20.0, "announcement_date": "2026-06-17"},
        ]
    )


# --- symbol handling ----------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("given,expected", [
    ("2330", "2330"),
    ("2330.TW", "2330"),
    ("2330.tw", "2330"),
    ("6488.TWO", "6488"),
    (" 2330 ", "2330"),
])
def test_canonical_strips_yahoo_suffix(given, expected):
    assert twmd._canonical(given) == expected


# --- core prices --------------------------------------------------------------

@pytest.mark.unit
def test_get_stock_returns_csv_with_lineage(monkeypatch):
    _install_fake_twmd(monkeypatch, frames={"twse-daily-price": _price_frame()})
    out = twmd.get_stock("2330.TW", "2026-07-16", "2026-07-17")

    assert "Taiwan daily prices" in out
    assert "2330 (from 2330.TW)" in out
    assert "provider: TWSE" in out
    assert "data_as_of: 2026-07-17" in out
    assert "2026-07-16" in out and "2026-07-17" in out


@pytest.mark.unit
def test_get_stock_filters_to_requested_range(monkeypatch):
    _install_fake_twmd(monkeypatch, frames={"twse-daily-price": _price_frame()})
    out = twmd.get_stock("2330", "2026-07-17", "2026-07-17")
    assert "2026-07-17" in out
    assert "2026-07-16" not in out.split("\n\n", 1)[1]  # not in the CSV body


@pytest.mark.unit
def test_get_stock_empty_raises_no_market_data(monkeypatch):
    _install_fake_twmd(monkeypatch, frames={"twse-daily-price": pd.DataFrame()})
    with pytest.raises(NoMarketDataError):
        twmd.get_stock("9999", "2026-07-16", "2026-07-17")


@pytest.mark.unit
def test_client_built_with_ecosystem_source_marker(monkeypatch):
    # §6 unified attribution: the vendor must tag its traffic as tradingagents.
    record = {}
    _install_fake_twmd(monkeypatch, frames={"twse-daily-price": _price_frame()}, record=record)
    twmd.get_stock("2330", "2026-07-16", "2026-07-17")
    assert record.get("source") == "ecosys/tradingagents"


# --- error mapping onto the router taxonomy -----------------------------------

@pytest.mark.unit
def test_auth_error_maps_to_not_configured(monkeypatch):
    _install_fake_twmd(monkeypatch, raises={"twse-daily-price": _FakeAuthError()})
    with pytest.raises(VendorNotConfiguredError) as info:
        twmd.get_stock("1101", "2026-07-16", "2026-07-17")
    # Message must point at free registration, not just fail.
    assert "twmarketdata.com" in str(info.value)
    assert "sample tickers" in str(info.value)


@pytest.mark.unit
def test_payment_required_maps_to_not_configured(monkeypatch):
    _install_fake_twmd(monkeypatch, raises={"income-statement": _FakePaymentError()})
    with pytest.raises(VendorNotConfiguredError):
        twmd.get_income_statement("2330", curr_date="2026-07-17")


@pytest.mark.unit
def test_rate_limit_maps_to_rate_limit(monkeypatch):
    _install_fake_twmd(monkeypatch, raises={"twse-daily-price": _FakeRateLimit()})
    with pytest.raises(VendorRateLimitError):
        twmd.get_stock("2330", "2026-07-16", "2026-07-17")


@pytest.mark.unit
def test_missing_twmd_install_is_not_configured(monkeypatch):
    # Simulate twmd not installed: importing it raises ImportError.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "twmd":
            raise ImportError("No module named 'twmd'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(VendorNotConfiguredError) as info:
        twmd.get_stock("2330", "2026-07-16", "2026-07-17")
    assert "pip install twmarketdata" in str(info.value)


# --- look-ahead filtering (the correctness contribution) ----------------------

@pytest.mark.unit
def test_monthly_revenue_excludes_unannounced_rows(monkeypatch):
    # At 2026-05-20 the May revenue (announced 2026-06-17) was not yet public.
    _install_fake_twmd(monkeypatch, frames={"monthly-revenue": _revenue_frame()})
    out = twmd.get_fundamentals("2330", curr_date="2026-05-20")

    body = out.split("\n\n", 1)[1]
    data_rows = [r for r in body.strip().splitlines()[1:] if r]  # drop CSV header
    assert len(data_rows) == 1                      # only the visible month
    assert "410.0" in data_rows[0]                  # April revenue, announced 2026-05-17
    assert "420.0" not in body                      # May revenue, announced 2026-06-17, hidden
    assert "by announcement_date" in out


@pytest.mark.unit
def test_look_ahead_note_reports_publication_basis(monkeypatch):
    _install_fake_twmd(monkeypatch, frames={"monthly-revenue": _revenue_frame()})
    out = twmd.get_fundamentals("2330", curr_date="2026-12-31")
    assert "published on/before 2026-12-31" in out


@pytest.mark.unit
def test_period_fallback_when_no_publication_date(monkeypatch):
    # A frame with only a period column must fall back and say so, not silently
    # present a period cut as a true point-in-time filter.
    df = pd.DataFrame([
        {"report_date": "2026-03-31", "revenue": 1},
        {"report_date": "2026-06-30", "revenue": 2},
    ])
    _install_fake_twmd(monkeypatch, frames={"income-statement": df})
    out = twmd.get_income_statement("2330", curr_date="2026-05-01")

    body = out.split("\n\n", 1)[1]
    assert "2026-03-31" in body
    assert "2026-06-30" not in body
    assert "not a per-row" in out


@pytest.mark.unit
def test_degenerate_publication_column_falls_back_to_period(monkeypatch):
    # All rows share one announcement_date (a bulk-load timestamp, seen on live
    # monthly-revenue). It cannot discriminate rows, so the cut must fall back to
    # the period column and NOT hide older months behind that single load date.
    df = pd.DataFrame([
        {"month": "2023-06", "revenue": 1, "announcement_date": "2026-05-17"},
        {"month": "2026-04", "revenue": 2, "announcement_date": "2026-05-17"},
    ])
    _install_fake_twmd(monkeypatch, frames={"monthly-revenue": df})
    # A 2024 backtest date: with the buggy publication cut this returns nothing;
    # with the period fallback it correctly shows the 2023-06 row.
    out = twmd.get_fundamentals("2330", curr_date="2024-01-01")

    body = out.split("\n\n", 1)[1]
    assert "2023-06" in body
    assert "2026-04" not in body
    assert "period on/before 2024-01-01" in out
    assert "by month" in out


@pytest.mark.unit
def test_no_curr_date_returns_all_rows(monkeypatch):
    _install_fake_twmd(monkeypatch, frames={"monthly-revenue": _revenue_frame()})
    out = twmd.get_fundamentals("2330", curr_date=None)
    body = out.split("\n\n", 1)[1]
    assert "2026-04" in body and "2026-05" in body


@pytest.mark.unit
def test_statement_all_filtered_out_raises_no_data(monkeypatch):
    _install_fake_twmd(monkeypatch, frames={"monthly-revenue": _revenue_frame()})
    # Before any row was announced.
    with pytest.raises(NoMarketDataError):
        twmd.get_fundamentals("2330", curr_date="2020-01-01")


# --- registration wiring ------------------------------------------------------

@pytest.mark.unit
def test_registered_in_vendor_methods():
    from tradingagents.dataflows import interface

    assert "twmd" in interface.VENDOR_LIST
    for method in ("get_stock_data", "get_income_statement",
                   "get_balance_sheet", "get_cashflow", "get_fundamentals"):
        assert "twmd" in interface.VENDOR_METHODS[method], method


@pytest.mark.unit
def test_benchmark_map_has_taiwan():
    from tradingagents.default_config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["benchmark_map"][".TW"] == "^TWII"
    assert DEFAULT_CONFIG["benchmark_map"][".TWO"] == "^TWOII"
