"""CVM filings: what a B3 company had filed by the run's date, and nothing after.

Yahoo tags almost no article with a ``.SA`` symbol, so a B3 run's news analyst
read nothing about the company. The CVM register dates every filing by the day it
was delivered, which serves a run exactly what the market had read by then.
"""

from __future__ import annotations

import copy
import io
import zipfile
from unittest import mock

import pytest

from tradingagents import default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.vendors import cvm

_REAL_DOWNLOAD = cvm._download

_REGISTRY_HEADER = ("CNPJ_Companhia;Data_Referencia;Nome_Empresarial;Codigo_Negociacao;"
                    "Data_Inicio_Negociacao;Data_Fim_Negociacao")
_FILINGS_HEADER = "CNPJ_Companhia;Categoria;Tipo;Assunto;Data_Entrega;Protocolo_Entrega;Versao;Link_Download"

PETROBRAS = "33.000.167/0001-01"
VALE = "33.592.510/0001-54"
OLDCO = "11.111.111/0001-11"
NEWCO = "22.222.222/0001-22"
CSN = "33.042.730/0001-04"

REGISTRY = [
    f"{PETROBRAS};2026-01-01;PETROLEO BRASILEIRO S.A. PETROBRAS;PETR4;2018-05-14;",
    f"{VALE};2026-01-01;VALE S.A.;VALE3;2017-12-22;",
    # One code, two issuers: the first stopped trading, the second took the code over.
    f"{OLDCO};2026-01-01;OLD CO S.A.;REUS3;2010-01-04;2026-03-31",
    f"{NEWCO};2026-01-01;NEW CO S.A.;REUS3;2026-04-01;",
    # Filers leave dates stale: Raízen's RAIZ4 still reads as ending in 2021.
    f"{NEWCO};2026-01-01;NEW CO S.A.;STAL4;2021-08-05;2021-09-10",
    # And fill the code in wrong: CSN entered its CVM code.
    f"{CSN};2026-01-01;CIA SIDERURGICA NACIONAL;4030;1973-07-09;",
]

# B3's search matches names too; only the exact root names the issuer.
B3_SEARCH = {
    "CSNA": [{"issuingCompany": "CSNC", "cnpj": "1", "companyName": "SOME OTHER CSN", "dateListing": "01/01/2000"},
             {"issuingCompany": "CSNA", "cnpj": "33042730000104", "companyName": "CIA SIDERURGICA NACIONAL",
              "dateListing": "22/07/1993"}],
    "CMIN": [{"issuingCompany": "CMIN", "cnpj": "8902291000115", "companyName": "CSN MINERAÇÃO S.A.",
              "dateListing": "12/02/2021"}],
    # The root Embraer freed when it became EMBJ: a registrant that never traded.
    "EMBR": [{"issuingCompany": "EMBR", "cnpj": "4310364000129", "companyName": "EMBRAST INDSTRIA E COMERCIO",
              "dateListing": "31/12/9999"}],
}

FILINGS = [
    f"{PETROBRAS};Fato Relevante;;;2026-10-08;P1;1;https://rad/p1",
    f"{PETROBRAS};Comunicado ao Mercado;;Nova descoberta no Amapá;2026-10-02;P2;1;https://rad/p2",
    # Refiled a week later: the market read it on the first delivery.
    f"{PETROBRAS};Comunicado ao Mercado;;Nova descoberta no Amapá;2026-10-09;P2;2;https://rad/p2v2",
    # Paperwork that outnumbers the news and says little about the price.
    f"{PETROBRAS};Assembleia;AGE;Ata;2026-10-03;P3;1;https://rad/p3",
    f"{VALE};Fato Relevante;;Atualização de projeções||Distribuição de remuneração;2026-10-05;V1;1;https://rad/v1",
]


