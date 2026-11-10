"""Brønnøysund register vendor: picking the company, formatting its officers,
and failing as a vendor outage rather than a crash.

All API access is mocked, so these run without a network connection.
"""
from unittest import mock

import pytest
import requests

from tradingagents.agents import tools
from tradingagents.agents.analysts import fundamentals_analyst
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import brreg

_SEARCH = {
    "_embedded": {
        "enheter": [
            {"organisasjonsnummer": "111111111", "navn": "KITRON HOLDING AS",
             "organisasjonsform": {"kode": "AS", "beskrivelse": "Aksjeselskap"}},
            {"organisasjonsnummer": "222222222", "navn": "KITRON ASA",
             "organisasjonsform": {"kode": "ASA", "beskrivelse": "Allmennaksjeselskap"},
             "stiftelsesdato": "1996-01-01", "antallAnsatte": 12,
             "naeringskode1": {"beskrivelse": "Produksjon av elektronikk"},
             "forretningsadresse": {"kommune": "ASKER"}},
        ]
    }
}
_ROLES = {
    "rollegrupper": [
        {"type": {"kode": "DAGL", "beskrivelse": "Daglig leder"}, "sistEndret": "2024-05-01",
         "roller": [{"type": {"beskrivelse": "Daglig leder"}, "fratraadt": False,
                     "person": {"navn": {"fornavn": "Kari", "etternavn": "Nordmann"}}}]},
        {"type": {"kode": "STYR", "beskrivelse": "Styre"},
         "roller": [
             {"type": {"beskrivelse": "Styrets leder"}, "fratraadt": False,
              "person": {"navn": {"fornavn": "Ola", "mellomnavn": "B", "etternavn": "Hansen"}}},
             {"type": {"beskrivelse": "Styremedlem"}, "fratraadt": True,
              "person": {"navn": {"fornavn": "Per", "etternavn": "Olsen"}}},
         ]},
        {"type": {"kode": "REVI", "beskrivelse": "Revisor"},
         "roller": [{"type": {"beskrivelse": "Revisor"}, "fratraadt": False,
                     "enhet": {"organisasjonsnummer": "333333333", "navn": ["REVISJON AS"]}}]},
    ]
}


def _response(payload, status=200):
    response = mock.Mock(status_code=status)
    response.json.return_value = payload
    response.raise_for_status.side_effect = (
        requests.HTTPError(f"{status}") if status >= 400 else None
    )
    return response


def _api(search=_SEARCH, roles=_ROLES):
    def get(url, **kwargs):
        return _response(roles if url.endswith("/roller") else search)
    return mock.patch.object(brreg.requests, "get", side_effect=get)


@pytest.mark.unit
def test_the_exact_name_wins_over_the_first_hit():
    with _api() as get:
        report = brreg.get_company_officers("Kitron ASA")
    assert "Organisation number: 222222222" in report
    assert get.call_args_list[-1].args[0].endswith("/enheter/222222222/roller")
    # The entry not picked is listed so a wrong pick is visible.
    assert "KITRON HOLDING AS (org.nr 111111111)" in report


@pytest.mark.unit
def test_officers_are_listed_by_role_group():
    with _api():
        report = brreg.get_company_officers("Kitron ASA")
    assert "## Daglig leder (last changed 2024-05-01)" in report
    assert "- Daglig leder: Kari Nordmann" in report
    assert "- Styrets leder: Ola B Hansen" in report
    assert "- Styremedlem: Per Olsen (resigned)" in report
    assert "- Revisor: REVISJON AS (org.nr 333333333)" in report
    assert "Founded: 1996-01-01" in report


@pytest.mark.unit
def test_a_bankruptcy_flag_is_reported():
    search = {"_embedded": {"enheter": [{"organisasjonsnummer": "1", "navn": "X ASA", "konkurs": True}]}}
    with _api(search=search):
        assert "Status flags: BANKRUPT" in brreg.get_company_officers("X ASA")


@pytest.mark.unit
def test_an_unknown_company_says_so_without_asking_for_roles():
    with _api(search={"page": {"totalElements": 0}}) as get:
        report = brreg.get_company_officers("Nope ASA")
    assert "No company named 'Nope ASA'" in report
    assert get.call_count == 1


@pytest.mark.unit
def test_a_blank_name_makes_no_request():
    with _api() as get:
        assert "No company name given" in brreg.get_company_officers("  ")
    get.assert_not_called()


@pytest.mark.unit
def test_a_failed_request_is_a_vendor_outage():
    with mock.patch.object(brreg.requests, "get", side_effect=requests.ConnectionError("down")), \
            pytest.raises(VendorUnavailableError):
        brreg.get_company_officers("Kitron ASA")


@pytest.mark.unit
def test_the_tool_reports_an_outage_instead_of_raising():
    with mock.patch.object(brreg.requests, "get", side_effect=requests.ConnectionError("down")):
        out = tools.get_company_officers.invoke({"company_name": "Kitron ASA"})
    assert out.startswith("DATA_UNAVAILABLE")


@pytest.mark.unit
def test_the_fundamentals_analyst_is_offered_the_tool():
    assert tools.get_company_officers in fundamentals_analyst.TOOLS
