"""
Crawl4AI Document Extraction Client.

Provides web crawling and document extraction for financial documents
like 10-Ks, transcripts, and reports using Crawl4AI.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class FinancialDocument(BaseModel):
    """Extracted financial document."""

    url: str = Field(description="Source URL")
    title: str = Field(description="Document title")
    doc_type: str = Field(description="Document type (10-K, 10-Q, transcript, etc.)")
    company: str = Field(description="Company name")
    ticker: str | None = Field(default=None, description="Ticker symbol")
    date: str | None = Field(default=None, description="Document date")
    content: str = Field(description="Extracted content in Markdown")
    metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=datetime.now)


class Crawl4AIClient:
    """Client for Crawl4AI document extraction."""

    def __init__(
        self,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
    ):
        """
        Initialize Crawl4AI client.

        Args:
            llm_provider: LLM provider for extraction (e.g., 'openai/gpt-4o')
                         If not provided, uses CSS extraction only.
            llm_api_key: API key for LLM provider
        """
        self.llm_provider = llm_provider or os.environ.get("CRAWL4AI_LLM_PROVIDER")
        self.llm_api_key = llm_api_key or os.environ.get("CRAWL4AI_LLM_API_KEY")

    async def extract_document(
        self,
        url: str,
        doc_type: str = "auto",
        company: str | None = None,
        ticker: str | None = None,
    ) -> FinancialDocument:
        """
        Extract a financial document from URL.

        Args:
            url: URL to extract from
            doc_type: Document type (10-K, 10-Q, transcript, report, auto)
            company: Company name (if known)
            ticker: Ticker symbol (if known)

        Returns:
            Extracted FinancialDocument
        """
        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
            from crawl4ai import JsonCssExtractionStrategy, LLMExtractionStrategy, LLMConfig
        except ImportError:
            raise ImportError(
                "Crawl4AI not installed. Run: pip install crawl4ai && crawl4ai-setup"
            )

        # Determine extraction strategy
        if self.llm_provider and self.llm_api_key:
            extraction_strategy = LLMExtractionStrategy(
                llm_config=LLMConfig(
                    provider=self.llm_provider,
                    api_token=self.llm_api_key,
                ),
                schema=FinancialDocument.model_json_schema(),
                extraction_type="schema",
                instruction=self._get_extraction_instruction(doc_type),
                input_format="markdown",
            )
        else:
            # Use CSS extraction as fallback
            extraction_strategy = self._get_css_strategy(doc_type)

        # Configure crawler
        browser_config = BrowserConfig(headless=True, verbose=False)
        run_config = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            word_count_threshold=100,
        )

        # Crawl and extract
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

            if not result.success:
                raise Exception(f"Crawl failed: {result.error_message}")

            # Parse extracted content
            extracted = json.loads(result.extracted_content) if result.extracted_content else {}

            return FinancialDocument(
                url=url,
                title=extracted.get("title", result.metadata.get("title", "Unknown")),
                doc_type=extracted.get("doc_type", doc_type),
                company=extracted.get("company", company or "Unknown"),
                ticker=extracted.get("ticker", ticker),
                date=extracted.get("date"),
                content=result.markdown,
                metadata=extracted,
            )

    async def extract_10k(
        self,
        ticker: str,
        year: int | None = None,
    ) -> FinancialDocument:
        """
        Extract 10-K filing for a company.

        Args:
            ticker: Company ticker
            year: Fiscal year (if None, most recent)

        Returns:
            Extracted 10-K document
        """
        # SEC EDGAR URL pattern
        cik = await self._get_cik(ticker)
        if not cik:
            raise ValueError(f"Could not find CIK for {ticker}")

        # Search for 10-K filing
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb=&owner=include&count=10"

        return await self.extract_document(
            url=url,
            doc_type="10-K",
            ticker=ticker,
        )

    async def extract_transcript(
        self,
        url: str,
        company: str | None = None,
    ) -> FinancialDocument:
        """
        Extract earnings transcript.

        Args:
            url: Transcript URL
            company: Company name

        Returns:
            Extracted transcript
        """
        return await self.extract_document(
            url=url,
            doc_type="transcript",
            company=company,
        )

    async def extract_report(
        self,
        url: str,
        report_type: str = "analyst",
    ) -> FinancialDocument:
        """
        Extract analyst/report document.

        Args:
            url: Report URL
            report_type: Type of report

        Returns:
            Extracted report
        """
        return await self.extract_document(
            url=url,
            doc_type=f"report-{report_type}",
        )

    async def extract_batch(
        self,
        urls: list[str],
        doc_type: str = "auto",
    ) -> list[FinancialDocument]:
        """
        Extract multiple documents in parallel.

        Args:
            urls: List of URLs to extract
            doc_type: Document type

        Returns:
            List of extracted documents
        """
        tasks = [
            self.extract_document(url, doc_type)
            for url in urls
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def _get_extraction_instruction(self, doc_type: str) -> str:
        """Get extraction instruction based on document type."""
        instructions = {
            "10-K": (
                "Extract key financial data from this 10-K filing: "
                "revenue, net income, total assets, total liabilities, "
                "cash flow from operations, and any material risks mentioned. "
                "Include the fiscal year and filing date."
            ),
            "10-Q": (
                "Extract quarterly financial data from this 10-Q filing: "
                "revenue, net income, total assets, total liabilities. "
                "Include the quarter and filing date."
            ),
            "transcript": (
                "Extract key information from this earnings transcript: "
                "revenue guidance, EPS guidance, key metrics mentioned, "
                "management commentary, and any notable quotes."
            ),
            "auto": (
                "Extract all relevant financial information from this document. "
                "Include company name, ticker, date, key financial metrics, "
                "and any important notes or risks."
            ),
        }
        return instructions.get(doc_type, instructions["auto"])

    def _get_css_strategy(self, doc_type: str):
        """Get CSS extraction strategy as fallback."""
        from crawl4ai import JsonCssExtractionStrategy

        # Basic CSS schema for financial documents
        schema = {
            "baseSelector": "body",
            "fields": [
                {"name": "title", "selector": "title", "type": "text"},
                {"name": "content", "selector": "article, .content, main", "type": "text"},
            ],
        }
        return JsonCssExtractionStrategy(schema=schema)

    async def _get_cik(self, ticker: str) -> str | None:
        """Get CIK number for a ticker from SEC EDGAR."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://www.sec.gov/cgi-bin/browse-edgar"
                    f"?action=getcompany&company={ticker}&CIK=&type=10-K&dateb=&owner=include&count=10&search_text=&action=getcompany",
                    headers={"User-Agent": "TradingAgents/1.0"},
                )
                # Parse CIK from response (simplified)
                text = response.text
                if "CIK" in text:
                    # Extract CIK number
                    import re
                    match = re.search(r"CIK=(\d+)", text)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        return None


# Global instance
_crawl4ai_client: Crawl4AIClient | None = None


def get_crawl4ai_client() -> Crawl4AIClient:
    """Get or create the global Crawl4AI client."""
    global _crawl4ai_client
    if _crawl4ai_client is None:
        _crawl4ai_client = Crawl4AIClient()
    return _crawl4ai_client
