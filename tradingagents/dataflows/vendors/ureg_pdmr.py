"""Keyless PDMR (insider trading) vendor for German equities.

Source: the public capital-market-information search of the German
Unternehmensregister (unternehmensregister.de) — the official register every
German issuer must disclose Art. 19 MAR (PDMR) notifications in. No API key,
no browser: the search result page is server-rendered (Next.js RSC payload
embedded in the HTML) and each record's full disclosure is a stateless
``GET /api/pub-html?payload=...`` fetch (verified 2026-10-12).

Per-emitter disambiguation ("Fall-Unterscheidung"): the register's name
search is fuzzy — "Siemens AG" surfaces *Siemens Energy AG* (a subsidiary),
"Volkswagen AG" surfaces *Volkswagen Financial Services AG* alongside the
parent, and "BMW" matches nothing. This vendor therefore never trusts the
fuzzy match: it (a) resolves the ticker to a configured identity in the
issuer registry (``ureg_query_name`` for the search, ``ureg_entity_name`` as
the validation target) and (b) keeps only publication rows whose
``companyNameAtTimeOfPublication`` normalizes to that exact entity. Rows of
a matched-but-wrong company are dropped, not mislabeled.

Self-selection: a ticker that is not a configured German-equity registry
entry is *not covered by this vendor* and raises ``VendorNotConfiguredError``
so the router continues down the chain (finnhub, yfinance, ...). A configured
ticker that genuinely has no PDMR disclosure in the window returns an
honest, source-scoped "none" string (terminal for the chain, like
issuer_rss).
"""
from __future__ import annotations

import base64
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)

UReg_BASE = "https://www.unternehmensregister.de"
# Art. 19 MAR PDMR rows carry publicationCategory.id 80 inside the
# "Kapitalmarktinformationen" section (drilldownFilter=21), which also holds
# other categories (83, 81, 79) — the category filter below is what makes the
# disambiguation per disclosure *type*, not only per issuer.
PDMR_CATEGORY_ID = 80
DRILLDOWN_FILTER = "21"
PAGE_SIZE = 30
REQUEST_TIMEOUT = 40
MAX_RECORDS = 40          # cap on records returned per call
MAX_DETAIL_FETCHES = 25   # cap on /api/pub-html fetches per call
# UReg search order is not strictly by date; walk enough pages to cover the
# window even when a PDMR row sits deep in a busy issuer's list (verified:
# Mercedes-Benz's PDMR rows appear past page 2).
MAX_PAGES = 6

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/155.0.0.0 Safari/537.36"
)


def _norm_name(value: str | None) -> str:
    """Umlaut-fold + casefold + whitespace-collapsed name key.

    UReg mixes cases per issuer ("SAP SE", "DEUTSCHE BANK AKTIENGESELLSCHAFT",
    "VOLKSWAGEN AKTIENGESELLSCHAFT"), so exact matching would drop valid
    rows; compare on this normalized key instead. ß is folded to "ss" *before*
    the ASCII step (NFKD gives ß no ASCII decomposition and it would be
    dropped). Umlauts fold to their plain vowels (ü→u, not ue) — the registry
    carries the exact official UReg name, so both sides of the comparison use
    the same spelling and the fold only has to absorb case/punctuation
    differences, not mixed umlaut/ue spellings.
    """
    if not value:
        return ""
    s = value.replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\s\-]+", " ", s).strip().casefold()


def _to_iso_date(value: str | None) -> str | None:
    """Normalize a date to ISO (YYYY-MM-DD). UReg mixes formats: list rows
    and the search index use ISO, the /api/pub-html detail uses DD.MM.YYYY.
    The point-in-time filter compares ISO strings, so every date we surface or
    filter on must pass through here.
    """
    if not value:
        return None
    value = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", value)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return value


