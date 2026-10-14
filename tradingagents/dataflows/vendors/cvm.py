"""Company filings of B3 listings, from the CVM (Brazil's securities regulator).

What moves a Brazilian stock is filed with the CVM before it reaches any news
feed: material facts (*fato relevante*), notices to the market, earnings
releases, dividend notices. Yahoo tags almost no article with a ``.SA`` symbol,
so without this the news analyst of a B3 run reads little or nothing.

The CVM publishes every filing in its open data portal with the day it was
delivered, which makes the feed point-in-time and complete: an empty window is
a real absence, not a gap in coverage. No key or account is needed.

The delivery day carries no time, and companies commonly release material
facts after the close, so a run dated in the past does not read filings
delivered on its own last day (#1518). A run dated today reads them:
whatever is on file now is public.

Only ``.SA`` symbols are served; anything else falls through to the next
configured vendor, so ``tool_vendors={"get_news": "cvm,yfinance"}`` covers a
mixed universe.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import time
import zipfile
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.files import replace_file

_BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
# Periodic and occasional filings (IPE): one zip per year of delivery.
_FILINGS_URL = _BASE_URL + "/IPE/DADOS/ipe_cia_aberta_{year}.zip"
# Registration form (FCA): the CVM dataset that carries trading codes.
_REGISTRY_URL = _BASE_URL + "/FCA/DADOS/fca_cia_aberta_{year}.zip"

# B3's listing of issuers, by root: the public endpoint behind its company search page.
_B3_ISSUERS_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/"

REQUEST_TIMEOUT = 60

# The portal rebuilds the yearly files once a day. A closed year still takes
# late versions of old filings, so it is refreshed too, only less often.
_CURRENT_YEAR_TTL_SECONDS = 24 * 60 * 60
_CLOSED_YEAR_TTL_SECONDS = 7 * 24 * 60 * 60

# Categories that carry news, most decisive first: the rank orders what is kept
# when a window holds more filings than the article limit. Left out on purpose:
# monthly insider holdings, shareholder meeting minutes, bylaws and other
# paperwork, which outnumber these and say little about the price.
_CATEGORIES = (
    "Fato Relevante",
    "Comunicado ao Mercado",
    "Dados Econômico-Financeiros",
    "Aviso aos Acionistas",
    "Relatório Proventos",
    "Calendário de Eventos Corporativos",
)

# How each category reads to a model that may not know Portuguese.
_CATEGORY_NAMES = {
    "Fato Relevante": "Material fact",
    "Comunicado ao Mercado": "Notice to the market",
    "Dados Econômico-Financeiros": "Financial results",
    "Aviso aos Acionistas": "Notice to shareholders",
    "Relatório Proventos": "Dividend report",
    "Calendário de Eventos Corporativos": "Corporate events calendar",
}


def _b3_code(ticker: str) -> str | None:
    """``PETR4`` for ``petr4.sa``, or None when the symbol is not a B3 listing."""
    symbol = ticker.strip().upper()
    if not symbol.endswith(".SA"):
        return None
    code = symbol[: -len(".SA")]
    return code if code.isalnum() else None


def _download(url: str) -> bytes | None:
    """The file's bytes, or None when the portal has no such file (a year not yet open)."""
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise VendorUnavailableError(f"CVM open data request failed ({status or type(exc).__name__})") from exc


def _fresh(path: Path, ttl: float) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < ttl


