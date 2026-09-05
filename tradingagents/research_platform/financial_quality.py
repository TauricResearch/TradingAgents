"""Point-in-time financial quality snapshots for local equity research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from math import isnan
from typing import Any

from .data_contracts import DataProvenance, FundamentalSnapshot


def build_financial_quality_snapshot(
    *,
    symbol: str,
    as_of_date: date,
    currency: str | None,
    income_rows: Sequence[Mapping[str, Any]],
    balance_rows: Sequence[Mapping[str, Any]],
    cashflow_rows: Sequence[Mapping[str, Any]],
    indicator_rows: Sequence[Mapping[str, Any]],
    provenance: DataProvenance,
) -> FundamentalSnapshot | None:
    """Build the latest fully disclosed report-period snapshot available by ``as_of_date``."""

    sources = (income_rows, balance_rows, cashflow_rows, indicator_rows)
    periods = _disclosed_periods(sources, as_of_date)
    if not periods:
        return None

    period_end = max(periods)
    income = _latest_row_for_period(income_rows, period_end, as_of_date)
    balance = _latest_row_for_period(balance_rows, period_end, as_of_date)
    cashflow = _latest_row_for_period(cashflow_rows, period_end, as_of_date)
    indicator = _latest_row_for_period(indicator_rows, period_end, as_of_date)
    metrics = _quality_metrics(income, balance, cashflow, indicator)
    if not metrics:
        return None

    return FundamentalSnapshot(
        symbol=symbol,
        period_end=period_end,
        fiscal_period=f"financial_report_{period_end.isoformat()}",
        currency=currency,
        metrics=metrics,
        provenance=provenance,
    )


def build_financial_quality_history(
    *,
    symbol: str,
    as_of_date: date,
    currency: str | None,
    income_rows: Sequence[Mapping[str, Any]],
    balance_rows: Sequence[Mapping[str, Any]],
    cashflow_rows: Sequence[Mapping[str, Any]],
    indicator_rows: Sequence[Mapping[str, Any]],
    provenance: DataProvenance,
    max_periods: int = 8,
) -> list[FundamentalSnapshot]:
    """Build recent disclosed report snapshots in ascending report-period order."""

    if max_periods < 1:
        raise ValueError("max_periods must be at least 1")
    sources = (income_rows, balance_rows, cashflow_rows, indicator_rows)
    periods = sorted(_disclosed_periods(sources, as_of_date))[-max_periods:]
    snapshots: list[FundamentalSnapshot] = []
    for period_end in periods:
        snapshot = build_financial_quality_snapshot(
            symbol=symbol,
            as_of_date=as_of_date,
            currency=currency,
            income_rows=_rows_through_period(income_rows, period_end),
            balance_rows=_rows_through_period(balance_rows, period_end),
            cashflow_rows=_rows_through_period(cashflow_rows, period_end),
            indicator_rows=_rows_through_period(indicator_rows, period_end),
            provenance=provenance,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


def _disclosed_periods(
    sources: Sequence[Sequence[Mapping[str, Any]]],
    as_of_date: date,
) -> set[date]:
    return {
        period
        for rows in sources
        for row in rows
        if _available_date(row, "ann_date", as_of_date) is not None
        and (period := _available_date(row, "end_date", as_of_date)) is not None
    }


def _rows_through_period(
    rows: Sequence[Mapping[str, Any]],
    period_end: date,
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if (row_period := _parse_date(row.get("end_date"))) is not None and row_period <= period_end
    ]


def _latest_row_for_period(
    rows: Sequence[Mapping[str, Any]],
    period_end: date,
    as_of_date: date,
) -> Mapping[str, Any] | None:
    eligible = [
        row
        for row in rows
        if _available_date(row, "end_date", as_of_date) == period_end
        and _available_date(row, "ann_date", as_of_date) is not None
    ]
    return max(
        eligible,
        key=lambda row: _available_date(row, "ann_date", as_of_date) or date.min,
        default=None,
    )


def _quality_metrics(
    income: Mapping[str, Any] | None,
    balance: Mapping[str, Any] | None,
    cashflow: Mapping[str, Any] | None,
    indicator: Mapping[str, Any] | None,
) -> dict[str, float | int | str | None]:
    metrics: dict[str, float | int | str | None] = {}
    _copy_metrics(
        metrics,
        income,
        {
            "total_revenue": "reported_total_revenue",
            "revenue": "reported_revenue",
            "n_income": "reported_net_income",
            "operate_profit": "reported_operating_profit",
        },
    )
    _copy_metrics(
        metrics,
        balance,
        {
            "total_assets": "reported_total_assets",
            "total_liab": "reported_total_liabilities",
            "total_hldr_eqy_exc_min_int": "reported_total_equity",
        },
    )
    _copy_metrics(
        metrics,
        cashflow,
        {
            "n_cashflow_act": "reported_operating_cashflow",
            "free_cashflow": "reported_free_cashflow",
        },
    )
    _copy_metrics(
        metrics,
        indicator,
        {
            "roe": "return_on_equity_pct",
            "roa": "return_on_assets_pct",
            "grossprofit_margin": "gross_profit_margin_pct",
            "debt_to_assets": "debt_to_assets_pct",
            "current_ratio": "current_ratio",
            "quick_ratio": "quick_ratio",
            "ocf_to_debt": "operating_cashflow_to_debt_pct",
            "netprofit_yoy": "net_profit_yoy_pct",
            "ocf_yoy": "operating_cashflow_yoy_pct",
        },
    )
    _add_ratio(
        metrics,
        numerator_key="reported_operating_cashflow",
        denominator_key="reported_net_income",
        result_key="operating_cashflow_to_net_income_ratio",
    )
    _add_ratio(
        metrics,
        numerator_key="reported_total_liabilities",
        denominator_key="reported_total_assets",
        result_key="calculated_liabilities_to_assets_ratio",
    )
    _add_announcement_dates(metrics, income, balance, cashflow, indicator)
    return metrics


def _copy_metrics(
    metrics: dict[str, float | int | str | None],
    row: Mapping[str, Any] | None,
    mapping: Mapping[str, str],
) -> None:
    if row is None:
        return
    for source, target in mapping.items():
        if (value := _number_or_text(row.get(source))) is not None:
            metrics[target] = value


def _add_ratio(
    metrics: dict[str, float | int | str | None],
    *,
    numerator_key: str,
    denominator_key: str,
    result_key: str,
) -> None:
    numerator = metrics.get(numerator_key)
    denominator = metrics.get(denominator_key)
    if isinstance(numerator, int | float) and isinstance(denominator, int | float) and denominator:
        metrics[result_key] = numerator / denominator


def _add_announcement_dates(
    metrics: dict[str, float | int | str | None],
    income: Mapping[str, Any] | None,
    balance: Mapping[str, Any] | None,
    cashflow: Mapping[str, Any] | None,
    indicator: Mapping[str, Any] | None,
) -> None:
    for label, row in (
        ("income", income),
        ("balance", balance),
        ("cashflow", cashflow),
        ("indicator", indicator),
    ):
        if row is not None and (value := _date_text(row.get("ann_date"))) is not None:
            metrics[f"{label}_announcement_date"] = value


def _available_date(row: Mapping[str, Any], field: str, as_of_date: date) -> date | None:
    value = _parse_date(row.get(field))
    return value if value is not None and value <= as_of_date else None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return (
                date.fromisoformat(value)
                if pattern == "%Y-%m-%d"
                else date(int(value[:4]), int(value[4:6]), int(value[6:]))
            )
        except ValueError:
            continue
    return None


def _date_text(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed is not None else None


def _number_or_text(value: Any) -> float | int | str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and isnan(value):
        return None
    if isinstance(value, int | float | str):
        return value
    return None
