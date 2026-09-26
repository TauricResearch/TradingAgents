"""Bank Negara Malaysia (BNM) macro vendor — Malaysia's own policy rate and
ringgit reference rate, for grounding KLSE analysis in domestic hard data.

FRED, the other macro vendor, is a US series library: its curated aliases are
all Federal Reserve / BLS / BEA series, so a Bursa run asking for "the policy
rate" got the *federal funds rate* and debated Malaysian equities through a
US lens. BNM publishes the series that actually move KLSE — the Overnight
Policy Rate set by its Monetary Policy Committee, and the Kuala Lumpur USD/MYR
reference rate — through a keyless public API, so this vendor needs no
credential and slots in ahead of FRED in the ``macro_data`` chain.

Point-in-time safety works differently here than in ``fred.py``, and more
simply. FRED serves revision-prone series (CPI, GDP) and therefore needs an
explicit vintage pin so a historical run doesn't see revisions published after
its as-of date. The two series here are *revision-free*: an MPC decision and a
day's reference rate are published once and never restated. Filtering
observations to ``<= curr_date`` is therefore sufficient for a point-in-time
correct answer — there is no later vintage to leak.

The OPR needs one piece of domain handling: BNM publishes MPC *decisions*, not
a daily level, so the series is a step function that can legitimately have zero
observations inside a window (the OPR has held at one level for a year or more
several times). An empty window is "unchanged", not "no data" — a distinction
this module preserves, because reporting "no data" for a rate that is simply
stable would be a false claim. The prevailing level is carried forward from the
last decision before the window.

Degrades like the other optional dataflow sources: an indicator this vendor
does not serve raises ``NoMarketDataError`` immediately and without a network
call, so the routing layer falls straight through to FRED for US series.

API shapes are documented at https://apidocs.bnm.gov.my. Field extraction is
deliberately tolerant (several accepted spellings per field) so a minor
response-shape difference degrades one field rather than the whole call.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import requests

from .errors import NoMarketDataError, VendorError

logger = logging.getLogger(__name__)

_API_BASE = "https://api.bnm.gov.my/public"

# BNM versions its API through the Accept header rather than the URL; without
# this it answers 400.
_ACCEPT = "application/vnd.BNM.API.v1+json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

REQUEST_TIMEOUT = 30

# Matches fred.py: a year captures the trend and the year-over-year base.
DEFAULT_LOOKBACK_DAYS = 365

# Rows cap for the rendered table, as in fred.py — the daily FX series over a
# long window would otherwise flood the analyst's context.
MAX_ROWS = 40

# The FX series is fetched one month per request, so a multi-year window would
# fan out into dozens of calls. Cap the fan-out and say so in the output rather
# than silently stalling a run.
_MAX_FX_MONTHS = 24

_OPR = "opr"
_USDMYR = "usd_myr"

# Friendly aliases -> the series this vendor serves. Anything not listed here is
# not BNM's to answer: the lookup is local, so a US indicator costs no network
# round-trip before the router falls through to FRED.
BNM_SERIES = {
    # Overnight Policy Rate (the MPC's policy rate)
    "opr": _OPR,
    "overnight_policy_rate": _OPR,
    "policy_rate": _OPR,
    "bnm_opr": _OPR,
    "bnm_policy_rate": _OPR,
    "malaysia_policy_rate": _OPR,
    "malaysia_interest_rate": _OPR,
    # Kuala Lumpur USD/MYR reference rate
    "usd_myr": _USDMYR,
    "myr_usd": _USDMYR,
    "usdmyr": _USDMYR,
    "ringgit": _USDMYR,
    "myr": _USDMYR,
    "ringgit_exchange_rate": _USDMYR,
    "malaysia_exchange_rate": _USDMYR,
}

_SERIES_META = {
    _OPR: {
        "title": "Overnight Policy Rate (OPR)",
        "units": "%",
        "frequency": "Per MPC decision (step series)",
    },
    _USDMYR: {
        "title": "Kuala Lumpur USD/MYR Reference Rate",
        "units": "MYR per USD",
        "frequency": "Daily (business days)",
    },
}


class BnmUnavailableError(VendorError):
    """BNM could not be reached or returned an unusable response.

    A ``VendorError`` so the routing layer treats it as "this vendor failed"
    and tries the next one in the chain instead of aborting the run.
    """


def _resolve_series(indicator: str) -> str:
    """Map an alias to a BNM series key, or raise so the router tries FRED.

    Purely local. ``NoMarketDataError`` is the right signal: this vendor has no
    rows for that indicator, and the router's existing handling moves on to the
    next configured vendor without logging it as a failure.
    """
    key = indicator.strip().lower().replace(" ", "_").replace("-", "_")
    if key in BNM_SERIES:
        return BNM_SERIES[key]
    raise NoMarketDataError(
        indicator,
        detail=(
            "BNM serves Malaysian series only "
            f"({', '.join(sorted(set(BNM_SERIES.values())))}); "
            "US series are served by FRED"
        ),
    )


def _request(path: str) -> dict:
    """GET a BNM endpoint and return the decoded JSON envelope.

    BNM answers 404 for a period it has no data for (e.g. a future month),
    which is a legitimate empty result rather than an error, so that maps to an
    empty envelope. Anything else that prevents a usable answer raises
    ``BnmUnavailableError``.
    """
    url = f"{_API_BASE}/{path}"
    try:
        response = requests.get(
            url,
            headers={"Accept": _ACCEPT, "User-Agent": _UA},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise BnmUnavailableError(f"BNM request failed for {path}: {exc}") from exc

    if response.status_code == 404:
        logger.debug("BNM has no data for %s (404)", path)
        return {}
    if response.status_code >= 400:
        raise BnmUnavailableError(
            f"BNM returned HTTP {response.status_code} for {path}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise BnmUnavailableError(f"BNM returned a non-JSON body for {path}") from exc
    return payload if isinstance(payload, dict) else {}


def _rows(payload: dict) -> list[dict]:
    """Extract the ``data`` array from a BNM envelope.

    Single-object endpoints return ``data`` as an object rather than a list;
    normalize both to a list of dicts so callers have one shape to parse.
    """
    data = payload.get("data")
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def _first_field(row: dict, *names):
    """Return the first present, non-null field among ``names``.

    Tolerance is deliberate: it keeps a minor field-name difference in BNM's
    response from failing the whole call.
    """
    for name in names:
        if row.get(name) is not None:
            return row[name]
    return None


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_opr(start_date: str, curr_date: str) -> list[tuple[str, float, float | None]]:
    """Fetch OPR decisions as ``(date, level, change)``, oldest first.

    Fetches from the year before the window so the level prevailing at the
    window's start is known even when no decision falls inside it — see the
    module docstring on why an empty window means "unchanged", not "no data".
    Observations are filtered to ``<= curr_date``; the OPR is revision-free, so
    that alone makes the result point-in-time correct.
    """
    start_year = int(start_date[:4])
    end_year = int(curr_date[:4])

    decisions: list[tuple[str, float, float | None]] = []
    reached = False
    for year in range(start_year - 1, end_year + 1):
        payload = _request(f"opr/year/{year}")
        reached = True
        for row in _rows(payload):
            date = _first_field(row, "date", "opr_date")
            level = _as_float(
                _first_field(row, "new_opr_level", "opr_level", "opr", "level")
            )
            if not date or level is None:
                continue
            change = _as_float(_first_field(row, "change_in_opr", "change"))
            if str(date) <= curr_date:
                decisions.append((str(date), level, change))

    if not reached:
        raise BnmUnavailableError("BNM returned no OPR response")

    decisions.sort(key=lambda d: d[0])
    return decisions


def _months(start_date: str, curr_date: str) -> list[tuple[int, int]]:
    """Inclusive (year, month) pairs spanning the window, most recent last."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    pairs: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        pairs.append((year, month))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return pairs


