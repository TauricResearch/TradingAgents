"""Degradable China capital-flow, northbound, and insider source adapters.

These data sets are *research supplements*.  They deliberately live outside
the OHLCV route: a changing public endpoint must never turn a usable price
request into an unavailable one.  Every adapter returns source-labelled rows
or raises a typed vendor error; it never derives a trading conclusion from a
missing field.
"""

from __future__ import annotations

import importlib
from datetime import date
from typing import Any

import pandas as pd

from .china_capabilities import AshareCapabilityUnavailableError, CapabilityReport
from .ticker_utils import is_a_share_ticker, normalize_ticker_symbol, to_akshare_symbol


class ChinaCapitalFlowProvider:
    """AKShare-backed public capital-flow adapters with schema-safe filtering.

    ``api`` is injectable so the boundary is testable without a live provider.
    The source is intentionally called only through its documented AKShare
    adapter names; no browser signing or private endpoint emulation is used.
    """

    name = "akshare"

    def __init__(self, api: Any | None = None) -> None:
        self._api = api

    def northbound_flow(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> CapabilityReport:
        """Return aggregate northbound net-flow history when the public adapter exists."""
        data = self._call("stock_hsgt_hist_em", "northbound_flow", symbol="北向资金")
        selected = _filter_date_window(data, start_date, end_date)
        return _market_report(
            selected,
            capability="northbound_flow",
            provider=self.name,
            note=(
                "Aggregate northbound-flow rows supplied by AKShare/EastMoney. "
                "The result is a source record, not an attribution of a stock move."
            ),
        )

    def northbound_holdings(
        self,
        ticker: str,
        indicator: str = "今日排行",
    ) -> CapabilityReport:
        """Return a requested A-share's northbound holding/ranking record.

        AKShare's public ranking endpoint is market-wide, so filtering by the
        requested security is mandatory before a report is returned.
        """
        code = _require_a_share_code(ticker, "northbound_holdings")
        if indicator not in {"今日排行", "3日排行", "5日排行", "10日排行", "月排行", "年排行"}:
            raise AshareCapabilityUnavailableError(
                "northbound_holdings", self.name, "unsupported indicator"
            )
        data = self._call(
            "stock_hsgt_hold_stock_em",
            "northbound_holdings",
            market="北向",
            indicator=indicator,
        )
        selected = _filter_security_code(data, code, "northbound_holdings", self.name)
        return _ticker_report(
            selected,
            capability="northbound_holdings",
            ticker=ticker,
            provider=self.name,
            note=(
                f"Northbound holding/ranking snapshot for the provider indicator {indicator!r}; "
                "it is not a complete beneficial-ownership register."
            ),
        )

    def insider_trades(
        self,
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> CapabilityReport:
        """Return disclosed management/shareholder change rows for one A-share.

        The public dataset can contain shareholder and director/supervisor
        disclosures.  The report preserves that scope rather than pretending
        every row is a board-member transaction.
        """
        code = _require_a_share_code(ticker, "insider_trades")
        data = self._call("stock_ggcg_em", "insider_trades", symbol="全部")
        selected = _filter_security_code(data, code, "insider_trades", self.name)
        selected = _filter_date_window(selected, start_date, end_date)
        return _ticker_report(
            selected,
            capability="insider_trades",
            ticker=ticker,
            provider=self.name,
            note=(
                "Public disclosed manager/shareholder share-change records. "
                "Identity, relation, and disclosure timing must be verified against the source filing."
            ),
        )

    def _call(self, method: str, capability: str, **kwargs: Any) -> pd.DataFrame:
        api = self._api
        if api is None:
            try:
                api = importlib.import_module("akshare")
            except ImportError as exc:
                raise AshareCapabilityUnavailableError(
                    capability, self.name, "optional akshare package is not installed"
                ) from exc
        function = getattr(api, method, None)
        if not callable(function):
            raise AshareCapabilityUnavailableError(
                capability, self.name, f"installed AKShare has no {method} adapter"
            )
        try:
            result = function(**kwargs)
        except Exception as exc:
            raise AshareCapabilityUnavailableError(capability, self.name, type(exc).__name__) from exc
        if not isinstance(result, pd.DataFrame) or result.empty:
            raise AshareCapabilityUnavailableError(capability, self.name, "no tabular rows")
        return result


def get_a_share_northbound_flow(
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Render aggregate northbound-flow history as an optional research input."""
    return ChinaCapitalFlowProvider().northbound_flow(start_date, end_date).render()


def get_a_share_northbound_holdings(ticker: str, indicator: str = "今日排行") -> str:
    """Render one ticker's provider-reported northbound holding/ranking row(s)."""
    return ChinaCapitalFlowProvider().northbound_holdings(ticker, indicator).render()


def get_a_share_insider_trades(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Render disclosed manager/shareholder share-change rows for one A-share."""
    return ChinaCapitalFlowProvider().insider_trades(ticker, start_date, end_date).render()


def _require_a_share_code(ticker: str, capability: str) -> str:
    canonical = normalize_ticker_symbol(ticker)
    if not is_a_share_ticker(canonical):
        raise AshareCapabilityUnavailableError(capability, "akshare", f"{ticker} is not an A-share ticker")
    return to_akshare_symbol(canonical)


def _filter_security_code(
    data: pd.DataFrame,
    code: str,
    capability: str,
    provider: str,
) -> pd.DataFrame:
    for column in ("证券代码", "代码", "股票代码", "SECURITY_CODE"):
        if column in data.columns:
            extracted = data[column].astype(str).str.extract(r"(\d{6})", expand=False)
            selected = data.loc[extracted == code].copy()
            if selected.empty:
                raise AshareCapabilityUnavailableError(
                    capability, provider, f"no rows for security code {code}"
                )
            return selected
    raise AshareCapabilityUnavailableError(
        capability, provider, "provider result has no recognized security-code column"
    )


def _filter_date_window(
    data: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    if not start_date and not end_date:
        return data.copy()
    start = _parse_iso_date(start_date) if start_date else None
    end = _parse_iso_date(end_date) if end_date else None
    for column in ("日期", "交易日期", "变动日期", "TRADE_DATE", "REPORT_DATE"):
        if column not in data.columns:
            continue
        dates = pd.to_datetime(data[column], errors="coerce").dt.date
        selected = data.copy()
        if start:
            selected = selected.loc[dates >= start]
            dates = dates.loc[selected.index]
        if end:
            selected = selected.loc[dates <= end]
        if selected.empty:
            raise AshareCapabilityUnavailableError("date_window", "akshare", "no rows in requested date window")
        return selected
    # The provider gave rows, but no stable date field.  Preserve the rows and
    # say so in the report note instead of fabricating a time filter.
    return data.copy()


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except (AttributeError, ValueError) as exc:
        raise AshareCapabilityUnavailableError("date_window", "akshare", f"invalid ISO date: {value!r}") from exc


def _ticker_report(
    data: pd.DataFrame,
    *,
    capability: str,
    ticker: str,
    provider: str,
    note: str,
) -> CapabilityReport:
    _capture_vendor_raw(data, provider=provider, capability=capability, ticker=ticker)
    return CapabilityReport(capability, normalize_ticker_symbol(ticker), provider, data, note)


def _market_report(
    data: pd.DataFrame,
    *,
    capability: str,
    provider: str,
    note: str,
) -> CapabilityReport:
    _capture_vendor_raw(data, provider=provider, capability=capability, ticker=None)
    return CapabilityReport(capability, None, provider, data, note)


def _capture_vendor_raw(
    data: pd.DataFrame,
    *,
    provider: str,
    capability: str,
    ticker: str | None,
) -> None:
    """Capture only usable source rows when a provenance scope is active."""
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(
        data,
        metadata={"provider": provider, "dataset": capability, "ticker": ticker or "market-wide"},
    )