def _cached_zip(url: str, name: str, year: int) -> Path | None:
    """The cached copy of a yearly file, or None when the portal has none for that year."""
    path = Path(get_config()["data_cache_dir"]) / "cvm" / name
    # A year with no file yet is remembered too, or every call would ask again.
    missing = path.with_name(f"{name}.missing")
    ttl = _CURRENT_YEAR_TTL_SECONDS if year >= date.today().year else _CLOSED_YEAR_TTL_SECONDS
    if _fresh(path, ttl):
        return path
    if _fresh(missing, ttl):
        return None
    content = _download(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        missing.touch()
        return None
    replace_file(path, lambda temp: Path(temp).write_bytes(content))
    missing.unlink(missing_ok=True)
    return path


def _csv_rows(path: Path, member: str):
    """Rows of one CSV inside a CVM zip; the portal writes Latin-1 with ``;`` as separator."""
    try:
        with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
            yield from csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")
    except (zipfile.BadZipFile, KeyError) as exc:
        # A truncated download is a miss for the next run, not a cached failure.
        path.unlink(missing_ok=True)
        raise VendorUnavailableError(f"CVM open data file {path.name} is unreadable") from exc


# A year of filings is ~36k rows across every company and category; only the
# news categories and the fields a report prints are kept, indexed by company,
# so a run holds a few MB per year rather than the whole file. ``mtime`` keys
# each index to the version of the file it was built from.
_FILING_FIELDS = ("Categoria", "Tipo", "Especie", "Assunto", "Data_Entrega",
                  "Protocolo_Entrega", "Link_Download")


@lru_cache(maxsize=16)
def _filings_index(path: str, mtime: float, member: str) -> dict[str, tuple[dict, ...]]:
    index: dict[str, list[dict]] = {}
    for row in _csv_rows(Path(path), member):
        if row.get("Categoria") in _CATEGORIES:
            index.setdefault(row["CNPJ_Companhia"], []).append({k: row.get(k) or "" for k in _FILING_FIELDS})
    return {cnpj: tuple(rows) for cnpj, rows in index.items()}


@lru_cache(maxsize=4)
def _registry_index(path: str, mtime: float, member: str) -> tuple[tuple[str, str, str, str, str, str], ...]:
    """(code, CNPJ, name, reference date, first and last trading day) per listed security."""
    return tuple(
        (code, row["CNPJ_Companhia"], row.get("Nome_Empresarial") or "", row.get("Data_Referencia") or "",
         row.get("Data_Inicio_Negociacao") or "", row.get("Data_Fim_Negociacao") or "")
        for row in _csv_rows(Path(path), member)
        if (code := (row.get("Codigo_Negociacao") or "").strip().upper())
    )


def _yearly(url: str, kind: str, member: str, year: int, build, empty):
    """``build``'s index of one year's file, or ``empty`` when the portal has no file for it."""
    path = _cached_zip(url.format(year=year), f"{kind}_{year}.zip", year)
    if path is None:
        return empty
    return build(str(path), path.stat().st_mtime, member.format(year=year))


def _b3_search(text: str) -> list[dict]:
    """B3's company search results for ``text``."""
    query = base64.b64encode(json.dumps(
        {"language": "pt-br", "pageNumber": 1, "pageSize": 120, "company": text}).encode()).decode()
    try:
        response = requests.get(_B3_ISSUERS_URL + query, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json().get("results") or []
    except (requests.RequestException, ValueError) as exc:
        raise VendorUnavailableError(f"B3 listed companies request failed ({type(exc).__name__})") from exc


def _b3_issuer(root: str) -> tuple[str, str, str] | None:
    """(CNPJ, name, listing day) of the issuer B3 lists under a four-letter root, or None.

    The fallback for registry entries a company filled in wrong: the trading
    code in the CVM form is free text, and some filers enter their CVM code
    (CSN wrote ``4030``) or zeros (BTG Pactual) instead. B3's own listing names
    the issuer behind every root. Its search matches names too, so only an
    exact root counts.
    """
    path = Path(get_config()["data_cache_dir"]) / "cvm" / f"b3_issuer_{root}.json"
    if _fresh(path, _CLOSED_YEAR_TTL_SECONDS):
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
            return tuple(found) if found else None
        except ValueError:
            pass  # a truncated file is a miss, not a failure
    match = next((r for r in _b3_search(root) if (r.get("issuingCompany") or "").upper() == root), None)
    found = None
    if match:
        digits = "".join(c for c in str(match.get("cnpj") or "") if c.isdigit()).zfill(14)
        try:
            listed = datetime.strptime(match.get("dateListing") or "", "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            listed = ""
        if digits != "0" * 14 and listed:
            cnpj = f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
            found = (cnpj, match.get("companyName") or "", listed)
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_file(path, lambda temp: Path(temp).write_text(json.dumps(found), encoding="utf-8"))
    return found


def company_for(code: str, as_of_date: str) -> tuple[str, str] | None:
    """(CNPJ, name) of the company trading as ``code`` on ``as_of_date``.

    Companies refile the CVM registration form every year, so the as-of year and
    the one before list every active security at the code it had then. An exact
    code wins over its four-letter root (``PETR3`` resolves through ``PETR4``,
    the same issuer on B3). Among entries for one code, one trading on the date
    is preferred, but an entry is never ruled out by its dates alone: filers
    leave them stale (Raízen's ``RAIZ4`` reads as ending in 2021). A code the
    registry does not list at all is looked up in B3's listing by its root,
    which only answers for an issuer already listed on the date.
    """
    year = int(as_of_date[:4])
    root = code[:4]
    # Lower is better: exact before root, then trading on the date before not.
    best: tuple[int, tuple[str, str]] | None = None
    for y in (year, year - 1):
        registry = _yearly(_REGISTRY_URL, "fca", "fca_cia_aberta_valor_mobiliario_{year}.csv", y, _registry_index, ())
        for listed, cnpj, name, reference, first_day, last_day in registry:
            if reference > as_of_date:
                continue
            if listed == code:
                rank = 0
            elif len(code) > 4 and listed[:4] == root:
                rank = 2
            else:
                continue
            trading = first_day <= as_of_date and not (last_day and last_day < as_of_date)
            rank += 0 if trading else 1
            if best is None or rank < best[0]:
                best = (rank, (cnpj, name))
    if best is not None:
        return best[1]
    if not (root.isalpha() and len(root) == 4):
        return None
    issuer = _b3_issuer(root)
    # B3 lists the present: an issuer listed after the date did not trade as this
    # code then. Registrants that never traded are listed as of 31/12/9999, and a
    # root freed by a renamed issuer can be one (``EMBR`` once Embraer became ``EMBJ``).
    if issuer is None or issuer[2] > as_of_date:
        return None
    return issuer[0], issuer[1]


def _filings(cnpj: str, start_date: str, last_day: str) -> list[dict]:
    """News-bearing filings delivered in ``[start_date, last_day]``, one per filing.

    A filing refiled as a new version keeps its first delivery: that is when the
    market first read it.
    """
    first: dict[str, dict] = {}
    for year in range(int(start_date[:4]), int(last_day[:4]) + 1):
        index = _yearly(_FILINGS_URL, "ipe", "ipe_cia_aberta_{year}.csv", year, _filings_index, {})
        for row in index.get(cnpj, ()):
            delivered = row["Data_Entrega"]
            if not start_date <= delivered <= last_day:
                continue
            key = row["Protocolo_Entrega"] or row["Link_Download"] or f"{delivered}|{row['Assunto']}"
            if key not in first or delivered < first[key]["Data_Entrega"]:
                first[key] = row
    return list(first.values())


def _describe(row: dict) -> str:
    category = row["Categoria"]
    label = _CATEGORY_NAMES.get(category, category)
    # Material facts often go out with no subject; the type says what the rest is.
    subject = (row.get("Assunto") or row.get("Tipo") or row.get("Especie") or "").strip()
    # A filing on several subjects joins them with ``||``.
    subject = "; ".join(part.strip() for part in subject.split("||") if part.strip())
    line = f"### {label} ({category}), delivered {row['Data_Entrega']}"
    if subject:
        line += f"\n{subject}"
    if row.get("Link_Download"):
        line += f"\nDocument: {row['Link_Download']}"
    return line + "\n"


def get_news_cvm(ticker: str, start_date: str, end_date: str) -> str:
    """Filings by the company behind a ``.SA`` symbol, delivered to the CVM in the window."""
    code = _b3_code(ticker)
    if code is None:
        raise NoMarketDataError(ticker, ticker, "not a B3 listing (.SA)")
    company = company_for(code, end_date)
    if company is None:
        raise NoMarketDataError(ticker, code, f"no CVM registrant trades as {code}")
    cnpj, name = company

    # The delivery day has no time: on a past run's last day a filing may have
    # come after the close, and the market's reaction to it is what gets scored.
    last_day, note = end_date, ""
    if is_historical(end_date):
        last_day = f"{datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=1):%Y-%m-%d}"
        note = (f"Filings delivered on {end_date} are left out: the CVM records the day "
                f"but not the time, so they may have come after that day's close.\n\n")
    if last_day < start_date:
        return (f"No CVM filings are served for {ticker} between {start_date} and {end_date}: "
                f"the window is the run's last day only. {note.strip()}")

    filings = _filings(cnpj, start_date, last_day)
    header = f"## {ticker} ({name}) filings with the CVM, delivered {start_date} to {last_day}:\n\n"
    if not filings:
        # The CVM register is complete, so this is a real absence.
        return header + note + "No material facts, notices or results were filed in this window.\n"

    limit = get_config()["news_article_limit"]
    rank = {category: i for i, category in enumerate(_CATEGORIES)}
    # Newest first within a category, then the most decisive categories first,
    # so a full window keeps every material fact before any calendar update.
    by_date = sorted(filings, key=lambda r: r["Data_Entrega"], reverse=True)
    kept = sorted(by_date, key=lambda r: rank[r["Categoria"]])[:limit]
    kept.sort(key=lambda r: r["Data_Entrega"], reverse=True)
    dropped = len(filings) - len(kept)
    tail = f"\n_({dropped} lower-priority filings in this window are not shown)_\n" if dropped else ""
    return header + note + "\n".join(_describe(row) for row in kept) + tail
