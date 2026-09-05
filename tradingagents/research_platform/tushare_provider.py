"""Tushare Pro provider for China A-share and Hong Kong daily research data."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from math import isnan
from typing import Any

from .data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    InstrumentIdentity,
    NewsItem,
    PriceBar,
)
from .financial_quality import build_financial_quality_history

ProClientFactory = Callable[[str], Any]


class TushareDataUnavailableError(RuntimeError):
    """Raised when Tushare Pro cannot return usable normalized data."""


class TushareProProvider:
    """Normalize Tushare Pro A-share and Hong Kong daily data.

    A-share bars merge Tushare's ``daily`` and ``adj_factor`` endpoints and
    expose forward-adjusted closes. Hong Kong bars use ``hk_daily_adj`` when
    the caller has that endpoint's permission.
    A-share company disclosures are normalized as date-granular research
    evidence; Hong Kong company-event coverage is intentionally not inferred.
    """

    name = "tushare_pro"

    def __init__(
        self,
        *,
        pro_client: Any | None = None,
        token: str | None = None,
        pro_client_factory: ProClientFactory | None = None,
    ):
        self._token = token or os.environ.get("TUSHARE_TOKEN", "").strip()
        if pro_client is None and not self._token:
            raise TushareDataUnavailableError("TUSHARE_TOKEN is required for Tushare Pro research.")
        self._pro = pro_client or (pro_client_factory or _default_pro_client_factory)(self._token)

    def get_price_bars(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[PriceBar]:
        if end < start:
            raise ValueError("end must be on or after start")
        availability_date = as_of_date or end
        ts_code = canonical_tushare_symbol(identity)
        frame = self._fetch_price_frame(ts_code, start, end)
        rows = _records(frame)
        if not rows:
            raise TushareDataUnavailableError(
                f"no Tushare daily rows for {identity.symbol} between {start} and {end}"
            )

        parsed_rows = []
        for row in rows:
            trade_date = _required_date(row, "trade_date")
            if start <= trade_date <= end and trade_date <= availability_date:
                parsed_rows.append((trade_date, row))
        if not parsed_rows:
            raise TushareDataUnavailableError(
                f"no Tushare rows available by {availability_date.isoformat()} for {identity.symbol}"
            )

        latest_row = max(parsed_rows, key=lambda item: item[0])[1]
        latest_factor = _optional_float(latest_row, "adj_factor")
        bars: list[PriceBar] = []
        for trade_date, row in parsed_rows:
            close = _required_float(row, "close")
            factor = _optional_float(row, "adj_factor")
            adjusted_close = (
                close * factor / latest_factor
                if factor is not None and latest_factor not in (None, 0)
                else None
            )
            bars.append(
                PriceBar(
                    symbol=identity.symbol,
                    date=trade_date,
                    open=_required_float(row, "open"),
                    high=_required_float(row, "high"),
                    low=_required_float(row, "low"),
                    close=close,
                    adjusted_close=adjusted_close,
                    adjustment_factor=factor,
                    adjustment_method=(
                        "forward_adjusted"
                        if factor is not None and latest_factor not in (None, 0)
                        else None
                    ),
                    volume=_optional_int(row, "vol"),
                    currency=identity.currency or _currency_for(ts_code),
                    provenance=_provenance(
                        availability_date,
                        source=(
                            "tushare.pro.hk_daily_adj"
                            if ts_code.endswith(".HK")
                            else (
                                "tushare.pro.daily+adj_factor"
                                if latest_factor is not None
                                else "tushare.pro.daily"
                            )
                        ),
                        vendor_symbol=ts_code,
                    ),
                )
            )
        return sorted(bars, key=lambda bar: bar.date)

    def get_fundamentals(
        self,
        identity: InstrumentIdentity,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[FundamentalSnapshot]:
        availability_date = as_of_date or date.today()
        ts_code = canonical_tushare_symbol(identity)
        if ts_code.endswith(".HK"):
            rows = self._fetch_fundamental_rows("hk_daily_adj", ts_code, availability_date)
            metric_builder = _hk_metrics
            source = "tushare.pro.hk_daily_adj"
        else:
            rows = self._fetch_fundamental_rows("daily_basic", ts_code, availability_date)
            metric_builder = _a_share_metrics
            source = "tushare.pro.daily_basic"

        snapshots = _daily_fundamental_snapshots(
            identity=identity,
            rows=rows,
            availability_date=availability_date,
            currency=identity.currency or _currency_for(ts_code),
            source=source,
            ts_code=ts_code,
            metric_builder=metric_builder,
        )
        if not snapshots:
            raise TushareDataUnavailableError(
                f"no usable Tushare fundamental snapshot for {identity.symbol}"
            )
        if ts_code.endswith(".HK"):
            return snapshots

        profile_metrics = self._fetch_a_share_company_profile(ts_code)
        if profile_metrics:
            latest = snapshots[0]
            snapshots[0] = latest.model_copy(
                update={"metrics": {**latest.metrics, **profile_metrics}}
            )

        financial_rows = self._fetch_financial_quality_rows(ts_code, availability_date)
        snapshots.extend(
            build_financial_quality_history(
                symbol=identity.symbol,
                as_of_date=availability_date,
                currency=identity.currency or _currency_for(ts_code),
                income_rows=financial_rows["income"],
                balance_rows=financial_rows["balancesheet"],
                cashflow_rows=financial_rows["cashflow"],
                indicator_rows=financial_rows["fina_indicator"],
                provenance=_provenance(
                    availability_date,
                    source="tushare.pro.financial_statements",
                    vendor_symbol=ts_code,
                ),
            )
        )
        return snapshots

    def get_news(
        self,
        identity: InstrumentIdentity,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> Sequence[NewsItem]:
        """Return A-share company disclosures with explicit announcement dates."""

        if end < start:
            raise ValueError("end must be on or after start")
        availability_date = as_of_date or end
        ts_code = canonical_tushare_symbol(identity)
        if ts_code.endswith(".HK"):
            return []

        events: list[NewsItem] = []
        for endpoint, event_type, optional in (
            ("forecast", "earnings_forecast", False),
            ("express", "earnings_express", False),
            ("dividend", "dividend_plan", True),
            ("repurchase", "share_repurchase", True),
            ("fina_audit", "audit_opinion", True),
        ):
            try:
                rows = self._fetch_corporate_event_rows(endpoint, ts_code, start, end)
            except TushareDataUnavailableError:
                if optional:
                    continue
                raise
            for row in rows:
                announcement_date = _optional_date(row, "ann_date")
                if announcement_date is None or not (
                    start <= announcement_date <= end and announcement_date <= availability_date
                ):
                    continue
                events.append(
                    NewsItem(
                        symbol=identity.symbol,
                        title=_corporate_event_title(event_type, row),
                        published_at=datetime.combine(
                            announcement_date,
                            time.min,
                            tzinfo=timezone.utc,
                        ),
                        as_of_date=availability_date,
                        provider=self.name,
                        summary=_corporate_event_summary(event_type, row),
                        source_id=_corporate_event_source_id(event_type, ts_code, row),
                    )
                )
        unique_events = {item.source_id: item for item in events}
        return sorted(unique_events.values(), key=lambda item: item.published_at, reverse=True)

    def _fetch_price_frame(self, ts_code: str, start: date, end: date) -> Any:
        params = {
            "ts_code": ts_code,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        }
        try:
            if ts_code.endswith(".HK"):
                return self._pro.hk_daily_adj(**params)
            daily_rows = _records(self._pro.daily(**params))
            try:
                factor_rows = _records(self._pro.adj_factor(**params))
            except Exception:
                factor_rows = []
            factors_by_date = {
                str(row.get("trade_date")): _optional_float(row, "adj_factor")
                for row in factor_rows
                if row.get("trade_date") is not None
            }
            return [
                {**row, "adj_factor": factors_by_date.get(str(row.get("trade_date")))}
                for row in daily_rows
            ]
        except Exception as error:
            raise TushareDataUnavailableError(
                f"Tushare price data unavailable for {ts_code}: {error}"
            ) from error

    def _fetch_a_share_company_profile(self, ts_code: str) -> dict[str, str]:
        params = {
            "ts_code": ts_code,
            "fields": "ts_code,name,area,industry,market,exchange,list_date",
        }
        try:
            rows = _records(self._pro.stock_basic(**params))
        except Exception:
            return {}
        if not rows:
            return {}
        mapping = {
            "name": "company_name",
            "area": "company_area",
            "industry": "company_industry",
            "market": "company_market",
            "exchange": "company_exchange",
            "list_date": "company_list_date",
        }
        return {
            target: value
            for source, target in mapping.items()
            if isinstance((value := rows[0].get(source)), str) and value.strip()
        }

    def _fetch_fundamental_rows(
        self,
        endpoint: str,
        ts_code: str,
        availability_date: date,
    ) -> list[Mapping[str, Any]]:
        lookback_days = 400 if endpoint == "daily_basic" else 14
        params = {
            "ts_code": ts_code,
            "start_date": (availability_date - timedelta(days=lookback_days)).strftime("%Y%m%d"),
            "end_date": availability_date.strftime("%Y%m%d"),
        }
        try:
            return _records(getattr(self._pro, endpoint)(**params))
        except Exception as error:
            raise TushareDataUnavailableError(
                f"Tushare fundamental data unavailable for {ts_code}: {error}"
            ) from error

    def _fetch_financial_quality_rows(
        self,
        ts_code: str,
        availability_date: date,
    ) -> dict[str, list[Mapping[str, Any]]]:
        params = {
            "ts_code": ts_code,
            "start_date": (availability_date - timedelta(days=730)).strftime("%Y%m%d"),
            "end_date": availability_date.strftime("%Y%m%d"),
        }
        endpoints = ("income", "balancesheet", "cashflow", "fina_indicator")
        try:
            return {
                endpoint: _records(getattr(self._pro, endpoint)(**params)) for endpoint in endpoints
            }
        except Exception as error:
            raise TushareDataUnavailableError(
                f"Tushare financial quality data unavailable for {ts_code}: {error}"
            ) from error

    def _fetch_corporate_event_rows(
        self,
        endpoint: str,
        ts_code: str,
        start: date,
        end: date,
    ) -> list[Mapping[str, Any]]:
        params = {
            "ts_code": ts_code,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        }
        try:
            return _records(getattr(self._pro, endpoint)(**params))
        except Exception as error:
            raise TushareDataUnavailableError(
                f"Tushare corporate event data unavailable for {ts_code}: {error}"
            ) from error


def canonical_tushare_symbol(identity: InstrumentIdentity) -> str:
    """Normalize local, Yahoo-style, and Tushare-style Chinese tickers."""

    raw = (identity.vendor_symbol or identity.symbol).strip().upper()
    if raw.endswith(".SS"):
        raw = raw[:-3] + ".SH"
    if raw.endswith(".HK"):
        code = raw[:-3]
        if not code.isdigit() or len(code) > 5:
            raise ValueError(f"unsupported Hong Kong symbol: {identity.symbol}")
        return f"{code.zfill(5)}.HK"
    if raw.endswith((".SH", ".SZ", ".BJ")):
        code, suffix = raw.rsplit(".", 1)
        if not code.isdigit() or len(code) != 6:
            raise ValueError(f"unsupported China A-share symbol: {identity.symbol}")
        return f"{code}.{suffix}"
    if raw.isdigit() and len(raw) == 6:
        if raw.startswith(("4", "8")):
            return f"{raw}.BJ"
        return f"{raw}.SH" if raw.startswith(("5", "6", "9")) else f"{raw}.SZ"
    raise ValueError(
        "Tushare Pro expects a six-digit A-share code or a Tushare-style .HK/.SH/.SZ symbol."
    )


def supports_tushare_symbol(symbol: str) -> bool:
    """Return whether a symbol can be resolved by this China/Hong Kong adapter."""

    try:
        canonical_tushare_symbol(InstrumentIdentity(symbol=symbol))
    except ValueError:
        return False
    return True


def _corporate_event_title(event_type: str, row: Mapping[str, Any]) -> str:
    labels = {
        "earnings_forecast": "Earnings forecast",
        "earnings_express": "Earnings express",
        "dividend_plan": "Dividend plan",
        "share_repurchase": "Share repurchase",
        "audit_opinion": "Audit opinion",
    }
    period_end = _optional_number_or_text(row, "end_date")
    label = labels[event_type]
    return f"{label} announced for period {period_end}" if period_end is not None else label


def _corporate_event_summary(event_type: str, row: Mapping[str, Any]) -> str | None:
    fields_by_event = {
        "earnings_forecast": (
            ("type", "type"),
            ("p_change_min", "profit change minimum (%)"),
            ("p_change_max", "profit change maximum (%)"),
            ("net_profit_min", "net profit minimum"),
            ("net_profit_max", "net profit maximum"),
            ("summary", "summary"),
            ("change_reason", "change reason"),
        ),
        "earnings_express": (
            ("revenue", "revenue"),
            ("n_income", "net income"),
            ("yoy_net_profit", "net income YoY (%)"),
            ("perf_summary", "summary"),
        ),
        "dividend_plan": (
            ("cash_div_tax", "cash dividend per share (tax included)"),
            ("stk_div", "stock dividend per share"),
            ("record_date", "record date"),
            ("ex_date", "ex-dividend date"),
            ("div_proc", "progress"),
        ),
        "share_repurchase": (
            ("proc", "progress"),
            ("vol", "repurchased volume"),
            ("amount", "repurchase amount"),
            ("high_limit", "upper price limit"),
            ("low_limit", "lower price limit"),
        ),
        "audit_opinion": (
            ("audit_result", "audit result"),
            ("audit_fees", "audit fees"),
            ("audit_agency", "audit agency"),
            ("audit_sign", "auditor signatory"),
        ),
    }
    fields = fields_by_event[event_type]
    values = [
        f"{label}: {value}"
        for field, label in fields
        if (value := _optional_number_or_text(row, field)) is not None
    ]
    return "; ".join(values) or None


def _corporate_event_source_id(event_type: str, ts_code: str, row: Mapping[str, Any]) -> str:
    parts = [
        event_type,
        ts_code,
        str(_optional_number_or_text(row, "ann_date") or "unknown-date"),
        str(_optional_number_or_text(row, "end_date") or "unknown-period"),
        str(_optional_number_or_text(row, "update_flag") or "base"),
    ]
    return "tushare:" + ":".join(parts)


def _default_pro_client_factory(token: str) -> Any:
    try:
        import tushare as ts
    except ImportError as error:
        raise TushareDataUnavailableError(
            "tushare is not installed; install it to use Tushare Pro research"
        ) from error
    return ts.pro_api(token)


def _records(frame: Any) -> list[Mapping[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [row for row in frame if isinstance(row, Mapping)]
    if hasattr(frame, "to_dict"):
        rows = frame.to_dict("records")
        return [row for row in rows if isinstance(row, Mapping)]
    raise TushareDataUnavailableError("Tushare returned an unsupported response type")


def _daily_fundamental_snapshots(
    *,
    identity: InstrumentIdentity,
    rows: list[Mapping[str, Any]],
    availability_date: date,
    currency: str,
    source: str,
    ts_code: str,
    metric_builder: Callable[[list[Mapping[str, Any]], date], dict[str, float | int | str | None]],
) -> list[FundamentalSnapshot]:
    eligible = [
        row
        for row in rows
        if _has_trade_date(row) and _required_date(row, "trade_date") <= availability_date
    ]
    snapshots: list[FundamentalSnapshot] = []
    seen_periods: set[date] = set()
    provenance = _provenance(availability_date, source=source, vendor_symbol=ts_code)
    for row in sorted(eligible, key=lambda item: _required_date(item, "trade_date"), reverse=True):
        period_end = _required_date(row, "trade_date")
        if period_end in seen_periods:
            continue
        seen_periods.add(period_end)
        metrics = metric_builder([row], availability_date)
        if not metrics:
            continue
        snapshots.append(
            FundamentalSnapshot(
                symbol=identity.symbol,
                period_end=period_end,
                fiscal_period="daily_snapshot",
                currency=currency,
                metrics=metrics,
                provenance=provenance,
            )
        )
    return snapshots


def _a_share_metrics(
    rows: list[Mapping[str, Any]], as_of_date: date
) -> dict[str, float | int | str | None]:
    row = _latest_row(rows, as_of_date)
    if row is None:
        return {}
    return _metrics_from_row(
        row,
        {
            "pe": "pe_ratio",
            "pe_ttm": "pe_ratio_ttm",
            "pb": "price_to_book",
            "ps": "price_to_sales",
            "ps_ttm": "price_to_sales_ttm",
            "dv_ratio": "dividend_yield_pct",
            "turnover_rate": "turnover_rate_pct",
            "total_mv": "total_market_value_10k_cny",
            "circ_mv": "circulating_market_value_10k_cny",
        },
    )


def _hk_metrics(
    rows: list[Mapping[str, Any]], as_of_date: date
) -> dict[str, float | int | str | None]:
    row = _latest_row(rows, as_of_date)
    if row is None:
        return {}
    return _metrics_from_row(
        row,
        {
            "turnover_ratio": "turnover_rate_pct",
            "total_mv": "total_market_value_raw",
            "free_mv": "free_float_market_value_raw",
            "total_share": "total_share_raw",
            "free_share": "free_share_raw",
        },
    )


def _latest_row(rows: list[Mapping[str, Any]], as_of_date: date) -> Mapping[str, Any] | None:
    eligible = [
        row
        for row in rows
        if _has_trade_date(row) and _required_date(row, "trade_date") <= as_of_date
    ]
    return max(eligible, key=lambda row: _required_date(row, "trade_date"), default=None)


def _metrics_from_row(
    row: Mapping[str, Any], mapping: Mapping[str, str]
) -> dict[str, float | int | str | None]:
    return {
        target: value
        for source, target in mapping.items()
        if (value := _optional_number_or_text(row, source)) is not None
    }


def _currency_for(ts_code: str) -> str:
    return "HKD" if ts_code.endswith(".HK") else "CNY"


def _provenance(as_of_date: date, *, source: str, vendor_symbol: str) -> DataProvenance:
    return DataProvenance(
        provider=TushareProProvider.name,
        as_of_date=as_of_date,
        retrieved_at=datetime.now(timezone.utc),
        source=source,
        vendor_symbol=vendor_symbol,
    )


def _has_trade_date(row: Mapping[str, Any]) -> bool:
    return bool(row.get("trade_date"))


def _required_date(row: Mapping[str, Any], field: str) -> date:
    value = row.get(field)
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError as error:
            raise TushareDataUnavailableError(f"invalid Tushare {field}: {value}") from error
    raise TushareDataUnavailableError(f"missing Tushare {field}")


def _optional_date(row: Mapping[str, Any], field: str) -> date | None:
    value = row.get(field)
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _required_float(row: Mapping[str, Any], field: str) -> float:
    value = _optional_float(row, field)
    if value is None:
        raise TushareDataUnavailableError(f"missing Tushare {field}")
    return value


def _optional_float(row: Mapping[str, Any], field: str) -> float | None:
    value = row.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if isnan(parsed) else parsed


def _optional_int(row: Mapping[str, Any], field: str) -> int | None:
    value = _optional_float(row, field)
    return int(value) if value is not None else None


def _optional_number_or_text(row: Mapping[str, Any], field: str) -> float | int | str | None:
    value = row.get(field)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and isnan(value):
        return None
    if isinstance(value, int | float | str):
        return value
    return None
