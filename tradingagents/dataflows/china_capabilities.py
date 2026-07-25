"""Typed, degradable adapters for A-share specialty datasets.

These adapters deliberately report *source records*, rather than quietly
turning a missing public endpoint into an investment conclusion.  AKShare is
used as a public-data transport only; its upstream sources can change without
notice, therefore an empty response, a changed schema, or an unavailable
optional package always raises :class:`AshareCapabilityUnavailableError`.

The functions in this module are intentionally separate from core OHLCV and
financial-statement routes.  They are optional research supplements, so a
failure here must not make a price/fundamentals request look unavailable.
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from .errors import VendorError
from .ticker_utils import is_a_share_ticker, normalize_ticker_symbol, to_akshare_symbol


class AshareCapabilityUnavailableError(VendorError):
    """A named A-share specialty capability could not return source records.

    ``capability`` and ``provider`` are structured attributes so the caller
    can record a truthful degradation rather than parsing a human message.
    """

    def __init__(self, capability: str, provider: str, detail: str) -> None:
        self.capability = capability
        self.provider = provider
        self.detail = detail
        super().__init__(f"A-share capability '{capability}' unavailable from {provider}: {detail}")


@dataclass(frozen=True)
class CapabilityReport:
    """Source-labelled tabular output and its explicit scope limitations."""

    capability: str
    ticker: str | None
    provider: str
    data: pd.DataFrame
    note: str

    def render(self) -> str:
        if self.data.empty:
            raise AshareCapabilityUnavailableError(self.capability, self.provider, "no usable rows")
        target = self.ticker or "market-wide"
        return "\n".join(
            [
                f"# China A-share {self.capability.replace('_', ' ')} for {target}",
                f"# Source: {self.provider}",
                f"# Note: {self.note}",
                f"# Total records: {len(self.data)}",
                "",
                self.data.to_csv(index=False),
            ]
        )


class AKShareSpecialtyProvider:
    """Public AKShare adapters with capability-specific schema guards."""

    name = "akshare"

    def __init__(self, api: Any | None = None) -> None:
        self._api = api

    def interactive_questions(self, ticker: str) -> CapabilityReport:
        code = _require_a_share_code(ticker, "interactive_questions")
        data = self._call("stock_irm_cninfo", "interactive_questions", symbol=code)
        return _report_for_ticker(
            data,
            capability="interactive_questions",
            ticker=ticker,
            provider=self.name,
            code=code,
            note="CNINFO Interactive Q&A question records through AKShare; answers require an explicit question ID.",
            filter_if_present=False,
        )

    def interactive_answers(self, question_id: str) -> CapabilityReport:
        if not str(question_id).strip():
            raise AshareCapabilityUnavailableError("interactive_answers", self.name, "question_id is required")
        data = self._call("stock_irm_ans_cninfo", "interactive_answers", symbol=str(question_id))
        if data.empty:
            raise AshareCapabilityUnavailableError("interactive_answers", self.name, "no answer records")
        return CapabilityReport(
            capability="interactive_answers",
            ticker=None,
            provider=self.name,
            data=data,
            note="CNINFO Interactive Q&A answer records through AKShare for the requested question ID.",
        )

    def iwencai_search(self, query: str) -> CapabilityReport:
        """Run an optional, source-labelled iWenCai query when pywencai exists.

        iWenCai's query grammar and anti-bot contract are owned by that
        provider.  We do not reverse engineer browser signatures: no installed
        ``pywencai`` integration therefore yields a typed degradation.
        """
        if not str(query).strip():
            raise AshareCapabilityUnavailableError("iwencai_search", "pywencai", "query is required")
        try:
            client = importlib.import_module("pywencai")
            getter: Callable[..., Any] = client.get
        except (ImportError, AttributeError) as exc:
            raise AshareCapabilityUnavailableError(
                "iwencai_search", "pywencai", "optional pywencai client is not installed or exposes no get()"
            ) from exc
        try:
            data = getter(query=str(query), loop=True)
        except Exception as exc:
            raise AshareCapabilityUnavailableError("iwencai_search", "pywencai", type(exc).__name__) from exc
        return _report_from_data(
            data,
            capability="iwencai_search",
            ticker=None,
            provider="iwencai",
            note="Natural-language query result returned by the optional pywencai client; query semantics are provider-defined.",
        )

    def _call(self, method: str, capability: str, **kwargs: Any) -> pd.DataFrame:
        api = self._api
        if api is None:
            try:
                api = importlib.import_module("akshare")
            except ImportError as exc:
                raise AshareCapabilityUnavailableError(capability, self.name, "optional akshare package is not installed") from exc
        try:
            function: Callable[..., Any] = getattr(api, method)
        except AttributeError as exc:
            raise AshareCapabilityUnavailableError(
                capability, self.name, f"installed AKShare has no {method} adapter"
            ) from exc
        try:
            result = function(**kwargs)
        except Exception as exc:
            raise AshareCapabilityUnavailableError(capability, self.name, type(exc).__name__) from exc
        if not isinstance(result, pd.DataFrame):
            raise AshareCapabilityUnavailableError(capability, self.name, "provider returned a non-tabular result")
        return result


def get_a_share_interactive_questions(ticker: str) -> str:
    return AKShareSpecialtyProvider().interactive_questions(ticker).render()


def get_a_share_interactive_answers(question_id: str) -> str:
    return AKShareSpecialtyProvider().interactive_answers(question_id).render()


def search_a_share_iwencai(query: str) -> str:
    return AKShareSpecialtyProvider().iwencai_search(query).render()


def get_cls_telegraph() -> str:
    """Cailianpress market-wide flash via the cls.cn v1 API (zero key).

    The endpoint enforces a ``sign`` query parameter, but the signature is
    fully computable locally -- ``md5(sha1(query string sorted by key))`` --
    so no API key or browser-captured token is required.  This is an
    independent backup to EastMoney global news (different source, different
    rate-limit plane); see a-stock-data SKILL.md §5.2.
    """
    page_size = 50
    params = {
        "appName": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
        "last_time": "",
        "refresh_type": "1",
        "rn": str(page_size),
    }
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()
    url = f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.cls.cn/",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise AshareCapabilityUnavailableError("cls_telegraph", "cls", type(exc).__name__) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise AshareCapabilityUnavailableError("cls_telegraph", "cls", "invalid JSON response") from exc
    roll_data = (payload.get("data") or {}).get("roll_data") or []
    rows = []
    for item in roll_data:
        ts = item.get("ctime")
        # CLS timestamps are Beijing time; pin the offset so the rendered time
        # is correct regardless of the host machine's local timezone.
        published = (
            datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
            if ts
            else ""
        )
        rows.append(
            {
                "Time": published,
                "Title": item.get("title", "") or item.get("brief", ""),
                "Content": item.get("content", "") or item.get("brief", ""),
            }
        )
    if not rows:
        raise AshareCapabilityUnavailableError("cls_telegraph", "cls", "no roll_data rows")
    _capture_vendor_raw(payload, metadata={"provider": "cls", "dataset": "cls_telegraph", "ticker": None})
    return CapabilityReport(
        capability="cls_telegraph",
        ticker=None,
        provider="cls",
        data=pd.DataFrame(rows),
        note="Cailianpress market-wide flash via cls.cn v1 API with local signing (zero key); independent backup to EastMoney global news.",
    ).render()


def _report_for_ticker(
    data: pd.DataFrame,
    *,
    capability: str,
    ticker: str,
    provider: str,
    code: str,
    note: str,
    filter_if_present: bool = True,
) -> CapabilityReport:
    if data.empty:
        raise AshareCapabilityUnavailableError(capability, provider, "no rows")
    selected = _filter_security_code(data, code) if filter_if_present else data
    if selected.empty:
        raise AshareCapabilityUnavailableError(capability, provider, f"no rows for security code {code}")
    _capture_vendor_raw(
        selected,
        metadata={"provider": provider, "dataset": capability, "ticker": normalize_ticker_symbol(ticker)},
    )
    return CapabilityReport(capability, normalize_ticker_symbol(ticker), provider, selected, note)


def _report_from_data(
    data: Any,
    *,
    capability: str,
    ticker: str | None,
    provider: str,
    note: str,
) -> CapabilityReport:
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise AshareCapabilityUnavailableError(capability, provider, "no tabular rows")
    _capture_vendor_raw(data, metadata={"provider": provider, "dataset": capability, "ticker": ticker})
    return CapabilityReport(capability, ticker, provider, data, note)


def _require_a_share_code(ticker: str, capability: str) -> str:
    canonical = normalize_ticker_symbol(ticker)
    if not is_a_share_ticker(canonical):
        raise AshareCapabilityUnavailableError(capability, "akshare", f"{ticker} is not an A-share ticker")
    return to_akshare_symbol(canonical)


def _compact_date(value: str) -> str:
    try:
        return date.fromisoformat(value[:10]).strftime("%Y%m%d")
    except (AttributeError, ValueError) as exc:
        raise AshareCapabilityUnavailableError("date", "akshare", f"invalid ISO date: {value!r}") from exc


def _filter_security_code(data: pd.DataFrame, code: str) -> pd.DataFrame:
    for column in ("证券代码", "代码", "股票代码", "SECURITY_CODE"):
        if column in data.columns:
            values = data[column].astype(str).str.extract(r"(\d{6})", expand=False)
            return data.loc[values == code].copy()
    raise AshareCapabilityUnavailableError("ticker_filter", "akshare", "provider result has no recognized security-code column")


def _capture_vendor_raw(data: Any, *, metadata: Mapping[str, Any]) -> None:
    """Avoid importing the observability package until a real request succeeds.

    ``observability`` eventually imports agent tool modules, which import the
    router.  A lazy import keeps this capability adapter usable by itself while
    preserving the existing raw-artifact contract on actual provider calls.
    """
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(data, metadata=dict(metadata))
