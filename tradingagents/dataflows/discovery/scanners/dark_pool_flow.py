"""Dark pool flow scanner — scrapes FINRA ATS anomalies from meridianfin.io."""

from typing import Any, Dict, List

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

_SOURCE_URL = "https://meridianfin.io/darkpool"


def _parse_volume(text: str) -> int:
    """Parse volume strings like '60.64M', '1.2B', '500K' into integers."""
    import re

    text = text.strip().upper().replace(",", "")
    match = re.match(r"([\d.]+)\s*([KMBT]?)", text)
    if not match:
        return 0
    value = float(match.group(1))
    suffix = match.group(2)
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    return int(value * multipliers.get(suffix, 1))


class DarkPoolFlowScanner(BaseScanner):
    """Scan for unusual off-exchange (dark pool) volume anomalies.

    Data source: meridianfin.io — daily FINRA ATS data with Z-score anomaly
    detection pre-computed. 1-day lag (FINRA settlement). No auth required.
    """

    name = "dark_pool_flow"
    pipeline = "edge"
    strategy = "institutional_accumulation"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.min_z_score = self.scanner_config.get("min_z_score", 2.0)
        self.min_dark_pool_pct = self.scanner_config.get("min_dark_pool_pct", 40.0)
        self.source_url = self.scanner_config.get("source_url", _SOURCE_URL)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("🌑 Scanning dark pool flow anomalies (meridianfin.io)...")

        try:
            rows = self._fetch_anomalies()
        except Exception as e:
            logger.warning(f"⚠️  Dark pool flow scrape failed: {e}")
            return []

        if not rows:
            logger.info("Found 0 dark pool anomalies")
            return []

        candidates = []
        for row in rows:
            z = row.get("z_score", 0.0)
            dp_pct = row.get("dark_pool_pct", 0.0)

            if z < self.min_z_score or dp_pct < self.min_dark_pool_pct:
                continue

            if z >= 4.0:
                priority = Priority.CRITICAL.value
            elif z >= 3.0:
                priority = Priority.HIGH.value
            else:
                priority = Priority.MEDIUM.value

            vol = row.get("off_exchange_vol", 0)
            candidates.append(
                {
                    "ticker": row["ticker"],
                    "source": self.name,
                    "context": (
                        f"Dark pool anomaly: {dp_pct:.1f}% off-exchange"
                        f" | Z-score {z:.2f}"
                        f" | Vol: {vol:,}"
                    ),
                    "priority": priority,
                    "strategy": self.strategy,
                    "dark_pool_pct": dp_pct,
                    "z_score": z,
                    "off_exchange_vol": vol,
                }
            )

        candidates = candidates[: self.limit]
        logger.info(f"Found {len(candidates)} dark pool anomalies")
        return candidates

    def _fetch_anomalies(self) -> List[Dict[str, Any]]:
        """Scrape the anomaly table from meridianfin.io/darkpool."""
        import re

        import requests
        from bs4 import BeautifulSoup

        # re is used for ticker validation below

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        resp = requests.get(self.source_url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find the anomaly table — look for a <table> containing ticker-like cells
        table = soup.find("table")
        if not table:
            logger.warning("No <table> found on meridianfin.io/darkpool")
            return []

        rows = []
        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 4:
                continue

            # Skip header rows
            if cells[0].lower() in ("ticker", "symbol", "#", ""):
                continue

            ticker = cells[0].upper()
            # Validate ticker format (1-5 uppercase letters)
            if not re.match(r"^[A-Z]{1,5}$", ticker):
                continue

            # Columns: Ticker | Volume | DPI (%) | Z-Score | Date | Company | OTC % | Source
            try:
                off_exchange_vol = _parse_volume(cells[1])
                dark_pool_pct = float(re.sub(r"[%,]", "", cells[2]))
                z_score = float(cells[3])
            except (IndexError, ValueError):
                continue

            rows.append(
                {
                    "ticker": ticker,
                    "off_exchange_vol": off_exchange_vol,
                    "dark_pool_pct": dark_pool_pct,
                    "z_score": z_score,
                }
            )

        return rows


SCANNER_REGISTRY.register(DarkPoolFlowScanner)
