"""
Web Research Analyst — busca Google CSE em sites DeFi curados.

Estratégia de queries por categoria:
  - security:  honeypot.is, tokensniffer
  - news:      coindesk, theblock, cryptopanic, bloomberg, reuters
  - analytics: defillama, dune, geckoterminal, dexscreener, bubblemaps
  - sentiment: lunarcrush, cryptopanic
  - markets:   polymarket, hyperliquid, coinglass
  - governance: snapshot.org, tally.xyz
"""

import logging
import os
from dataclasses import dataclass

from tradingagents.dataflows.google_search_tools import (
    GoogleSearchClient,
    SearchResult,
    QuotaExceededError,
)

logger = logging.getLogger(__name__)

# Site groups for focused queries
SITE_GROUPS: dict[str, list[str]] = {
    "security": ["honeypot.is", "tokensniffer.com"],
    "news": [
        "coindesk.com",
        "theblock.co",
        "cryptopanic.com",
        "bloomberg.com",
        "reuters.com",
    ],
    "analytics": [
        "defillama.com",
        "dune.com",
        "geckoterminal.com",
        "dexscreener.com",
        "bubblemaps.io",
        "birdeye.so",
    ],
    "sentiment": ["lunarcrush.com", "cryptopanic.com"],
    "markets": [
        "polymarket.com",
        "hyperliquid.xyz",
        "coinglass.com",
        "tradingview.com",
    ],
    "governance": ["snapshot.org", "tally.xyz"],
}


def _build_site_filter(sites: list[str]) -> str:
    return " OR ".join(f"site:{s}" for s in sites)


@dataclass
class ResearchReport:
    token_name: str
    security_findings: list[SearchResult]
    news_findings: list[SearchResult]
    analytics_findings: list[SearchResult]
    sentiment_findings: list[SearchResult]
    quota_status: dict

    def to_text(self) -> str:
        """Returns a text summary consumable by an LLM agent."""
        sections = [f"## Web Research Report: {self.token_name}\n"]

        def _fmt(label: str, results: list[SearchResult]) -> str:
            if not results:
                return f"### {label}\nNenhum resultado encontrado.\n"
            lines = [f"### {label}"]
            for r in results:
                lines.append(f"- **{r.title}**\n  {r.snippet}\n  {r.link}")
            return "\n".join(lines)

        sections.append(_fmt("🔒 Segurança", self.security_findings))
        sections.append(_fmt("📰 Notícias", self.news_findings))
        sections.append(_fmt("📊 Analytics On-Chain", self.analytics_findings))
        sections.append(_fmt("💬 Sentimento", self.sentiment_findings))
        sections.append(
            f"### 📈 Quota Google Search\n"
            f"Uso hoje: {self.quota_status['usage_today']}/{self.quota_status['daily_limit']} "
            f"({'⚠️ próximo ao limite' if self.quota_status['is_near_limit'] else '✅ ok'})"
        )
        return "\n\n".join(sections)


class WebResearchAnalyst:
    """
    Analista que pesquisa em sites DeFi curados via Google Custom Search.

    Usa uma estratégia consciente de quota:
    - Agrupa queries por categoria para maximizar informação por query
    - Respeita o limite diário configurado (padrão: 95/100 free tier)
    - Aborta graciosamente se quota esgotada (não lança exceção — retorna parcial)
    """

    def __init__(self, search_client: GoogleSearchClient | None = None) -> None:
        if search_client is None:
            api_key = os.environ["GOOGLE_SEARCH_API_KEY"]
            cx = os.environ["GOOGLE_SEARCH_ENGINE_ID"]
            daily_limit = int(os.environ.get("GOOGLE_SEARCH_DAILY_LIMIT", "95"))
            search_client = GoogleSearchClient(
                api_key=api_key, cx=cx, daily_limit=daily_limit
            )
        self.client = search_client

    async def research_token(
        self, token_name: str, token_address: str | None = None
    ) -> ResearchReport:
        """
        Pesquisa completa sobre um token em sites DeFi curados.

        Usa no máximo 4 queries (uma por categoria principal):
        security, news, analytics, sentiment.

        Args:
            token_name: Nome legível do token (ex: "Solana", "BONK")
            token_address: Endereço do contrato (usado em queries de segurança)

        Returns:
            ResearchReport com findings por categoria e status da quota
        """
        security: list[SearchResult] = []
        news: list[SearchResult] = []
        analytics: list[SearchResult] = []
        sentiment: list[SearchResult] = []

        search_subject = token_address if token_address else token_name

        # Each block catches QuotaExceededError gracefully — returns partial results
        try:
            security = await self.client.search(
                f"{search_subject} {token_name} security risk",
                num=3,
                siteSearch=_build_site_filter(SITE_GROUPS["security"]),
            )
        except QuotaExceededError as e:
            logger.warning("Quota exceeded before security search: %s", e)

        try:
            news = await self.client.search(
                f"{token_name} crypto news",
                num=5,
                siteSearch=_build_site_filter(SITE_GROUPS["news"]),
            )
        except QuotaExceededError as e:
            logger.warning("Quota exceeded before news search: %s", e)

        try:
            analytics = await self.client.search(
                f"{token_name} DEX liquidity TVL analysis",
                num=4,
                siteSearch=_build_site_filter(SITE_GROUPS["analytics"]),
            )
        except QuotaExceededError as e:
            logger.warning("Quota exceeded before analytics search: %s", e)

        try:
            sentiment = await self.client.search(
                f"{token_name} sentiment community",
                num=3,
                siteSearch=_build_site_filter(SITE_GROUPS["sentiment"]),
            )
        except QuotaExceededError as e:
            logger.warning("Quota exceeded before sentiment search: %s", e)

        return ResearchReport(
            token_name=token_name,
            security_findings=security,
            news_findings=news,
            analytics_findings=analytics,
            sentiment_findings=sentiment,
            quota_status=self.client.quota_status,
        )