def _load_instrument(ticker: str) -> dict:
    """Resolve the ticker to its configured UReg identity from the issuer
    registry (same file/pattern as issuer_rss)."""
    path = Path(
        get_config().get("issuer_registry_path", "~/.tradingagents/german_equities.json")
    ).expanduser()
    if not path.is_file():
        raise VendorNotConfiguredError(f"issuer registry not found: {path}")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise VendorNotConfiguredError(f"issuer registry unreadable: {path}")
    instruments = registry.get("instruments", {}) if isinstance(registry, dict) else {}
    if not isinstance(instruments, dict):
        raise VendorNotConfiguredError("issuer registry 'instruments' must be a JSON object")
    wanted = ticker.strip().upper()
    for key, record in instruments.items():
        if not isinstance(record, dict):
            continue
        aliases = record.get("aliases", [])
        candidates = [
            key,
            record.get("ticker"),
            record.get("isin"),
            record.get("wkn"),
            record.get("yahoo_symbol"),
            record.get("alpha_vantage_symbol"),
            *(aliases if isinstance(aliases, list) else []),
        ]
        if any(str(c).strip().upper() == wanted for c in candidates if c):
            query_name = record.get("ureg_query_name")
            entity_name = record.get("ureg_entity_name")
            if not query_name or not entity_name:
                raise VendorNotConfiguredError(
                    f"{key} has no UReg identity configured "
                    "(missing ureg_query_name/ureg_entity_name)"
                )
            return {**record, "ticker": key}
    raise VendorNotConfiguredError(
        f"{ticker} is not a configured German-equity PDMR identity — this "
        f"vendor only serves registry-listed issuers"
    )


# ---------------------------------------------------------------------------
# Search-result page parsing (RSC payload embedded in the SSR HTML)
# ---------------------------------------------------------------------------

