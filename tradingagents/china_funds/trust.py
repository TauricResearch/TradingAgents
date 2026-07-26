"""Deterministic China public-fund freshness and trust rules."""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from tradingagents.domain import TrustLevel

from .domain import ChinaFundSnapshot, MarketScope

SHANGHAI = ZoneInfo("Asia/Shanghai")

# Shanghai Stock Exchange published closure dates. Weekends are handled
# separately. Dates outside this window remain conservative weekday estimates.
SSE_HOLIDAYS = frozenset(
    date.fromisoformat(value)
    for value in (
        "2025-01-01",
        "2025-01-28",
        "2025-01-29",
        "2025-01-30",
        "2025-01-31",
        "2025-02-03",
        "2025-02-04",
        "2025-04-04",
        "2025-05-01",
        "2025-05-02",
        "2025-05-05",
        "2025-06-02",
        "2025-10-01",
        "2025-10-02",
        "2025-10-03",
        "2025-10-06",
        "2025-10-07",
        "2025-10-08",
        "2026-01-01",
        "2026-01-02",
        "2026-02-16",
        "2026-02-17",
        "2026-02-18",
        "2026-02-19",
        "2026-02-20",
        "2026-02-23",
        "2026-04-06",
        "2026-05-01",
        "2026-05-04",
        "2026-05-05",
        "2026-06-19",
        "2026-09-25",
        "2026-10-01",
        "2026-10-02",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
    )
)


def relevant_trading_days_between(
    start: date, end: date, *, holidays: Collection[date] = SSE_HOLIDAYS
) -> int:
    if end <= start:
        return 0
    return sum(
        1
        for offset in range(1, (end - start).days + 1)
        if date.fromordinal(start.toordinal() + offset).weekday() < 5
        and date.fromordinal(start.toordinal() + offset) not in holidays
    )


def assess_snapshot(snapshot: ChinaFundSnapshot) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = list(snapshot.warnings)
    critical = False

    identity_evidence = any(item.name.startswith("identity") for item in snapshot.evidence)
    if (
        not snapshot.identity.code
        or not identity_evidence
        or snapshot.capability_status.get("identity") == "expired"
    ):
        reasons.append("IDENTITY_UNVERIFIED")
        critical = True

    latest_nav = snapshot.nav_history[-1] if snapshot.nav_history else None
    nav_lag: int | None = None
    if latest_nav is None:
        reasons.append("NAV_MISSING")
        critical = True
    else:
        nav_lag = relevant_trading_days_between(
            date.fromisoformat(latest_nav.date), date.fromisoformat(snapshot.analysis_date)
        )
        threshold = 5 if snapshot.identity.market_scope == MarketScope.QDII else 2
        if snapshot.capability_status.get("nav") == "expired" or nav_lag > threshold:
            reasons.append("NAV_STALE")
            critical = True
        elif snapshot.identity.market_scope == MarketScope.QDII and nav_lag > 0:
            reasons.append("QDII_DATA_LAG")
            warnings.append(f"QDII NAV publication lag is {nav_lag} relevant trading day(s).")

    status = snapshot.transaction_status
    local_today = datetime.now(SHANGHAI).date()
    if status is None:
        reasons.append("TRANSACTION_STATUS_MISSING")
        critical = True
    else:
        observed_day = datetime.fromisoformat(status.observed_at).astimezone(SHANGHAI).date()
        if (
            observed_day != local_today
            or snapshot.capability_status.get("transaction_status") == "expired"
        ):
            reasons.append("TRANSACTION_STATUS_STALE")
            critical = True

    if not snapshot.holdings:
        reasons.append("HOLDINGS_UNAVAILABLE")
        warnings.append("Latest holdings are unavailable; no values were inferred.")
    else:
        disclosure = next(
            (item.disclosure_date for item in snapshot.holdings if item.disclosure_date), None
        )
        if (
            disclosure
            and (date.fromisoformat(snapshot.analysis_date) - date.fromisoformat(disclosure)).days
            > 180
        ):
            reasons.append("HOLDINGS_DISCLOSURE_OLD")
            warnings.append("Holdings are from an older published reporting period.")

    if not snapshot.benchmark or not snapshot.benchmark.disclosed_text:
        reasons.append("BENCHMARK_UNAVAILABLE")
        warnings.append("Relative benchmark metrics are unavailable; no benchmark was invented.")

    if critical:
        level = TrustLevel.INSUFFICIENT
    elif reasons:
        level = TrustLevel.USABLE_WITH_WARNING
    else:
        level = TrustLevel.TRUSTED
    return {
        "level": level,
        "executable": level == TrustLevel.TRUSTED,
        "critical_ready": not critical,
        "reason_codes": list(dict.fromkeys(reasons)),
        "warnings": list(dict.fromkeys(warnings)),
        "assessed_at": datetime.now(SHANGHAI).isoformat(),
        "nav_lag_trading_days": nav_lag,
        "policy": {
            "domestic_nav_max_lag": 2,
            "qdii_nav_max_lag": 5,
            "transaction_status_local_day": True,
            "calendar": "SSE published closures for 2025-2026; weekday fallback otherwise",
            "calendar_source": "https://www.sse.com.cn/disclosure/dealinstruc/closed/",
        },
    }
