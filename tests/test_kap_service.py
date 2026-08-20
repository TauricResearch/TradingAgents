from __future__ import annotations

import json
import os
from datetime import datetime

import httpx
import pytest
from kap_client import (
    Attachment,
    Company,
    CompanyNotFoundError,
    Disclosure,
    KapError,
    RateLimitError,
)

from tradingagents.dataflows.kap import KapService, normalize_bist_ticker_for_kap


@pytest.mark.parametrize(
    ("yahoo_ticker", "kap_ticker"),
    [("THYAO.IS", "THYAO"), ("asels.is", "ASELS"), (" TUPRS.IS ", "TUPRS")],
)
def test_normalize_bist_ticker_for_kap(yahoo_ticker, kap_ticker):
    assert normalize_bist_ticker_for_kap(yahoo_ticker) == kap_ticker


@pytest.mark.parametrize("ticker", ["THYAO", "AAPL", "FAKE.IS.EXTRA", ".IS", "IS.ISLAND"])
def test_normalizer_rejects_non_bist_or_malformed_symbols(ticker):
    with pytest.raises(ValueError, match="not a BIST"):
        normalize_bist_ticker_for_kap(ticker)


def _disclosure(index=1, subject="Yeni İş İlişkisi", summary="Yeni sözleşme imzalandı"):
    return Disclosure(
        index=index,
        publish_datetime=datetime(2026, 8, 20, 12, 30),
        company_name="TÜRK HAVA YOLLARI A.O.",
        fund_code="",
        stock_codes="THYAO",
        subject=subject,
        summary=summary,
        disclosure_type="DG",
        has_attachment=True,
        is_late=False,
        is_corrective=False,
        is_english=False,
        url=f"https://www.kap.org.tr/tr/Bildirim/{index}",
    )


class FakeKap:
    failure: Exception | None = None
    disclosures = [_disclosure()]

    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def find_company(self, ticker):
        if self.failure:
            raise self.failure
        assert ticker == "THYAO"
        return Company(oid="a" * 32, name="TÜRK HAVA YOLLARI A.O.", ticker=ticker)

    def fetch_disclosures(self, oid, start_date, end_date):
        assert oid == "a" * 32
        assert (start_date, end_date) == ("2026-07-21", "2026-08-20")
        return list(self.disclosures)

    def fetch_attachments(self, disclosure_index):
        assert disclosure_index == 1
        return [Attachment(filename="rapor.pdf", url="https://kap.example/rapor.pdf")]


def test_kap_company_lookup_and_disclosure_parsing():
    result = KapService(timeout=7, client_factory=FakeKap).get_disclosures(
        "THYAO.IS", end_date="2026-08-20"
    )

    assert result.status == "ok"
    assert result.kap_ticker == "THYAO"
    assert result.total_found == 1
    disclosure = result.disclosures[0]
    assert disclosure.company == "TÜRK HAVA YOLLARI A.O."
    assert disclosure.disclosure_id == 1
    assert disclosure.has_attachment is True
    assert disclosure.attachments[0].filename == "rapor.pdf"
    payload = json.loads(result.to_json())
    assert payload["disclosures"][0]["published_at"] == "2026-08-20T12:30"


def test_kap_company_lookup_uses_current_registry_fallback():
    class LegacyRegistryKap(FakeKap):
        def find_company(self, ticker):
            raise CompanyNotFoundError(ticker)

    result = KapService(
        client_factory=LegacyRegistryKap,
        company_resolver=lambda ticker: "a" * 32,
    ).get_disclosures("THYAO.IS", end_date="2026-08-20")
    assert result.status == "ok"


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (CompanyNotFoundError("THYAO"), "company_not_found", "bulunamadı"),
        (RateLimitError(12), "rate_limited", "limiti"),
        (httpx.ReadTimeout("slow"), "timeout", "zaman aşımına"),
        (KapError("down"), "unavailable", "geçici olarak alınamadı"),
    ],
)
def test_kap_api_errors_return_fail_safe_result(error, status, message):
    class FailingKap(FakeKap):
        failure = error

    resolver = (lambda ticker: None) if isinstance(error, CompanyNotFoundError) else None
    result = KapService(client_factory=FailingKap, company_resolver=resolver).get_disclosures(
        "THYAO.IS", end_date="2026-08-20"
    )
    assert result.status == status
    assert message in result.message
    assert result.disclosures == ()


def test_non_bist_does_not_call_kap_client():
    def should_not_construct(**kwargs):
        raise AssertionError("KAP client must not run for foreign symbols")

    result = KapService(client_factory=should_not_construct).get_disclosures(
        "AAPL", end_date="2026-08-20"
    )
    assert result.status == "not_bist"


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("TRADINGAGENTS_RUN_KAP_INTEGRATION") != "1",
    reason="set TRADINGAGENTS_RUN_KAP_INTEGRATION=1 for live KAP calls",
)
@pytest.mark.parametrize("ticker", ["THYAO.IS", "ASELS.IS", "TUPRS.IS"])
def test_live_kap_company_resolution(ticker):
    result = KapService(timeout=30).get_disclosures(
        ticker, end_date="2026-08-20", max_disclosures=1, include_attachments=False
    )
    assert result.status == "ok", result.message