def _zip(member: str, header: str, rows: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, "\n".join([header, *rows]).encode("latin-1"))
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _no_network_or_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "get_config", lambda: {"data_cache_dir": str(tmp_path), "news_article_limit": 20})
    cvm._filings_index.cache_clear()
    cvm._registry_index.cache_clear()
    fetched = []

    def download(url):
        fetched.append(url)
        if "/FCA/" in url and "2026" in url:
            return _zip("fca_cia_aberta_valor_mobiliario_2026.csv", _REGISTRY_HEADER, REGISTRY)
        if "/IPE/" in url and "2026" in url:
            return _zip("ipe_cia_aberta_2026.csv", _FILINGS_HEADER, FILINGS)
        return None  # a year the portal has no file for

    monkeypatch.setattr(cvm, "_download", download)
    monkeypatch.setattr(cvm, "_b3_search", lambda text: fetched.append(f"b3:{text}") or B3_SEARCH.get(text, []))
    # A fixed "today" after every filing, so each run below is a past one.
    monkeypatch.setattr(cvm, "is_historical", lambda d: d < "2026-10-13")
    return fetched


@pytest.mark.unit
def test_a_listing_resolves_to_its_company_and_a_sibling_class_to_the_same_one():
    assert cvm.company_for("PETR4", "2026-10-10") == (PETROBRAS, "PETROLEO BRASILEIRO S.A. PETROBRAS")
    # Only PETR4 is in the registry; PETR3 is the same company on B3.
    assert cvm.company_for("PETR3", "2026-10-10")[0] == PETROBRAS
    assert cvm.company_for("ZZZZ3", "2026-10-10") is None


@pytest.mark.unit
def test_a_reused_code_resolves_to_the_issuer_trading_it_on_the_date():
    assert cvm.company_for("REUS3", "2026-03-02")[0] == OLDCO
    assert cvm.company_for("REUS3", "2026-10-10")[0] == NEWCO


@pytest.mark.unit
def test_a_stale_trading_end_date_does_not_hide_a_listing():
    assert cvm.company_for("STAL4", "2026-10-10")[0] == NEWCO


@pytest.mark.unit
def test_a_code_the_filer_entered_wrong_resolves_through_b3():
    """CSN's form lists ``4030`` as its trading code, so only B3 knows CSNA3."""
    assert cvm.company_for("CSNA3", "2026-10-10") == (CSN, "CIA SIDERURGICA NACIONAL")
    # B3 reports CNPJs without leading zeros.
    assert cvm.company_for("CMIN3", "2026-10-10")[0] == "08.902.291/0001-15"


@pytest.mark.unit
def test_b3_never_resolves_to_an_issuer_that_was_not_trading():
    # Never listed: a freed root must not point at whoever registered it next.
    assert cvm.company_for("EMBR3", "2026-10-10") is None
    # Listed after the date: B3 lists the present, a past run must not read it.
    assert cvm.company_for("CMIN3", "2020-06-01") is None


@pytest.mark.unit
def test_b3_is_asked_only_when_the_registry_cannot_answer(_no_network_or_cache):
    cvm.company_for("PETR4", "2026-10-10")
    cvm.company_for("PETR3", "2026-10-10")
    assert not any(url.startswith("b3:") for url in _no_network_or_cache)


@pytest.mark.unit
def test_a_b3_answer_is_cached(_no_network_or_cache):
    cvm.company_for("CSNA3", "2026-10-10")
    cvm.company_for("CSNA5", "2026-10-10")
    assert _no_network_or_cache.count("b3:CSNA") == 1


@pytest.mark.unit
def test_an_unresolvable_code_with_b3_down_reads_as_unavailable(monkeypatch):
    def down(text):
        raise VendorUnavailableError("B3 listed companies request failed (ConnectionError)")

    monkeypatch.setattr(cvm, "_b3_search", down)
    with pytest.raises(VendorUnavailableError, match="B3"):
        cvm.get_news_cvm("CSNA3.SA", "2026-10-01", "2026-10-10")


@pytest.mark.unit
def test_a_symbol_off_b3_falls_through_to_the_next_vendor():
    with pytest.raises(NoMarketDataError, match="not a B3 listing"):
        cvm.get_news_cvm("AAPL", "2026-10-01", "2026-10-10")


@pytest.mark.unit
def test_an_unknown_b3_code_is_reported_as_such():
    with pytest.raises(NoMarketDataError, match="no CVM registrant trades as ZZZZ3"):
        cvm.get_news_cvm("ZZZZ3.SA", "2026-10-01", "2026-10-10")


