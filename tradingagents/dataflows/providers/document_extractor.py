"""
Document Extraction Provider.

Provides web crawling and document extraction for financial documents
like 10-Ks, transcripts, and reports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from .base import DataProvider
from .crawl4ai_client import get_crawl4ai_client, FinancialDocument


class DocumentExtractionProvider(DataProvider):
    """Document extraction provider using Crawl4AI."""

    @property
    def name(self) -> str:
        return "crawl4ai"

    @property
    def supported_markets(self) -> list[str]:
        return ["US", "GLOBAL"]

    def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> Optional[pd.DataFrame]:
        """Crawl4AI doesn't provide OHLCV data."""
        return None

    def get_fundamentals(self, symbol: str) -> Optional[dict]:
        """Crawl4AI doesn't provide real-time fundamentals."""
        return None

    def get_financial_statement(
        self,
        symbol: str,
        statement_type: str,
        freq: str = "quarterly",
    ) -> Optional[pd.DataFrame]:
        """Crawl4AI doesn't provide structured financial statements."""
        return None

    async def extract_10k(
        self,
        ticker: str,
        year: int | None = None,
    ) -> Optional[FinancialDocument]:
        """
        Extract 10-K filing for a company.

        Args:
            ticker: Company ticker
            year: Fiscal year

        Returns:
            Extracted 10-K document
        """
        try:
            client = get_crawl4ai_client()
            return await client.extract_10k(ticker, year)
        except Exception as e:
            print(f"Error extracting 10-K for {ticker}: {e}")
            return None

    async def extract_transcript(
        self,
        url: str,
        company: str | None = None,
    ) -> Optional[FinancialDocument]:
        """
        Extract earnings transcript.

        Args:
            url: Transcript URL
            company: Company name

        Returns:
            Extracted transcript
        """
        try:
            client = get_crawl4ai_client()
            return await client.extract_transcript(url, company)
        except Exception as e:
            print(f"Error extracting transcript: {e}")
            return None

    async def extract_report(
        self,
        url: str,
        report_type: str = "analyst",
    ) -> Optional[FinancialDocument]:
        """
        Extract analyst/report document.

        Args:
            url: Report URL
            report_type: Type of report

        Returns:
            Extracted report
        """
        try:
            client = get_crawl4ai_client()
            return await client.extract_report(url, report_type)
        except Exception as e:
            print(f"Error extracting report: {e}")
            return None

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
        try:
            client = get_crawl4ai_client()
            return await client.extract_batch(urls, doc_type)
        except Exception as e:
            print(f"Error extracting batch: {e}")
            return []