def _fetch_usd_myr(start_date: str, curr_date: str) -> tuple[list[tuple[str, float]], bool]:
    """Fetch daily KL USD/MYR reference rates as ``(date, rate)``, oldest first.

    Returns the points and whether the month fan-out was clamped. Like the OPR,
    this rate is published once and never revised, so filtering to the window is
    point-in-time correct on its own.
    """
    pairs = _months(start_date, curr_date)
    clamped = len(pairs) > _MAX_FX_MONTHS
    if clamped:
        pairs = pairs[-_MAX_FX_MONTHS:]

    # Keyed by date rather than appended: the series is fetched one month per
    # request, and a month endpoint that pads with a neighbouring month's
    # boundary days would otherwise double-count those dates, corrupting both
    # the observation table and the change-over-window figure.
    by_date: dict[str, float] = {}
    reached = False
    for year, month in pairs:
        payload = _request(f"kl-usd-reference-rate/year/{year}/month/{month}")
        reached = True
        for row in _rows(payload):
            date = _first_field(row, "date", "rate_date")
            rate = _as_float(_first_field(row, "rate", "reference_rate", "value"))
            if not date or rate is None:
                continue
            if start_date <= str(date) <= curr_date:
                by_date[str(date)] = rate

    if not reached:
        raise BnmUnavailableError("BNM returned no USD/MYR response")

    return sorted(by_date.items()), clamped


def _header(series: str, start_date: str, curr_date: str) -> str:
    meta = _SERIES_META[series]
    return (
        f"## BNM: {meta['title']}\n"
        f"- Units: {meta['units']}\n"
        f"- Frequency: {meta['frequency']}\n"
        f"- Window: {start_date} to {curr_date}\n"
        f"- Source: Bank Negara Malaysia (api.bnm.gov.my); published once, not revised\n"
    )


