"""LangChain tool surface for KAP data."""

import json

from langchain_core.tools import tool

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.kap import KapService


@tool
def get_kap_disclosures(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    max_disclosures: int | None = None,
) -> str:
    """Get important KAP disclosures for a .IS BIST ticker as compact JSON.

    Args:
        ticker: Yahoo BIST symbol such as THYAO.IS. Other markets are rejected.
        start_date: Inclusive YYYY-MM-DD start. Defaults to 30 days before end_date.
        end_date: Inclusive YYYY-MM-DD end. Defaults to today.
        max_disclosures: Maximum significant records returned; default is configured (10).
    """
    config = get_config()
    if not config.get("kap_enabled", True):
        return (
            '{"status":"unavailable","message":"KAP entegrasyonu yapılandırmada devre dışı."}'
        )
    limit = (
        int(config.get("kap_max_disclosures", 10))
        if max_disclosures is None
        else max_disclosures
    )
    service = KapService(timeout=float(config.get("kap_timeout_seconds", 15.0)))
    try:
        result = service.get_disclosures(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            max_disclosures=limit,
            lookback_days=int(config.get("kap_lookback_days", 30)),
        )
    except (TypeError, ValueError) as exc:
        return json.dumps(
            {
                "status": "unavailable",
                "message": (
                    f"KAP sorgu parametreleri geçersiz: {exc}. "
                    "Analiz diğer verilerle devam edebilir."
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return result.to_json()
