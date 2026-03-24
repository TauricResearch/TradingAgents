import os
from datetime import datetime, timedelta

import requests


FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


def _get_fred_api_key() -> str | None:
    return os.getenv("FRED_API_KEY")


def _get_fred_observations(
    series_id: str,
    start_date: str,
    end_date: str,
    *,
    limit: int = 100,
):
    api_key = _get_fred_api_key()
    if not api_key:
        return {
            "error": (
                "FRED API key not configured. Set the FRED_API_KEY environment "
                "variable to enable macro data."
            )
        }

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "observation_end": end_date,
        "sort_order": "desc",
        "limit": limit,
    }

    try:
        response = requests.get(FRED_OBSERVATIONS_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {"error": f"Failed to fetch FRED data for {series_id}: {exc}"}
    except ValueError as exc:
        return {"error": f"FRED returned invalid JSON for {series_id}: {exc}"}


def _valid_observations(payload):
    observations = payload.get("observations", [])
    return [obs for obs in observations if obs.get("value") not in (None, ".")]


def _window_start(curr_date: str, lookback_days: int) -> str:
    return (
        datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")


def get_treasury_yield_curve(curr_date: str) -> str:
    start_date = _window_start(curr_date, 30)
    yield_series = [
        ("1 Month", "DGS1MO"),
        ("3 Month", "DGS3MO"),
        ("6 Month", "DGS6MO"),
        ("1 Year", "DGS1"),
        ("2 Year", "DGS2"),
        ("3 Year", "DGS3"),
        ("5 Year", "DGS5"),
        ("7 Year", "DGS7"),
        ("10 Year", "DGS10"),
        ("20 Year", "DGS20"),
        ("30 Year", "DGS30"),
    ]

    rows = []
    for maturity, series_id in yield_series:
        payload = _get_fred_observations(series_id, start_date, curr_date)
        if "error" in payload:
            continue
        observations = _valid_observations(payload)
        if not observations:
            continue
        latest = observations[0]
        rows.append((maturity, float(latest["value"]), latest["date"]))

    if not rows:
        return (
            f"## Treasury Yield Curve as of {curr_date}\n\n"
            "No Treasury yield data was available for the requested window."
        )

    lines = [
        f"## Treasury Yield Curve as of {curr_date}",
        "",
        "| Maturity | Yield (%) | Observation Date |",
        "| --- | ---: | --- |",
    ]
    for maturity, rate, observation_date in rows:
        lines.append(f"| {maturity} | {rate:.2f} | {observation_date} |")

    two_year = next((rate for maturity, rate, _ in rows if maturity == "2 Year"), None)
    ten_year = next((rate for maturity, rate, _ in rows if maturity == "10 Year"), None)
    if two_year is not None and ten_year is not None:
        spread = ten_year - two_year
        lines.extend(
            [
                "",
                "### Yield Curve Readout",
                f"- 2Y-10Y spread: {spread:.2f} percentage points.",
            ]
        )
        if spread < 0:
            lines.append("- Interpretation: the curve is inverted, a classic recession warning.")
        elif spread < 0.5:
            lines.append("- Interpretation: the curve is flat, pointing to tighter growth expectations.")
        else:
            lines.append("- Interpretation: the curve is upward sloping, consistent with normal growth expectations.")

    return "\n".join(lines)


def get_economic_indicators_report(curr_date: str, lookback_days: int = 90) -> str:
    start_date = _window_start(curr_date, lookback_days)
    indicators = {
        "Federal Funds Rate": {
            "series": "FEDFUNDS",
            "description": "Federal Reserve policy rate",
            "unit": "%",
        },
        "Consumer Price Index": {
            "series": "CPIAUCSL",
            "description": "Headline consumer inflation index",
            "unit": "index",
            "year_over_year": True,
        },
        "Producer Price Index": {
            "series": "PPIACO",
            "description": "Producer-level inflation index",
            "unit": "index",
            "year_over_year": True,
        },
        "Unemployment Rate": {
            "series": "UNRATE",
            "description": "Share of the labor force that is unemployed",
            "unit": "%",
        },
        "Nonfarm Payrolls": {
            "series": "PAYEMS",
            "description": "Total nonfarm payroll employment",
            "unit": "thousands",
        },
        "GDP": {
            "series": "GDP",
            "description": "Gross domestic product, nominal level",
            "unit": "billions",
        },
        "ISM Manufacturing PMI": {
            "series": "NAPM",
            "description": "Manufacturing activity diffusion index",
            "unit": "index",
        },
        "Consumer Confidence": {
            "series": "CSCICP03USM665S",
            "description": "OECD consumer confidence measure for the US",
            "unit": "index",
        },
        "VIX": {
            "series": "VIXCLS",
            "description": "CBOE market volatility index",
            "unit": "index",
        },
    }

    lines = [f"## Economic Indicators Report ({start_date} to {curr_date})", ""]
    for name, metadata in indicators.items():
        payload = _get_fred_observations(metadata["series"], start_date, curr_date)
        lines.append(f"### {name}")
        if "error" in payload:
            lines.append(f"- Error: {payload['error']}")
            lines.append("")
            continue

        observations = _valid_observations(payload)
        if not observations:
            lines.append("- No data available in the requested window.")
            lines.append("")
            continue

        latest = observations[0]
        latest_value = float(latest["value"])
        lines.append(
            f"- Latest value: {latest_value:.2f} {metadata['unit']} ({latest['date']})"
        )
        lines.append(f"- Description: {metadata['description']}")

        if len(observations) >= 2:
            previous = observations[1]
            previous_value = float(previous["value"])
            change = latest_value - previous_value
            change_pct = 0.0 if previous_value == 0 else (change / previous_value) * 100
            lines.append(
                f"- Sequential change: {change:+.2f} {metadata['unit']} ({change_pct:+.2f}%)"
            )

        if metadata.get("year_over_year") and len(observations) >= 12:
            year_ago = observations[11]
            year_ago_value = float(year_ago["value"])
            if year_ago_value != 0:
                yoy_change = ((latest_value - year_ago_value) / year_ago_value) * 100
                lines.append(f"- Year-over-year change: {yoy_change:+.2f}%")

        lines.append("")

    return "\n".join(lines).rstrip()


def get_fed_calendar_and_minutes(curr_date: str) -> str:
    start_date = _window_start(curr_date, 365)
    payload = _get_fred_observations("FEDFUNDS", start_date, curr_date)
    lines = [
        f"## Federal Reserve Policy Snapshot as of {curr_date}",
        "",
        "FRED does not provide the FOMC meeting calendar directly. This summary uses the recent policy-rate path as a proxy for the Fed backdrop.",
        "",
    ]

    if "error" in payload:
        lines.append(f"- Error: {payload['error']}")
        return "\n".join(lines)

    observations = _valid_observations(payload)
    if not observations:
        lines.append("- No recent Federal Funds observations were available.")
        return "\n".join(lines)

    lines.extend(
        [
            "| Date | Fed Funds Rate (%) | Change vs Prior |",
            "| --- | ---: | --- |",
        ]
    )
    recent_observations = observations[:6]
    for index, observation in enumerate(recent_observations):
        rate = float(observation["value"])
        change_text = "-"
        if index + 1 < len(observations):
            prior_rate = float(observations[index + 1]["value"])
            delta = rate - prior_rate
            change_text = "unchanged" if delta == 0 else f"{delta:+.2f}"
        lines.append(f"| {observation['date']} | {rate:.2f} | {change_text} |")

    latest_rate = float(recent_observations[0]["value"])
    lines.extend(
        [
            "",
            "### Policy Readout",
            f"- Latest effective Fed Funds rate in the series: {latest_rate:.2f}%.",
        ]
    )
    if latest_rate >= 4.0:
        lines.append("- Interpretation: policy remains restrictive relative to the post-2008 norm.")
    elif latest_rate <= 2.0:
        lines.append("- Interpretation: policy is accommodative by recent historical standards.")
    else:
        lines.append("- Interpretation: policy is near a neutral zone by recent historical standards.")

    return "\n".join(lines)