def _render_opr(decisions, start_date: str, curr_date: str) -> str:
    """Render the OPR step series, carrying the prevailing level forward."""
    header = _header(_OPR, start_date, curr_date)

    prior = [d for d in decisions if d[0] < start_date]
    in_window = [d for d in decisions if d[0] >= start_date]

    if not in_window:
        if not prior:
            # Genuinely nothing: no decision on or before curr_date at all.
            return header + (
                "\nNo OPR decision published on or before this date. The window "
                "may predate BNM's API coverage."
            )
        last_date, last_level, _ = prior[-1]
        return header + (
            f"\n**Latest:** {last_level:.2f}% (unchanged through the window)\n"
            f"\nThe MPC made no rate decision between {start_date} and {curr_date}. "
            f"The OPR has stood at **{last_level:.2f}%** since {last_date}. "
            f"This is a stable policy rate, not missing data.\n"
        )

    entry_level = prior[-1][1] if prior else in_window[0][1]
    last_date, last_level, _ = in_window[-1]
    delta = last_level - entry_level
    summary = (
        f"\n**Latest:** {last_level:.2f}% ({last_date}) | "
        f"**Change over window:** {delta:+.2f} pp "
        f"from {entry_level:.2f}%\n"
    )

    shown = in_window[-MAX_ROWS:]
    note = ""
    if len(in_window) > MAX_ROWS:
        note = (
            f"\n_(showing the most recent {MAX_ROWS} of {len(in_window)} decisions)_\n"
        )

    rows = []
    for date, level, change in shown:
        change_txt = f"{change:+.2f}" if change is not None else "—"
        rows.append(f"| {date} | {level:.2f} | {change_txt} |")
    table = (
        "\n| Decision date | OPR (%) | Change (pp) |\n| --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n"
    )
    return header + summary + note + table


def _render_usd_myr(points, clamped: bool, start_date: str, curr_date: str) -> str:
    """Render the daily USD/MYR reference-rate series."""
    header = _header(_USDMYR, start_date, curr_date)
    if not points:
        return header + (
            "\nNo USD/MYR reference rates published in this window. The window "
            "may fall entirely on non-business days or predate API coverage."
        )

    first_date, first_val = points[0]
    last_date, last_val = points[-1]
    delta = last_val - first_val
    pct = f" ({delta / first_val * 100:+.2f}%)" if first_val else ""
    # A rising USD/MYR is a *weaker* ringgit; spell that out so the analyst
    # cannot read the direction backwards.
    direction = "weaker" if delta > 0 else "stronger" if delta < 0 else "flat"
    summary = (
        f"\n**Latest:** {last_val:.4f} ({last_date}) | "
        f"**Change over window:** {delta:+.4f}{pct} "
        f"from {first_val:.4f} ({first_date}) — ringgit {direction} vs USD\n"
    )

    shown = points
    note = ""
    if clamped:
        note += (
            f"\n_(window clamped to the most recent {_MAX_FX_MONTHS} months)_\n"
        )
    if len(points) > MAX_ROWS:
        shown = points[-MAX_ROWS:]
        note += (
            f"\n_(showing the most recent {MAX_ROWS} of {len(points)} observations)_\n"
        )

    table = (
        "\n| Date | MYR per USD |\n| --- | --- |\n"
        + "\n".join(f"| {d} | {v:.4f} |" for d, v in shown)
        + "\n"
    )
    return header + summary + note + table


def get_macro_data(
    indicator: str,
    curr_date: str,
    look_back_days: int | None = None,
) -> str:
    """Fetch a Malaysian macro series from BNM as a formatted markdown report.

    Mirrors ``fred.get_macro_data``'s signature and output shape so the two are
    interchangeable behind the ``macro_data`` router.

    Args:
        indicator: A BNM alias — "opr"/"policy_rate" for the Overnight Policy
            Rate, "usd_myr"/"ringgit" for the KL USD/MYR reference rate. An
            indicator this vendor does not serve raises ``NoMarketDataError``
            without a network call so the router falls through to FRED.
        curr_date: The as-of date (yyyy-mm-dd), bounding the window. Both series
            are revision-free, so this bound alone is point-in-time correct.
        look_back_days: Trailing window length; ``None`` uses DEFAULT_LOOKBACK_DAYS.

    Returns:
        A markdown report with the series title, units, frequency, the latest
        value, the change over the window, and a recent observation table.
    """
    if look_back_days is None:
        look_back_days = DEFAULT_LOOKBACK_DAYS

    series = _resolve_series(indicator)

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (end_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

    if series == _OPR:
        return _render_opr(_fetch_opr(start_date, curr_date), start_date, curr_date)

    points, clamped = _fetch_usd_myr(start_date, curr_date)
    return _render_usd_myr(points, clamped, start_date, curr_date)
