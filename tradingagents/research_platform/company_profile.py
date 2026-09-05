"""Issuer identity extracted from normalized local fundamental snapshots."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from .data_contracts import FundamentalSnapshot

_PROFILE_FIELDS = (
    ("company_name", "name"),
    ("company_area", "area"),
    ("company_industry", "industry"),
    ("company_market", "market"),
    ("company_exchange", "exchange"),
    ("company_list_date", "list_date"),
)


class CompanyProfile(BaseModel):
    """Issuer identity available from the latest local snapshot."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    available: bool
    as_of_date: str | None = None
    name: str | None = None
    area: str | None = None
    industry: str | None = None
    market: str | None = None
    exchange: str | None = None
    list_date: str | None = None


def build_company_profile(
    snapshots: Iterable[FundamentalSnapshot], *, symbol: str
) -> CompanyProfile:
    """Read only vendor-supplied issuer fields from the latest daily snapshot."""

    candidates = [
        item
        for item in snapshots
        if item.fiscal_period == "daily_snapshot"
        and any(_text(item.metrics.get(source)) is not None for source, _ in _PROFILE_FIELDS)
    ]
    latest = max(
        candidates,
        key=lambda item: (item.period_end, item.provenance.as_of_date),
        default=None,
    )
    if latest is None:
        return CompanyProfile(symbol=symbol, available=False)

    values = {target: _text(latest.metrics.get(source)) for source, target in _PROFILE_FIELDS}
    values["list_date"] = _format_compact_date(values["list_date"])
    return CompanyProfile(
        symbol=symbol,
        available=any(values.values()),
        as_of_date=latest.provenance.as_of_date.isoformat(),
        **values,
    )


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _format_compact_date(value: str | None) -> str | None:
    if value is not None and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value
