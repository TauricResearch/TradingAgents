"""Source-labelled China macro and economic-cycle data adapters.

The public provider exposes separate statistical series.  This module keeps
their native rows and names intact: it does not interpolate missing releases,
combine units, or infer a cycle phase from incomplete observations.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import Any

import pandas as pd

from .china_capabilities import AshareCapabilityUnavailableError, CapabilityReport

_INDICATOR_METHODS = {
    "gdp": "macro_china_gdp",
    "cpi": "macro_china_cpi",
    "pmi": "macro_china_pmi",
    "money_supply": "macro_china_money_supply",
    "lpr": "macro_china_lpr",
    "industrial_production": "macro_china_industrial_production",
    "fx_reserves": "macro_china_fx_reserves",
}


class ChinaMacroProvider:
    """Fetch explicit China macro series through optional AKShare adapters."""

    name = "akshare"

    def __init__(self, api: Any | None = None) -> None:
        self._api = api

    def indicators(self, indicators: Iterable[str] | str = ("gdp", "cpi", "pmi")) -> CapabilityReport:
        requested = _normalise_indicators(indicators)
        frames: list[pd.DataFrame] = []
        unavailable: list[str] = []
        for indicator in requested:
            method = _INDICATOR_METHODS[indicator]
            try:
                data = self._call(method, indicator)
            except AshareCapabilityUnavailableError as exc:
                unavailable.append(f"{indicator}: {exc.detail}")
                continue
            frames.append(data.assign(indicator=indicator, source_method=method))

        if not frames:
            detail = "; ".join(unavailable) or "no usable public series"
            raise AshareCapabilityUnavailableError("china_macro_indicators", self.name, detail)

        combined = pd.concat(frames, ignore_index=True, sort=False)
        note = (
            "China macro source rows supplied by AKShare. Individual indicators may have "
            "different release calendars, units, and revisions; no cycle stage is inferred."
        )
        if unavailable:
            note += " Unavailable requested series: " + "; ".join(unavailable) + "."
        _capture_vendor_raw(combined, requested=requested)
        return CapabilityReport("china_macro_indicators", None, self.name, combined, note)

    def _call(self, method: str, indicator: str) -> pd.DataFrame:
        api = self._api
        if api is None:
            try:
                api = importlib.import_module("akshare")
            except ImportError as exc:
                raise AshareCapabilityUnavailableError(
                    "china_macro_indicators", self.name, "optional akshare package is not installed"
                ) from exc
        function = getattr(api, method, None)
        if not callable(function):
            raise AshareCapabilityUnavailableError(
                "china_macro_indicators", self.name, f"installed AKShare has no {method} adapter for {indicator}"
            )
        try:
            result = function()
        except Exception as exc:
            raise AshareCapabilityUnavailableError(
                "china_macro_indicators", self.name, f"{indicator}: {type(exc).__name__}"
            ) from exc
        if not isinstance(result, pd.DataFrame) or result.empty:
            raise AshareCapabilityUnavailableError(
                "china_macro_indicators", self.name, f"{indicator}: no tabular rows"
            )
        return result


def get_china_macro_indicators(indicators: str = "gdp,cpi,pmi") -> str:
    """Render selected China macro source records for research/cycle analysis.

    ``indicators`` is a comma-separated allowlist.  Unsupported names fail
    closed, avoiding accidental claims that a requested macro series exists.
    """
    return ChinaMacroProvider().indicators(indicators).render()


def _normalise_indicators(indicators: Iterable[str] | str) -> tuple[str, ...]:
    values = indicators.split(",") if isinstance(indicators, str) else indicators
    normalized = tuple(value.strip().lower() for value in values if str(value).strip())
    if not normalized:
        raise AshareCapabilityUnavailableError("china_macro_indicators", "akshare", "at least one indicator is required")
    unknown = [value for value in normalized if value not in _INDICATOR_METHODS]
    if unknown:
        raise AshareCapabilityUnavailableError(
            "china_macro_indicators", "akshare", f"unsupported indicator(s): {', '.join(unknown)}"
        )
    return tuple(dict.fromkeys(normalized))


def _capture_vendor_raw(data: pd.DataFrame, *, requested: tuple[str, ...]) -> None:
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(
        data,
        metadata={
            "provider": "akshare",
            "dataset": "china_macro_indicators",
            "indicators": ",".join(requested),
        },
    )