def _extract_dtoArray(record_text: str):
    """Extract the ``elasticSearchDtos`` array from a decoded RSC chunk.

    String-aware bracket matching: ``publicationText`` can contain ``[``/``]``
    characters that break naive counting.
    """
    i = record_text.find('"elasticSearchDtos"')
    if i < 0:
        return None
    start = record_text.find("[", i)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for j in range(start, len(record_text)):
        ch = record_text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(record_text[start:j + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def _iter_rsc_records(html: str):
    """Yield decoded RSC record strings from ``self.__next_f.push`` chunks.

    ``json.loads('"chunk"')`` is the correct decode for a JS string literal:
    it handles ``\\uXXXX`` escapes and keeps multibyte UTF-8 (the
    unicode_escape route mangles umlauts — "Münchener" would become
    "MÃ¼nchener" and break exact name matching).
    """
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', html):
        try:
            decoded = json.loads('"' + chunk + '"')
        except json.JSONDecodeError:
            continue
        if "elasticSearchDtos" in decoded:
            yield decoded


def _extract_publication_rows(html: str) -> list[dict]:
    """Return every capital-market publication row (any category) with
    list-level fields, including the category id.

    The category is kept (not filtered) so the caller can both (a) detect
    list exhaustion on non-PDMR pages and (b) filter to PDMR afterwards.
    UReg mixes categories per page (Infineon's PDMR rows start on page 2),
    so a PDMR-only extraction would wrongly signal "no more pages".
    """
    rows = []
    for record in _iter_rsc_records(html):
        dtos = _extract_dtoArray(record)
        if not dtos:
            continue
        for dto in dtos:
            if dto.get("entityType") == "1-company":
                continue  # company card, not a publication
            pub = dto.get("publicationDto") or {}
            payload = pub.get("encryptedPayload") or dto.get("encryptedPayload")
            if not payload:
                continue
            rows.append({
                "disclosure_date": _to_iso_date(pub.get("sourceDate")),
                "company": pub.get("companyNameAtTimeOfPublication"),
                "language": pub.get("language"),
                "payload": payload,
                "category": (pub.get("publicationCategory") or {}).get("id"),
                "title": (pub.get("title") or "")[:120],
            })
    return rows


def _extract_pdmr_rows(html: str) -> list[dict]:
    """Return PDMR rows (category 80) with list-level fields.

    Each row: sourceDate (disclosure date, verified == detail's
    "Pflichtveröffentlichung am"), companyNameAtTimeOfPublication (the
    per-emitter validation key), encryptedPayload (the /api/pub-html
    accessor), language.
    """
    return [r for r in _extract_publication_rows(html)
            if r["category"] == PDMR_CATEGORY_ID]


# ---------------------------------------------------------------------------
# Detail parsing (/api/pub-html)
# ---------------------------------------------------------------------------

def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&nbsp;", " ").replace("&amp;", "&")
    value = value.replace("&#8211;", "–").replace("&quot;", '"')
    value = value.replace("’", "'").replace("‘", "'").replace("„", '"').replace("“", '"')
    return re.sub(r"\s+", " ", value).strip()


# Canonical field -> set of normalized (umaut-folded, casefolded) labels that
# map to it. The register serves PDMR in German *and* English, so both label
# spellings are listed. Matching on normalized labels (not positions) means a
# reordered or partially-filled disclosure never misattributes a field.
_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "person":           ("name",),  # the FIRST Name row is the person
    "position":         ("a) position/status",),
    "notification_type": ("b) erstmeldung/berichtigung", "b) initial notification/ amendment"),
    "lei":              ("lei",),
    "instrument_type":  ("art des instruments", "type of instrument"),
    "isin":             ("kennung", "identification code"),
    "transaction_type": ("b) art des geschafts", "b) nature of the transaction"),
    "transaction_date": ("e) datum des geschafts", "e) date of the transaction"),
    "location":         ("f) ort des geschafts", "f) place of the transaction"),
    "disclosure_date":  ("pflichtveroffentlichung am", "obligatory publication on"),
    "disclosed_via":    ("pflichtveroffentlichung in/uber", "obligatory publication in/about"),
}
_LABEL_TO_FIELD = {lab: field for field, labs in _FIELD_LABELS.items() for lab in labs}


def parse_pub_html(html: str) -> dict:
    """Parse the /api/pub-html PDMR detail into flat fields, language-robust.

    The detail is a table of ``<P><b>Label:</b></P>`` / ``<P>value</P>`` pairs
    plus a price/volume table. The register emits the same structure in German
    and English (chosen per filing), so labels are matched on a normalized
    cross-language map rather than positions.
    """
    fields: dict[str, str] = {}
    seen_person = False

    for m in re.finditer(
        r"<P>\s*<b>([^<]+):</b>\s*</P>\s*</TD>\s*<TD[^>]*>\s*<P>(.*?)</P>", html, re.S
    ):
        raw_label, raw_value = m.group(1), m.group(2)
        value = _clean(raw_value)
        if not value:
            continue
        key = _norm_name(raw_label)
        field = _LABEL_TO_FIELD.get(key)
        if field == "person":
            # only the first Name row is the person; the issuer's Name is
            # resolved separately under its section heading.
            if not seen_person:
                fields.setdefault("person", value)
                seen_person = True
        elif field:
            fields.setdefault(field, value)

    # Price/volume: the "c)" table (DE "c) Preis(e) und Volumen", EN
    # "c) Price(s) and volume(s)"), whose first body row is price, volume.
    pm = re.search(
        r"<P>\s*<b>c\)\s*(?:Preis|Price)[^<]*</b>\s*</P>\s*<TABLE.*?<TBODY>(.*?)</TBODY>",
        html, re.S)
    if pm:
        cells = re.findall(r"<TD[^>]*>\s*<P>(.*?)</P>\s*</TD>", pm.group(1), re.S)
        if len(cells) >= 2:
            fields.setdefault("price", _clean(cells[0]))
            fields.setdefault("volume", _clean(cells[1]))

    return {
        "person": fields.get("person"),
        "position": fields.get("position"),
        "notification_type": fields.get("notification_type"),
        "emittent": None,  # resolved under the issuer heading in fetch_detail
        "lei": fields.get("lei"),
        "instrument_type": fields.get("instrument_type"),
        "isin": fields.get("isin"),
        "transaction_type": fields.get("transaction_type"),
        "price": fields.get("price"),
        "volume": fields.get("volume"),
        "transaction_date": fields.get("transaction_date"),
        "location": fields.get("location"),
        "disclosure_date": fields.get("disclosure_date"),
        "disclosed_via": fields.get("disclosed_via"),
    }


def _emittent_from_html(html: str) -> str | None:
    """The issuer's Name row sits under its section heading — DE "Angaben zum
    Emittenten", EN "Details of issuer" — distinct from the person's Name row."""
    m = re.search(
        r"(?:Angaben zum Emittenten|Details of issuer).*?"
        r"<P>\s*<b>Name:</b>\s*</P>\s*</TD>\s*<TD[^>]*>\s*<P>(.*?)</P>",
        html, re.S)
    return _clean(m.group(1)) if m else None


def fetch_detail(payload: str) -> dict:
    """Fetch one PDMR detail. Stateless (verified: 200 from a bare session)."""
    try:
        resp = requests.get(
            f"{UReg_BASE}/api/pub-html",
            params={"payload": payload},
            headers={"User-Agent": _USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"UReg detail fetch failed: {exc}") from None
    fields = parse_pub_html(resp.text)
    fields["emittent"] = _emittent_from_html(resp.text) or fields.get("emittent")
    return fields


# ---------------------------------------------------------------------------
# Search session
# ---------------------------------------------------------------------------

def _open_search(query_name: str) -> requests.Session:
    """Warm session + one-time search token (verified flow)."""
    s = requests.Session()
    s.headers.update({"User-Agent": _USER_AGENT, "Accept-Language": "de,en;q=0.8"})
    try:
        s.get(f"{UReg_BASE}/de", timeout=REQUEST_TIMEOUT)
        s.get(f"{UReg_BASE}/de/suche/kapitalmarktinformationen", timeout=REQUEST_TIMEOUT)
        token_resp = s.get(f"{UReg_BASE}/api/search-token", timeout=REQUEST_TIMEOUT)
        token_resp.raise_for_status()
        token = token_resp.json()["token"]
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"UReg search session failed: {exc}") from None
    except (ValueError, KeyError) as exc:
        raise VendorUnavailableError(f"UReg search-token response invalid: {exc}") from None
    inner = (
        f"companyName={query_name}&drilldownFilter={DRILLDOWN_FILTER}"
        f"&companyFederalState=&searchToken={token}&formType=CAPITAL_MARKET"
    )
    s.cookies.set("SEARCH_PARAMS", base64.b64encode(inner.encode()).decode())
    s.ureg_token = token  # the raw search token for the URL query string
    return s


def _fetch_page(s: requests.Session, query_name: str, page: int) -> list[dict]:
    url = (
        f"{UReg_BASE}/de/suche?companyName={quote(query_name)}"
        f"&drilldownFilter={DRILLDOWN_FILTER}&companyFederalState="
        f"&searchToken={s.ureg_token}"
        f"&from={(page - 1) * PAGE_SIZE}&size={PAGE_SIZE}"
    )
    try:
        body = s.get(url, timeout=REQUEST_TIMEOUT).text
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"UReg search request failed: {exc}") from None
    return _extract_publication_rows(body)