@pytest.mark.unit
def test_news_filings_are_served_and_paperwork_is_not():
    out = cvm.get_news_cvm("PETR4.SA", "2026-10-01", "2026-10-10")
    assert "Material fact (Fato Relevante), delivered 2026-10-08" in out
    assert "Nova descoberta no Amapá" in out
    assert "Ata" not in out and "https://rad/p3" not in out
    # Another company's filing never leaks in.
    assert "projeções" not in out


@pytest.mark.unit
def test_a_filing_on_several_subjects_lists_them_all():
    out = cvm.get_news_cvm("VALE3.SA", "2026-10-01", "2026-10-10")
    assert "Atualização de projeções; Distribuição de remuneração" in out and "||" not in out


@pytest.mark.unit
def test_a_refiled_document_counts_from_its_first_delivery():
    out = cvm.get_news_cvm("PETR4.SA", "2026-10-01", "2026-10-10")
    assert out.count("Nova descoberta no Amapá") == 1
    assert "delivered 2026-10-02" in out and "https://rad/p2v2" not in out


@pytest.mark.unit
def test_a_past_run_does_not_read_filings_from_its_own_last_day():
    """The CVM records the day, not the time: a material fact filed after the
    close of the run's day moves the price the day after, which is scored (#1518)."""
    out = cvm.get_news_cvm("PETR4.SA", "2026-10-01", "2026-10-08")
    assert "delivered 2026-10-08" not in out
    assert "Filings delivered on 2026-10-08 are left out" in out
    assert "delivered 2026-10-02" in out


@pytest.mark.unit
def test_a_run_dated_today_reads_what_is_on_file_now():
    out = cvm.get_news_cvm("PETR4.SA", "2026-10-01", "2026-10-13")
    assert "delivered 2026-10-08" in out
    assert "left out" not in out


@pytest.mark.unit
def test_a_window_with_nothing_filed_is_a_real_absence():
    out = cvm.get_news_cvm("PETR4.SA", "2026-06-01", "2026-06-30")
    assert "No material facts, notices or results were filed in this window" in out


@pytest.mark.unit
def test_a_full_window_keeps_material_facts_before_anything_else(monkeypatch, tmp_path):
    monkeypatch.setattr(cvm, "get_config", lambda: {"data_cache_dir": str(tmp_path), "news_article_limit": 1})
    out = cvm.get_news_cvm("PETR4.SA", "2026-10-01", "2026-10-13")
    assert "Fato Relevante" in out and "Nova descoberta" not in out
    assert "1 lower-priority filings in this window are not shown" in out


@pytest.mark.unit
def test_the_yearly_files_are_fetched_once_and_then_read_from_cache(_no_network_or_cache):
    cvm.get_news_cvm("PETR4.SA", "2026-10-01", "2026-10-10")
    first = len(_no_network_or_cache)
    cvm.get_news_cvm("VALE3.SA", "2026-10-01", "2026-10-10")
    assert len(_no_network_or_cache) == first


@pytest.mark.unit
def test_an_unreachable_portal_reads_as_unavailable_not_as_no_news(monkeypatch):
    import requests

    def fail(url, timeout):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(cvm, "_download", _REAL_DOWNLOAD)
    monkeypatch.setattr(cvm.requests, "get", fail)
    with pytest.raises(VendorUnavailableError, match="CVM open data request failed"):
        cvm.get_news_cvm("PETR4.SA", "2026-10-01", "2026-10-10")


def _route_news(ticker, tool_vendors=None):
    config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    if tool_vendors:
        config["tool_vendors"] = tool_vendors
    set_config(config)
    with mock.patch.dict(router.VENDOR_METHODS["get_news"],
                         {"yfinance": lambda *a, **k: "yahoo news"}):
        return router.route_to_vendor("get_news", ticker, "2026-10-01", "2026-10-10")


@pytest.mark.unit
def test_the_default_config_never_reaches_the_cvm(monkeypatch):
    monkeypatch.setattr(cvm, "_download", lambda url: pytest.fail("the CVM was asked"))
    assert _route_news("PETR4.SA") == "yahoo news"


@pytest.mark.unit
def test_one_chain_serves_b3_from_the_cvm_and_everything_else_from_yahoo():
    chain = {"get_news": "cvm,yfinance"}
    assert "Material fact (Fato Relevante)" in _route_news("PETR4.SA", chain)
    assert _route_news("AAPL", chain) == "yahoo news"
