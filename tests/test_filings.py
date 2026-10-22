"""Offline SEC metadata/XBRL tests: source timestamps and no invented filings."""
from datetime import date, datetime, timezone
import pytest
from tradingagents.paper import filings

def test_no_identifying_user_agent_means_zero_network_requests(monkeypatch):
    monkeypatch.delenv("KORAL_SEC_USER_AGENT",raising=False)
    monkeypatch.setattr(filings,"urlopen",
        lambda *a,**kw: (_ for _ in ()).throw(AssertionError("unexpected HTTP")))
    result=filings.SecEvidence().collect("ERO")
    assert result["status"]=="NOT_CONFIGURED"
    assert result["financial_facts"]=={}

def test_dated_6k_links_and_path_sanitisation():
    raw={"filings":{"recent":{
      "form":["6-K","10-Q","8-K","10-K"],
      "accessionNumber":["0001628280-26-053508","0001628280-26-053509",
                         "../../bad","0001628280-26-000002"],
      "filingDate":["2026-08-05","2026-11-02","2026-10-01","2025-04-01"],
      "primaryDocument":["release.htm","quarter.htm","../../../bad.htm","form.htm"]}}}
    out=filings.parse_filings(1853860,raw,asof=date(2026,10,22))
    assert len(out)==2
    assert out[0]["form"]=="6-K"
    assert "https://www.sec.gov/Archives/edgar/data/1853860/" in out[0]["url"]
    assert "2026-11-02" not in str(out)

def test_xbrl_facts_are_explicitly_filing_dated_not_auto_ttm():
    raw={"facts":{"us-gaap":{"CashAndCashEquivalentsAtCarryingValue":{"units":{"USD":[
      {"form":"10-Q","filed":"2026-08-05","end":"2026-06-30","val":101700000},
      {"form":"10-Q","filed":"2026-11-02","end":"2026-09-30","val":200000000}
    ]}}}}}
    out=filings.parse_facts(raw,asof=date(2026,10,22))
    assert out["filed_cash_usd"]["value_usd"]==101700000
    assert out["filed_cash_usd"]["period_end"]=="2026-06-30"
    assert "TTM" in out["filed_cash_usd"]["limitation"]

def test_unresolved_cik_returns_a_missing_evidence_state():
    reader=filings.SecEvidence("KoralEquities Research contact@example.org")
    reader._tickers={"ERO":1853860}
    assert reader.lookup("../ERO") is None
    result=reader.collect("MISSING",now=datetime(2026,10,22,tzinfo=timezone.utc))
    assert result["status"]=="CIK_UNRESOLVED"

def test_sec_filing_metadata_does_not_claim_financial_reconciliation(monkeypatch):
    reader=filings.SecEvidence("KoralEquities Research contact@example.org")
    reader._tickers={"ERO":1853860}
    def load(url):
        if "/submissions/" in url:
            return {"name":"Ero Copper Corp.","filings":{"recent":{
             "form":["6-K"],"accessionNumber":["0001628280-26-053508"],
             "filingDate":["2026-08-05"],"primaryDocument":["release.htm"]}}}
        return {"facts":{}}
    monkeypatch.setattr(reader,"_get",load)
    record=reader.collect("ERO",now=datetime(2026,10,22,tzinfo=timezone.utc))
    assert record["status"]=="AVAILABLE"
    assert record["filings"][0]["form"]=="6-K"
    assert record["financial_facts"]=={}
    assert "NOT verify all vendor" in record["limitation"]