def _search(query_name: str) -> list[dict]:
    s = _open_search(query_name)
    pdmr: list[dict] = []
    seen: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        page_rows = _fetch_page(s, query_name, page)
        # list exhaustion: no new publication rows of *any* category. UReg
        # mixes categories per page, so a page full of cat-81/83 rows is not
        # the end of the PDMR list (Infineon's PDMR rows start on page 2).
        fresh = [r for r in page_rows if r["payload"] not in seen]
        if not fresh:
            break
        for r in fresh:
            seen.add(r["payload"])
            if r["category"] == PDMR_CATEGORY_ID:
                pdmr.append(r)
        if len(pdmr) >= MAX_RECORDS:
            break
    return pdmr[:MAX_RECORDS]


# ---------------------------------------------------------------------------
# Vendor entry point
# ---------------------------------------------------------------------------

def get_ureg_pdmr_insider_transactions(ticker: str, as_of_date: str | None = None) -> str:
    """German PDMR (Art. 19 MAR) insider disclosures for a registry-listed
    issuer, with point-in-time filtering on the disclosure date."""
    instrument = _load_instrument(ticker)
    query_name: str = instrument["ureg_query_name"]
    entity_name: str = instrument["ureg_entity_name"]
    entity_key = _norm_name(entity_name)

    rows = _search(query_name)

    # Per-emitter validation: keep only rows of the configured entity.
    # Rows of a fuzzy-matched-but-wrong company (subsidiary, affiliate, or a
    # second matched company) are dropped — never mislabeled.
    mine = [r for r in rows if _norm_name(r["company"]) == entity_key]
    dropped = len(rows) - len(mine)

    as_of = None
    if as_of_date:
        try:
            from datetime import date
            as_of = date.fromisoformat(as_of_date)
        except ValueError:
            as_of = None

    if as_of:
        window = [
            r for r in mine
            if r["disclosure_date"] and r["disclosure_date"] <= as_of.isoformat()
        ]
    else:
        window = mine

    if not window:
        if mine:
            # configured emitter, real (coverage-verified) absence in window
            newest = max((r["disclosure_date"] or "") for r in mine)
            note = f"latest PDMR disclosure in source: {newest}"
        else:
            note = f"no PDMR rows of {entity_name!r} in the register's result set"
        if dropped:
            note += f"; {dropped} row(s) of other matched companies excluded by entity validation"
        return (
            f"# PDMR insider disclosures (Art. 19 MAR) for {instrument['ticker']} "
            f"({entity_name})\n"
            f"# Source: Unternehmensregister (unternehmensregister.de), keyless public "
            f"capital-market search, category 'Eigengeschäfte von Führungskräften'.\n"
            f"# Result: no PDMR disclosures"
            + (f" on or before {as_of.isoformat()}" if as_of else "")
            + f". {note}. This is an absence in this source only — it does not "
            f"prove no insider transactions occurred. Do not infer a neutral "
            f"insider sentiment from it."
        )

    # Details: fetch /api/pub-html for each in-window row (capped).
    details = []
    for row in window[:MAX_DETAIL_FETCHES]:
        d = fetch_detail(row["payload"])
        # second-gate the detail on the emitter too (defense in depth)
        d["emittent_ok"] = (
            _norm_name(d.get("emittent")) == entity_key if d.get("emittent") else None
        )
        # detail dates are DD.MM.YYYY — normalize to ISO for consistent output
        # and so the row's ISO date stays the point-in-time anchor.
        d["disclosure_date"] = _to_iso_date(row["disclosure_date"]) or _to_iso_date(d.get("disclosure_date"))
        d["transaction_date"] = _to_iso_date(d.get("transaction_date"))
        details.append(d)

    lines = [
        f"# PDMR insider disclosures (Art. 19 MAR) for {instrument['ticker']} "
        f"({entity_name})",
        "# Source: Unternehmensregister (unternehmensregister.de) — official German "
        "register, keyless public search; per-emitter entity-validated (fuzzy "
        "name matches of other companies excluded).",
        "# disclosure_date is the publication date (Pflichtveröffentlichung am); "
        "filtered point-in-time when an as-of date is given.",
    ]
    if dropped:
        lines.append(f"# {dropped} row(s) of other matched companies excluded by entity validation.")
    if as_of:
        lines.append(f"filtered to disclosures on or before {as_of.isoformat()} (point-in-time)")
    for d in details:
        person = d.get("person") or "(unknown person)"
        pos = d.get("position") or ""
        lines.append("")
        lines.append(
            f"## {d['disclosure_date']} — {person}"
            + (f" ({pos})" if pos else "")
        )
        for label, key in (
            ("emittent", "emittent"), ("LEI", "lei"),
            ("instrument", "instrument_type"), ("ISIN", "isin"),
            ("transaction", "transaction_type"),
            ("price", "price"), ("volume", "volume"),
            ("transaction date", "transaction_date"),
            ("location", "location"),
        ):
            if d.get(key):
                lines.append(f"- {label}: {d[key]}")
        if d.get("disclosed_via"):
            lines.append(f"- disclosed via: {d['disclosed_via']}")
    if len(window) > MAX_DETAIL_FETCHES:
        lines.append(f"\n_(showing {MAX_DETAIL_FETCHES} of {len(window)} disclosures)_")
    return "\n".join(lines)
