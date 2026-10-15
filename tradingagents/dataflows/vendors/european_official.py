"""Keyless European and German macro series from ECB and Eurostat official APIs.

Eurostat's Statistics API returns JSON-stat 2.0; ECB's SDMX endpoint exposes
CSV observations. Historical observations are bounded by the requested date,
but Eurostat does not provide a point-in-time vintage here, so revised history
must not be described as the value originally known on that date.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

import requests

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.net import get_scrubbed

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
REQUEST_TIMEOUT = 25
MAX_ROWS = 40

# Dataset filters intentionally select one series so the JSON-stat time
# dimension is the only varying dimension. This makes sparse JSON-stat indices
# unambiguous and prevents accidentally flattening a high-dimensional response.
EUROSTAT_SERIES = {
    "germany_10y": {
        "dataset": "irt_lt_mcby_m",
        "params": {"geo": "DE", "int_rt": "MCBY", "freq": "M"},
        "label": "Germany long-term government bond yield (around 10 years), monthly convergence series; not a daily market quote",
        "unit": "% p.a., monthly",
        "period": "month",
    },
    "germany_hicp": {
        "dataset": "prc_hicp_minr",
        "params": {"geo": "DE", "unit": "RCH_A", "coicop18": "TOTAL"},
        "label": "Germany HICP inflation, annual rate of change",
        "unit": "% year over year",
        "period": "month",
    },
    "germany_inflation": "germany_hicp",
    "euro_hicp": {
        "dataset": "prc_hicp_minr",
        "params": {"geo": "EA20", "unit": "RCH_A", "coicop18": "TOTAL"},
        "label": "Euro area HICP inflation, annual rate of change",
        "unit": "% year over year",
        "period": "month",
    },
    "euro_area_hicp": "euro_hicp",
    "germany_unemployment": {
        "dataset": "une_rt_m",
        "params": {"geo": "DE", "unit": "PC_ACT", "sex": "T", "age": "TOTAL", "s_adj": "SA"},
        "label": "Germany unemployment rate, seasonally adjusted",
        "unit": "% of active population",
        "period": "month",
    },
    "germany_real_gdp": {
        "dataset": "namq_10_gdp",
        "params": {"geo": "DE", "na_item": "B1GQ", "unit": "CLV10_MEUR", "s_adj": "SCA"},
        "label": "Germany real GDP, seasonally adjusted chain-linked volume",
        "unit": "million EUR, chain-linked volumes",
        "period": "quarter",
    },
    "germany_gdp": "germany_real_gdp",
    "euro_real_gdp": {
        "dataset": "namq_10_gdp",
        "params": {"geo": "EA20", "na_item": "B1GQ", "unit": "CLV10_MEUR", "s_adj": "SCA"},
        "label": "Euro area real GDP, seasonally adjusted chain-linked volume",
        "unit": "million EUR, chain-linked volumes",
        "period": "quarter",
    },
}

ECB_SERIES = {
    "ecb_deposit_rate": (
        "FM",
        "B.U2.EUR.4F.KR.DFR.LEV",
        "ECB deposit facility rate (rate of changes)",
    ),
    "ecb_deposit_facility_rate": "ecb_deposit_rate",
}


def _resolve(mapping: dict, name: str):
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    seen = set()
    while key in mapping and isinstance(mapping[key], str):
        if key in seen:
            raise ValueError(f"cyclic macro alias: {name}")
        seen.add(key)
        key = mapping[key]
    return mapping.get(key)


def _period_end(period: str) -> date:
    """Convert an ISO day, YYYY-MM, or YYYY-Qn period to its final date."""
    if len(period) == 10:
        return date.fromisoformat(period)
    if len(period) == 7 and period[4] == "-" and period[5:7].isdigit():
        year, month = int(period[:4]), int(period[5:7])
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - timedelta(days=1)
    if len(period) == 7 and period[4:6] == "-Q":
        year, quarter = int(period[:4]), int(period[6])
        month = quarter * 3
        if quarter not in range(1, 5):
            raise ValueError(f"invalid quarter period: {period}")
        if month == 12:
            return date(year, month, 31)
        return date(year, month + 1, 1) - timedelta(days=1)
    raise ValueError(f"unsupported observation period: {period}")


def parse_eurostat_observations(payload: dict) -> list[tuple[str, float]]:
    """Parse a filtered Eurostat JSON-stat response into ordered time points."""
    dim_ids = payload.get("id") or []
    sizes = payload.get("size") or []
    dimensions = payload.get("dimension") or {}
    if not dim_ids or len(dim_ids) != len(sizes) or dim_ids[-1] != "time":
        raise ValueError("Eurostat response has an unexpected dimension layout")
    if any(size != 1 for size in sizes[:-1]):
        raise ValueError("Eurostat query did not select a single series")
    time_index = dimensions.get("time", {}).get("category", {}).get("index", {})
    values = payload.get("value") or {}
    result = []
    for period, position in time_index.items():
        raw = values.get(str(position))
        if raw is None:
            continue
        result.append((period, float(raw)))
    return sorted(result, key=lambda point: point[0])


def _period_for_query(day: date, period_kind: str) -> str:
    if period_kind == "month":
        return day.strftime("%Y-%m")
    if period_kind == "quarter":
        return f"{day.year}-Q{((day.month - 1) // 3) + 1}"
    return day.isoformat()


def _request_json(dataset: str, params: dict) -> dict:
    try:
        response = get_scrubbed(
            f"{EUROSTAT_BASE}/{dataset}",
            params={**params, "lang": "en"},
            timeout=REQUEST_TIMEOUT,
            secret="",
        )
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise VendorUnavailableError(f"Eurostat {dataset} request failed: {exc}") from None
    if not isinstance(payload, dict) or payload.get("class") != "dataset":
        raise VendorUnavailableError(f"Eurostat {dataset} returned an unexpected response")
    return payload


def _format_report(
    provider: str,
    label: str,
    unit: str,
    observations: list[tuple[str, float]],
    start: date,
    end: date,
    updated: str = "",
    source_api_url: str = "",
) -> str:
    filtered = [
        (period, value)
        for period, value in observations
        if start <= _period_end(period) <= end
    ]
    if not filtered:
        raise NoMarketDataError(label, detail=f"no observations in {start}..{end}")
    shown = filtered[-MAX_ROWS:]
    extra = f"\n- Dataset last updated: {updated}" if updated else ""
    caveat = (
        "\n- Vintage: current source revision; revised historical values may differ "
        "from values originally published at the analysis date."
        if provider == "Eurostat"
        else ""
    )
    latest_period, latest_value = filtered[-1]
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"## {provider}: {label}",
        f"- Source: {provider} official statistical API",
        f"- API endpoint: {source_api_url or 'not recorded'}",
        f"- Retrieved at (UTC): {retrieved_at}",
        f"- Unit: {unit}",
        f"- Requested window: {start} to {end}",
        f"- Latest observation: {latest_period} — {latest_value:g} {unit}",
    ]
    if extra:
        lines.append(extra.strip())
    if caveat:
        lines.append(caveat.strip())
    lines += ["", "| Period | Value |", "| --- | ---: |"]
    lines.extend(f"| {period} | {value:g} |" for period, value in shown)
    if len(filtered) > len(shown):
        lines.append(f"\n_(showing the latest {len(shown)} of {len(filtered)} observations)_")
    return "\n".join(lines)


def _eurostat_data(indicator: str, spec: dict, as_of_date: str, look_back_days: int) -> str:
    end = date.fromisoformat(as_of_date)
    start = end - timedelta(days=look_back_days)
    start_period = _period_for_query(start, spec["period"])
    end_period = _period_for_query(end, spec["period"])
    payload = _request_json(
        spec["dataset"],
        {
            **spec["params"],
            "sinceTimePeriod": start_period,
            "untilTimePeriod": end_period,
        },
    )
    points = parse_eurostat_observations(payload)
    return _format_report(
        "Eurostat",
        spec["label"],
        spec["unit"],
        points,
        start,
        end,
        updated=payload.get("updated", ""),
        source_api_url=f"{EUROSTAT_BASE}/{spec['dataset']}",
    )


def _ecb_data(indicator: str, spec: tuple[str, str, str], as_of_date: str, look_back_days: int) -> str:
    end = date.fromisoformat(as_of_date)
    start = end - timedelta(days=look_back_days)
    flow, key, label = spec
    try:
        response = get_scrubbed(
            f"{ECB_BASE}/{flow}/{key}",
            params={"startPeriod": start.isoformat(), "endPeriod": end.isoformat(), "format": "csvdata"},
            timeout=REQUEST_TIMEOUT,
            secret="",
        )
        reader = csv.DictReader(io.StringIO(response.text))
        points = [
            (row["TIME_PERIOD"], float(row["OBS_VALUE"]))
            for row in reader
            if row.get("TIME_PERIOD") and row.get("OBS_VALUE") not in (None, "")
        ]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise VendorUnavailableError(f"ECB {indicator} request failed: {exc}") from None
    return _format_report(
        "European Central Bank", label, "% p.a.", points, start, end,
        source_api_url=f"{ECB_BASE}/{flow}/{key}",
    )


def get_macro_data(indicator: str, as_of_date: str, look_back_days: int | None = None) -> str:
    """Fetch a supported German/euro-area series, otherwise allow router fallback."""
    if look_back_days is None:
        look_back_days = 365
    if look_back_days <= 0:
        raise ValueError("look_back_days must be positive")
    name = indicator.strip().lower().replace(" ", "_").replace("-", "_")

    ecb_spec = _resolve(ECB_SERIES, name)
    if ecb_spec:
        return _ecb_data(name, ecb_spec, as_of_date, look_back_days)

    eurostat_spec = _resolve(EUROSTAT_SERIES, name)
    if eurostat_spec:
        return _eurostat_data(name, eurostat_spec, as_of_date, look_back_days)

    raise NoMarketDataError(
        indicator,
        detail="indicator is not covered by the configured ECB/Eurostat series; try the next vendor",
    )
