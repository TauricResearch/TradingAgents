"""
PDF Generator for TradingAgents Analysis Reports

This module generates PDF reports from analysis results using WeasyPrint.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except (ImportError, OSError) as e:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning(f"Playwright not available: {str(e)}. Trying WeasyPrint fallback.")

try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    WEASYPRINT_AVAILABLE = False
    HTML = None
    CSS = None
    FontConfiguration = None
    if not PLAYWRIGHT_AVAILABLE:
        logging.warning(f"WeasyPrint also not available: {str(e)}. PDF generation will be disabled.")

from ..converters.html_converter import RichToHTMLConverter
from ..formatters.report_formatter import ReportFormatter


class TradingReportPDFGenerator:
    """Generates PDF reports from TradingAgents analysis results."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize PDF generator.
        
        Args:
            config: Configuration dictionary for PDF generation
        """
        self.config = config or self._default_config()
        self.html_converter = RichToHTMLConverter()
        self.report_formatter = ReportFormatter()
        self.logger = logging.getLogger(__name__)
        
        if not WEASYPRINT_AVAILABLE:
            self.logger.warning("WeasyPrint not available. PDF generation disabled.")
    
    def _default_config(self) -> Dict[str, Any]:
        """Get default PDF generation configuration."""
        return {
            "enabled": True,
            "output_dir": "results",
            "page_format": "A4",
            "margin": "2cm",
            "font_family": "Arial, sans-serif",
            "font_size": "12pt"
        }
    
    def generate_pdf(self, analysis_results: Dict[str, Any], ticker: str, 
                    date: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Generate PDF report from analysis results.
        
        Args:
            analysis_results: Complete analysis results dictionary
            ticker: Stock ticker symbol
            date: Analysis date
            output_path: Optional custom output path
            
        Returns:
            Path to generated PDF file, or None if generation failed
        """
        if not self.is_available():
            self.logger.error("No PDF generation method available.")
            return None
        
        if not self.config.get("enabled", True):
            self.logger.info("PDF generation disabled in configuration.")
            return None
        
        try:
            # Generate output path if not provided
            if not output_path:
                output_path = self._generate_output_path(ticker, date)
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Format the report content
            html_content = self._create_html_report(analysis_results, ticker, date)
            
            # Generate PDF using available method
            success = self._html_to_pdf(html_content, output_path)
            
            if success:
                # Also save HTML backup
                html_path = output_path.replace('.pdf', '.html')
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                self.logger.info(f"PDF report generated: {output_path}")
                return output_path
            else:
                return None
            
        except Exception as e:
            self.logger.error(f"Failed to generate PDF report: {str(e)}")
            return None
    
    def _generate_output_path(self, ticker: str, date: str) -> str:
        """Generate output path for PDF file."""
        output_dir = Path(self.config["output_dir"]) / ticker / date
        return str(output_dir / "analysis_report.pdf")
    
    def _create_html_report(self, analysis_results: Dict[str, Any], 
                           ticker: str, date: str) -> str:
        """
        Create complete HTML report from analysis results.
        
        Args:
            analysis_results: Analysis results dictionary
            ticker: Stock ticker symbol
            date: Analysis date
            
        Returns:
            Complete HTML content for PDF generation
        """
        # Format the main report content
        report_content = self.report_formatter.format_complete_report(
            analysis_results, ticker, date
        )
        
        # Wrap in complete HTML document with styles
        html_template = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TradingAgents Analysis: {ticker}</title>
            {self._get_pdf_styles()}
        </head>
        <body>
            {report_content}
            <div class="footer">
                <p>Generated by TradingAgents on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """
        
        return html_template
    
    def _get_pdf_styles(self) -> str:
        """Get CSS styles for PDF generation."""
        return """
        <style>
            @page {
                size: A4;
                margin: 2cm;
                @bottom-center {
                    content: "Page " counter(page) " of " counter(pages);
                    font-size: 10pt;
                    color: #666;
                }
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 11pt;
                line-height: 1.5;
                color: #333;
                margin: 0;
                padding: 0;
            }
            
            .cover-page {
                text-align: center;
                padding: 100px 0;
                margin-bottom: 50px;
            }
            
            .report-title {
                font-size: 28pt;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 30px;
            }
            
            .ticker-symbol {
                font-size: 36pt;
                font-weight: bold;
                color: #3498db;
                margin: 30px 0;
            }
            
            .analysis-date, .generated-date {
                font-size: 14pt;
                color: #666;
                margin: 10px 0;
            }
            
            .section {
                margin: 30px 0;
                page-break-inside: avoid;
            }
            
            .section-header {
                font-size: 18pt;
                font-weight: bold;
                color: #2980b9;
                margin: 30px 0 15px 0;
                border-bottom: 2px solid #2980b9;
                padding-bottom: 5px;
            }
            
            .panel {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin: 15px 0;
                padding: 20px;
                background-color: #fafafa;
                page-break-inside: avoid;
            }
            
            .panel-title {
                font-weight: bold;
                font-size: 14pt;
                color: #2c3e50;
                margin-bottom: 15px;
                border-bottom: 1px solid #eee;
                padding-bottom: 8px;
            }
            
            .recommendation {
                font-weight: bold;
                font-size: 20pt;
                color: #27ae60;
                text-align: center;
                margin: 25px 0;
                padding: 15px;
                border: 3px solid #27ae60;
                border-radius: 10px;
                background-color: #f8f9fa;
            }
            
            .page-break {
                page-break-before: always;
            }
            
            .footer {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                text-align: center;
                font-size: 9pt;
                color: #666;
                padding: 10px;
            }
            
            p {
                margin: 10px 0;
                text-align: justify;
            }
            
            ul {
                margin: 10px 0;
                padding-left: 20px;
            }
            
            li {
                margin: 5px 0;
            }
            
            strong {
                font-weight: bold;
                color: #2c3e50;
            }
            
            em {
                font-style: italic;
                color: #555;
            }
            
            .executive-content,
            .analyst-content,
            .research-content,
            .trading-content,
            .final-decision-content {
                line-height: 1.6;
            }
        </style>
        """
    
    def _html_to_pdf(self, html_content: str, output_path: str) -> bool:
        """
        Convert HTML content to PDF using available method.
        
        Args:
            html_content: HTML content to convert
            output_path: Output PDF file path
            
        Returns:
            True if successful, False otherwise
        """
        # Try Playwright first (preferred method)
        if PLAYWRIGHT_AVAILABLE:
            try:
                return self._html_to_pdf_playwright(html_content, output_path)
            except Exception as e:
                self.logger.warning(f"Playwright PDF generation failed: {str(e)}. Trying WeasyPrint fallback.")
        
        # Fallback to WeasyPrint
        if WEASYPRINT_AVAILABLE:
            try:
                return self._html_to_pdf_weasyprint(html_content, output_path)
            except Exception as e:
                self.logger.error(f"WeasyPrint PDF generation also failed: {str(e)}")
        
        return False
    
    def _html_to_pdf_playwright(self, html_content: str, output_path: str) -> bool:
        """
        Convert HTML content to PDF using Playwright.
        
        Args:
            html_content: HTML content to convert
            output_path: Output PDF file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Set content and wait for it to load
                page.set_content(html_content, wait_until='networkidle')
                
                # Generate PDF with options
                page.pdf(
                    path=output_path,
                    format='A4',
                    margin={
                        'top': '2cm',
                        'right': '2cm',
                        'bottom': '2cm',
                        'left': '2cm'
                    },
                    print_background=True,
                    display_header_footer=True,
                    header_template='<div style="font-size:10px; width:100%; text-align:center; color:#666;">TradingAgents Analysis Report</div>',
                    footer_template='<div style="font-size:10px; width:100%; text-align:center; color:#666;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'
                )
                
                browser.close()
                self.logger.info("PDF generated successfully using Playwright")
                return True
                
        except Exception as e:
            self.logger.error(f"Playwright PDF generation failed: {str(e)}")
            return False
    
    def _html_to_pdf_weasyprint(self, html_content: str, output_path: str) -> bool:
        """
        Convert HTML content to PDF using WeasyPrint.
        
        Args:
            html_content: HTML content to convert
            output_path: Output PDF file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create font configuration
            font_config = FontConfiguration()
            
            # Generate PDF
            html_doc = HTML(string=html_content)
            html_doc.write_pdf(
                output_path,
                font_config=font_config,
                optimize_images=True
            )
            
            self.logger.info("PDF generated successfully using WeasyPrint")
            return True
            
        except Exception as e:
            self.logger.error(f"WeasyPrint conversion failed: {str(e)}")
            # Try without font configuration as fallback
            try:
                html_doc = HTML(string=html_content)
                html_doc.write_pdf(output_path)
                self.logger.info("PDF generated successfully using WeasyPrint (fallback mode)")
                return True
            except Exception as fallback_error:
                self.logger.error(f"WeasyPrint fallback also failed: {str(fallback_error)}")
                return False
    
    def is_available(self) -> bool:
        """Check if PDF generation is available."""
        return (PLAYWRIGHT_AVAILABLE or WEASYPRINT_AVAILABLE) and self.config.get("enabled", True)