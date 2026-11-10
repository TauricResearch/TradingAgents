"""Brønnøysund Register Centre (Enhetsregisteret): who runs a Norwegian company.

The open API at data.brreg.no needs no key. It serves the register as it stands
today, with no history, so the roles returned are the current ones whatever the
analysis date: fine for a live run, not point-in-time for a backtest.
"""

from __future__ import annotations

import requests

from tradingagents.dataflows.errors import VendorUnavailableError

API = "https://data.brreg.no/enhetsregisteret/api"
TIMEOUT = 15.0
# Company forms a listed Norwegian company can have, most likely first.
_LISTED_FORMS = ("ASA", "AS", "SE")


def _get(path: str, params: dict | None = None) -> dict | None:
    """One register request; ``None`` when the register has no such entry."""
    try:
        response = requests.get(
            f"{API}{path}", params=params, timeout=TIMEOUT,
            headers={"Accept": "application/json"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise VendorUnavailableError(f"Brønnøysund register request failed: {exc}") from exc


def find_companies(name: str, size: int = 10) -> list[dict]:
    """Register entries whose name matches ``name``, best candidate first."""
    data = _get("/enheter", {"navn": name, "size": size}) or {}
    companies = (data.get("_embedded") or {}).get("enheter") or []
    wanted = name.strip().casefold()

    def rank(company: dict) -> tuple:
        form = (company.get("organisasjonsform") or {}).get("kode", "")
        return (
            (company.get("navn") or "").casefold() != wanted,
            _LISTED_FORMS.index(form) if form in _LISTED_FORMS else len(_LISTED_FORMS),
        )

    return sorted(companies, key=rank)


def _person_name(person: dict) -> str:
    name = person.get("navn") or {}
    parts = (name.get("fornavn"), name.get("mellomnavn"), name.get("etternavn"))
    return " ".join(p for p in parts if p)


def _holder(role: dict) -> str:
    """Who holds a role: a person, or a company such as the auditor."""
    if role.get("person"):
        return _person_name(role["person"])
    unit = role.get("enhet") or {}
    names = unit.get("navn") or []
    label = " ".join(names) if isinstance(names, list) else str(names)
    number = unit.get("organisasjonsnummer")
    return f"{label} (org.nr {number})" if number else label


def _describe(company: dict) -> list[str]:
    form = company.get("organisasjonsform") or {}
    industry = company.get("naeringskode1") or {}
    address = company.get("forretningsadresse") or {}
    lines = [
        f"Name: {company.get('navn', 'unknown')}",
        f"Organisation number: {company.get('organisasjonsnummer', 'unknown')}",
        f"Company form: {form.get('kode', '?')} ({form.get('beskrivelse', 'unknown')})",
    ]
    if company.get("stiftelsesdato"):
        lines.append(f"Founded: {company['stiftelsesdato']}")
    if industry.get("beskrivelse"):
        lines.append(f"Industry: {industry['beskrivelse']}")
    if address.get("kommune"):
        lines.append(f"Registered in: {address['kommune']}")
    if company.get("antallAnsatte") is not None:
        lines.append(f"Registered employees: {company['antallAnsatte']}")
    flags = [label for key, label in (
        ("konkurs", "BANKRUPT"),
        ("underAvvikling", "UNDER LIQUIDATION"),
        ("underTvangsavviklingEllerTvangsopplosning", "UNDER FORCED LIQUIDATION"),
    ) if company.get(key)]
    if flags:
        lines.append("Status flags: " + ", ".join(flags))
    return lines


def get_company_officers(company_name: str) -> str:
    """The board, CEO and auditor of a Norwegian company, as registered today."""
    company_name = (company_name or "").strip()
    if not company_name:
        return "No company name given; pass the company's legal name, e.g. 'Kitron ASA'."

    candidates = find_companies(company_name)
    if not candidates:
        return (
            f"No company named '{company_name}' in the Brønnøysund register. It only covers"
            " companies registered in Norway; a foreign-registered company listed in Oslo"
            " will not be found."
        )

    company = candidates[0]
    number = company.get("organisasjonsnummer")
    lines = [f"# Brønnøysund register: officers of {company.get('navn', company_name)}",
             "Current registrations only; the register keeps no role history.", ""]
    lines += _describe(company)

    roles = _get(f"/enheter/{number}/roller") or {}
    groups = roles.get("rollegrupper") or []
    if not groups:
        lines += ["", "No roles are registered for this company."]
    for group in groups:
        title = (group.get("type") or {}).get("beskrivelse", "Roles")
        changed = group.get("sistEndret")
        lines += ["", f"## {title}" + (f" (last changed {changed})" if changed else "")]
        for role in group.get("roller") or []:
            label = (role.get("type") or {}).get("beskrivelse", "Role")
            resigned = " (resigned)" if role.get("fratraadt") else ""
            lines.append(f"- {label}: {_holder(role) or 'unnamed'}{resigned}")

    others = [c for c in candidates[1:6] if c.get("navn")]
    if others:
        lines += ["", "Other register entries with a similar name, in case the wrong one was picked:"]
        lines += [f"- {c['navn']} (org.nr {c.get('organisasjonsnummer', '?')})" for c in others]
    return "\n".join(lines)
