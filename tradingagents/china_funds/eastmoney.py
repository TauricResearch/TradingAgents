"""Minimal public Eastmoney adapter with explicit dates and no automatic retry."""

from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from tradingagents.dataflows.errors import ProviderRateLimitedError, ProviderTimedOutError
from tradingagents.domain import EvidenceField

from .domain import Benchmark, FeeRule, NavPoint, TransactionStatus
from .providers import CapabilityResult

SEARCH_URL = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
DETAIL_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"
STATUS_URL = "https://fund.eastmoney.com/Data/Fund_JJJZ_Data.aspx"
PROFILE_URL = "https://fundf10.eastmoney.com/jbgk_{code}.html"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def _plain_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))).strip()


def _decimal_text(value: Any) -> str | None:
    try:
        return format(Decimal(str(value)), "f")
    except (InvalidOperation, TypeError, ValueError):
        return None


def _evidence(
    name: str,
    value: Any,
    *,
    reference: str,
    retrieved_at: str,
    effective_at: str | None,
    raw_hash: str,
    unit: str | None = None,
    freshness: str = "unchecked",
    warnings: tuple[str, ...] = (),
) -> EvidenceField:
    return EvidenceField(
        name,
        value,
        unit,
        str(uuid.uuid4()),
        reference,
        retrieved_at,
        None,
        effective_at,
        raw_hash,
        freshness,
        warnings,
    )


def _js_variable(content: str, name: str) -> Any:
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*(.*?);", content, re.DOTALL)
    if not match:
        return None
    raw = match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip('"')


def _profile_fields(content: str) -> dict[str, str]:
    table = re.search(r'<table class="info w790">(.*?)</table>', content, re.DOTALL)
    if not table:
        return {}
    cells = re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", table.group(1), re.DOTALL)
    return {_plain_html(key): _plain_html(value) for key, value in cells}


