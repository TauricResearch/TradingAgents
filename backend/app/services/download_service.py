"""
Download Service for Analyst Reports
Handles single PDF and multiple PDF ZIP downloads
"""
import io
import zipfile
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
    
    def _get_english_name(self, analyst_name: str) -> str:
        """
        獲取分析師的英文名稱
        
        Args:
            analyst_name: 中文分析師名稱
            
        Returns:
            英文分析師名稱
        """
        # 使用對照表，如果找不到則使用原名稱並替換空格
        return ANALYST_NAME_MAPPING.get(analyst_name, analyst_name.replace(" ", "_"))
    
    def create_single_pdf(
        self,
        analyst_name: str,
        ticker: str,
        analysis_date: str,
        report_content: str,
        price_data: list = None,
        price_stats: dict = None,
    ) -> tuple[bytes, str]:
        """
        Create a PDF for a single analyst report
        
        Args:
            analyst_name: Name of the analyst
            ticker: Stock ticker symbol
            analysis_date: Date of analysis (YYYY-MM-DD)
            report_content: Markdown formatted report content
            price_data: Optional list of price data for cover page
            price_stats: Optional price statistics for cover page
            
        Returns:
            Tuple of (PDF bytes, filename)
        """
        # Generate PDF
        pdf_bytes = self.pdf_generator.generate_analyst_report_pdf(
            analyst_name=analyst_name,
            ticker=ticker,
            analysis_date=analysis_date,
            report_content=report_content,
            price_data=price_data,
            price_stats=price_stats,
        )
        
        # Generate filename with English name: TICKER_English_Name_DATE.pdf
        english_name = self._get_english_name(analyst_name)
        filename = f"{ticker}_{english_name}_{analysis_date}.pdf"
        
        return pdf_bytes, filename
    
    def create_multiple_pdfs_zip(
        self,
        ticker: str,
        analysis_date: str,
        reports: List[Dict[str, str]],
        price_data: list = None,
        price_stats: dict = None,
    ) -> tuple[bytes, str]:
        """
        Create a ZIP file containing multiple analyst report PDFs
        
        Args:
            ticker: Stock ticker symbol
            analysis_date: Date of analysis (YYYY-MM-DD)
            reports: List of dicts with keys 'analyst_name' and 'report_content'
            price_data: Optional list of price data for cover page
            price_stats: Optional price statistics for cover page
            
        Returns:
            Tuple of (ZIP bytes, filename)
        """
        # Create in-memory ZIP file
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for report in reports:
                analyst_name = report.get('analyst_name', 'Unknown')
                report_content = report.get('report_content', '')
                
                # Skip if no content
                if not report_content:
                    continue
                
                # Generate PDF for this analyst
                pdf_bytes = self.pdf_generator.generate_analyst_report_pdf(
                    analyst_name=analyst_name,
                    ticker=ticker,
                    analysis_date=analysis_date,
                    report_content=report_content,
                    price_data=price_data,
                    price_stats=price_stats,
                )
                
                # Add to ZIP with English filename
                english_name = self._get_english_name(analyst_name)
                pdf_filename = f"{ticker}_{english_name}_{analysis_date}.pdf"
                zip_file.writestr(pdf_filename, pdf_bytes)
        
        # Get ZIP content
        zip_bytes = zip_buffer.getvalue()
        zip_buffer.close()
        
        # Generate ZIP filename: TICKER_DATE.zip
        zip_filename = f"{ticker}_{analysis_date}.zip"
        
        return zip_bytes, zip_filename


# Singleton instance
download_service = DownloadService()
