"""
Download Service for Analyst Reports
Generates combined PDF reports with all analyst analyses
"""
import io
from typing import List, Dict, Optional
from datetime import datetime

from backend.app.services.pdf_generator import PDFGenerator


# 分析師中英文名稱對照表
ANALYST_NAME_MAPPING = {
    # 分析師組
    "市場分析師": "Market_Analyst",
    "基本面分析師": "Fundamentals_Analyst",
    "社群媒體分析師": "Social_Media_Analyst",
    "新聞分析師": "News_Analyst",
    
    # 研究員組
    "看漲研究員": "Bull_Researcher",
    "看跌研究員": "Bear_Researcher",
    
    # 風險辯論者組
    "激進分析師": "Aggressive_Debator",
    "保守分析師": "Conservative_Debator",
    "中立分析師": "Neutral_Debator",
    
    # 經理組
    "研究經理": "Research_Manager",
    "風險經理": "Risk_Manager",
    
    # 交易員
    "交易員": "Trader",
}


class DownloadService:
    """Service for handling analyst report downloads"""
    
    def __init__(self):
        """Initialize download service"""
        self.pdf_generator = PDFGenerator()
    
    def create_combined_pdf(
        self,
        ticker: str,
        analysis_date: str,
        reports: List[Dict[str, str]],
        price_data: list = None,
        price_stats: dict = None,
        language: str = "zh-TW",
    ) -> tuple[bytes, str]:
        """
        Create a single combined PDF containing all analyst reports
        
        Features:
        - Cover page with ticker and analysis date
        - Table of contents with price chart and analyst list
        - All analyst reports as separate sections
        
        Args:
            ticker: Stock ticker symbol
            analysis_date: Date of analysis (YYYY-MM-DD)
            reports: List of dicts with keys 'analyst_name' and 'report_content'
            price_data: Optional list of price data for chart
            price_stats: Optional price statistics for TOC
            language: Language for PDF labels ('en' or 'zh-TW')
            
        Returns:
            Tuple of (PDF bytes, filename)
        """
        # Define the preferred order for analysts (based on language)
        if language == "en":
            analyst_order = [
                'Market Analyst',
                'Fundamentals Analyst', 
                'Social Media Analyst',
                'News Analyst',
                'Bull Researcher',
                'Bear Researcher',
                'Aggressive Analyst',
                'Conservative Analyst',
                'Neutral Analyst',
                'Research Manager',
                'Risk Manager',
                'Trader',
            ]
        else:
            analyst_order = [
                '市場分析師',
                '基本面分析師', 
                '社群媒體分析師',
                '新聞分析師',
                '看漲研究員',
                '看跌研究員',
                '激進分析師',
                '保守分析師',
                '中立分析師',
                '研究經理',
                '風險經理',
                '交易員',
            ]
        
        # Sort reports by preferred order
        def get_order(report):
            analyst_name = report.get('analyst_name', '')
            try:
                return analyst_order.index(analyst_name)
            except ValueError:
                return len(analyst_order)  # Unknown analysts go to the end
        
        sorted_reports = sorted(reports, key=get_order)
        
        # Generate combined PDF
        pdf_bytes = self.pdf_generator.generate_combined_report_pdf(
            ticker=ticker,
            analysis_date=analysis_date,
            reports=sorted_reports,
            price_data=price_data,
            price_stats=price_stats,
            language=language,
        )
        
        # Generate filename: TICKER_Combined_Report_DATE.pdf
        filename = f"{ticker}_Combined_Report_{analysis_date}.pdf"
        
        return pdf_bytes, filename


# Singleton instance
download_service = DownloadService()