class EastmoneyFundProvider:
    """Capability adapter for public pages used by the AKShare fund adapters."""

    provider_id = "eastmoney_public"

    def __init__(self, *, timeout_seconds: float = 10, http_get=requests.get):
        self.timeout_seconds = timeout_seconds
        self.http_get = http_get

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> tuple[str, str]:
        observed = _now()
        try:
            response = self.http_get(url, params=params, timeout=self.timeout_seconds)
        except requests.Timeout as exc:
            raise ProviderTimedOutError(
                self.provider_id, timeout_seconds=self.timeout_seconds
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError("PUBLIC_FUND_PROVIDER_UNAVAILABLE") from exc
        if response.status_code == 429:
            raise ProviderRateLimitedError(
                self.provider_id,
                retry_after=response.headers.get("Retry-After"),
            )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text.lstrip("\ufeff"), observed

    def _search(self, code: str) -> tuple[dict[str, Any], str, str]:
        content, observed = self._get(SEARCH_URL, params={"m": "1", "key": code})
        payload = json.loads(content)
        candidates = [item for item in payload.get("Datas") or [] if item.get("CODE") == code]
        if not candidates:
            return {}, content, observed
        return candidates[0], content, observed

    def _detail(self, code: str) -> tuple[str, str]:
        return self._get(DETAIL_URL.format(code=code))

    def _profile(self, code: str) -> tuple[dict[str, str], str, str]:
        content, observed = self._get(PROFILE_URL.format(code=code))
        return _profile_fields(content), content, observed

    def fetch_identity(self, code: str) -> CapabilityResult:
        item, content, observed = self._search(code)
        if not item:
            return CapabilityResult(None)
        base = item.get("FundBaseInfo") or {}
        value = {
            "code": code,
            "display_name": item.get("NAME") or base.get("SHORTNAME"),
            "provider_fund_type": base.get("FTYPE"),
            "fund_company": base.get("JJGS"),
            "manager_name": base.get("JJJL"),
            "currency": "CNY",
        }
        reference = f"{SEARCH_URL}?m=1&key={code}"
        evidence = tuple(
            _evidence(
                f"identity.{key}",
                field,
                reference=reference,
                retrieved_at=observed,
                effective_at=observed[:10],
                raw_hash=_hash(content),
            )
            for key, field in value.items()
        )
        return CapabilityResult(value, evidence)

    def fetch_nav(self, code: str, analysis_date: str) -> CapabilityResult:
        content, observed = self._detail(code)
        trend = _js_variable(content, "Data_netWorthTrend") or []
        accumulated = {
            int(item[0]): item[1] for item in (_js_variable(content, "Data_ACWorthTrend") or [])
        }
        points: list[NavPoint] = []
        for item in trend:
            timestamp = int(item.get("x", 0))
            nav_date = datetime.fromtimestamp(timestamp / 1000, tz=UTC).date().isoformat()
            if nav_date > analysis_date:
                continue
            nav = _decimal_text(item.get("y"))
            if nav is not None:
                points.append(NavPoint(nav_date, nav, _decimal_text(accumulated.get(timestamp))))
        points.sort(key=lambda item: item.date)
        reference = DETAIL_URL.format(code=code)
        latest_date = points[-1].date if points else None
        evidence = (
            _evidence(
                "nav_history",
                [item.__dict__ for item in points],
                reference=reference,
                retrieved_at=observed,
                effective_at=latest_date,
                raw_hash=_hash(content),
                unit="CNY_per_unit",
            ),
        )
        return CapabilityResult(tuple(points), evidence)

    def fetch_transaction_status(self, code: str) -> CapabilityResult:
        params = {
            "t": "1",
            "lx": "1",
            "letter": "",
            "gsid": "",
            "text": code,
            "sort": "zdf,desc",
            "page": "1,10",
            "atfc": "",
            "onlySale": "0",
        }
        content, observed = self._get(STATUS_URL, params=params)
        rows_match = re.search(r"datas:(\[.*?\]),count:", content, re.DOTALL)
        dates_match = re.search(r"showday:(\[.*?\])\s*}", content, re.DOTALL)
        rows = json.loads(rows_match.group(1)) if rows_match else []
        dates = json.loads(dates_match.group(1)) if dates_match else []
        row = next((item for item in rows if item and item[0] == code), None)
        if not row:
            return CapabilityResult(None, warnings=("TRANSACTION_STATUS_UNAVAILABLE",))
        value = TransactionStatus(
            subscription=str(row[9] or "unknown"),
            redemption=str(row[10] or "unknown"),
            observed_at=observed,
        )
        reference = f"{STATUS_URL}?text={code}"
        effective = dates[0] if dates else observed[:10]
        evidence = (
            _evidence(
                "transaction_status.subscription",
                value.subscription,
                reference=reference,
                retrieved_at=observed,
                effective_at=effective,
                raw_hash=_hash(content),
            ),
            _evidence(
                "transaction_status.redemption",
                value.redemption,
                reference=reference,
                retrieved_at=observed,
                effective_at=effective,
                raw_hash=_hash(content),
            ),
        )
        return CapabilityResult(value, evidence)

    def fetch_fees(self, code: str) -> CapabilityResult:
        detail, observed = self._detail(code)
        profile, profile_content, profile_observed = self._profile(code)
        rules: list[FeeRule] = []
        purchase_rate = _js_variable(detail, "fund_sourceRate")
        minimum = _js_variable(detail, "fund_minsg")
        if purchase_rate not in (None, ""):
            rules.append(
                FeeRule(
                    "subscribe", f"minimum_amount={minimum or 'unknown'} CNY", f"{purchase_rate}%"
                )
            )
        redemption_rate = profile.get("最高赎回费率")
        if redemption_rate:
            rules.append(
                FeeRule("redeem", "maximum; holding-period tiers unavailable", redemption_rate)
            )
        content_hash = _hash(detail + profile_content)
        reference = PROFILE_URL.format(code=code)
        evidence = (
            _evidence(
                "fees",
                [item.__dict__ for item in rules],
                reference=reference,
                retrieved_at=max(observed, profile_observed),
                effective_at=max(observed, profile_observed)[:10],
                raw_hash=content_hash,
                freshness="unchecked",
                warnings=("APPROXIMATE_FEE_RULES",),
            ),
        )
        warnings = () if rules else ("FEE_RULE_UNKNOWN",)
        if redemption_rate:
            warnings += ("REDEMPTION_HOLDING_PERIOD_RULE_UNKNOWN",)
        return CapabilityResult(tuple(rules), evidence, warnings)

    def fetch_disclosure(self, code: str) -> CapabilityResult:
        content, observed = self._detail(code)
        managers = _js_variable(content, "Data_currentFundManager") or []
        allocation = _js_variable(content, "Data_assetAllocation") or {}
        categories = allocation.get("categories") or []
        disclosure_date = categories[-1] if categories else None
        asset_allocation: dict[str, str] = {}
        for item in allocation.get("series") or []:
            values = item.get("data") or []
            if values and values[-1] is not None:
                asset_allocation[str(item.get("name"))] = _decimal_text(values[-1]) or ""
        value = {
            "manager": managers[0] if managers else {},
            "holdings": (),
            "sector_allocation": {},
            "asset_allocation": asset_allocation,
            "disclosure_date": disclosure_date,
        }
        reference = DETAIL_URL.format(code=code)
        evidence = (
            _evidence(
                "manager",
                value["manager"] or None,
                reference=reference,
                retrieved_at=observed,
                effective_at=observed[:10],
                raw_hash=_hash(content),
            ),
            _evidence(
                "asset_allocation",
                asset_allocation or None,
                reference=reference,
                retrieved_at=observed,
                effective_at=disclosure_date,
                raw_hash=_hash(content),
                unit="percent",
            ),
            _evidence(
                "holdings",
                None,
                reference=reference,
                retrieved_at=observed,
                effective_at=disclosure_date,
                raw_hash=_hash(content),
                freshness="missing",
                warnings=("HOLDINGS_UNAVAILABLE",),
            ),
        )
        return CapabilityResult(value, evidence, ("HOLDINGS_UNAVAILABLE",))

    def fetch_benchmark(self, code: str) -> CapabilityResult:
        profile, content, observed = self._profile(code)
        disclosed = profile.get("业绩比较基准")
        tracked = profile.get("跟踪标的")
        selected_name = tracked if tracked and "无跟踪标的" not in tracked else None
        value = Benchmark(disclosed, selected_name=selected_name)
        reference = PROFILE_URL.format(code=code)
        evidence = (
            _evidence(
                "benchmark.disclosed_text",
                disclosed,
                reference=reference,
                retrieved_at=observed,
                effective_at=observed[:10],
                raw_hash=_hash(content),
                freshness="fresh" if disclosed else "missing",
            ),
            _evidence(
                "benchmark.tracked_index",
                selected_name,
                reference=reference,
                retrieved_at=observed,
                effective_at=observed[:10],
                raw_hash=_hash(content),
                freshness="fresh" if selected_name else "missing",
            ),
        )
        return CapabilityResult(value, evidence, () if disclosed else ("BENCHMARK_UNAVAILABLE",))
