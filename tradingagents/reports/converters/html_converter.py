"""
HTML Converter for Rich Console Output

This module converts Rich console output to clean HTML suitable for PDF generation.
"""

from rich.console import Console
from rich.text import Text
import re
from typing import Dict, Any, Optional


class RichToHTMLConverter:
    """Converts Rich console output to clean HTML for PDF generation."""
    
    def __init__(self):
        self.console = Console(record=True, width=120)
        
    def rich_to_html(self, console_output: str) -> str:
        """
        Convert Rich console output to clean HTML.
        
        Args:
            console_output: Raw console output with Rich formatting
            
        Returns:
            Clean HTML string suitable for PDF generation
        """
        # Create a console and export to HTML
        html_content = self.console.export_html(
            inline_styles=True,
            code_format=None
        )
        
        # Clean and optimize for PDF
        return self.clean_html_for_pdf(html_content)
    
    def clean_html_for_pdf(self, html_content: str) -> str:
        """
        Clean HTML content for better PDF rendering.
        
        Args:
            html_content: Raw HTML content from Rich export
            
        Returns:
            Cleaned HTML content
        """
        # Remove background colors that don't work well in PDF
        html_content = re.sub(r'background-color:\s*#[0-9a-fA-F]{6};?', '', html_content)
        
        # Ensure good contrast for text
        html_content = re.sub(r'color:\s*#[0-9a-fA-F]{6};?', 'color: #333333;', html_content)
        
        # Remove excessive margins and padding
        html_content = re.sub(r'margin:\s*\d+px;?', 'margin: 5px;', html_content)
        html_content = re.sub(r'padding:\s*\d+px;?', 'padding: 3px;', html_content)
        
        return html_content
    
    def apply_pdf_styles(self, html_content: str) -> str:
        """
        Apply PDF-specific styles to HTML content.
        
        Args:
            html_content: HTML content to style
            
        Returns:
            HTML content with PDF-optimized styles
        """
        pdf_styles = """
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 12pt;
                line-height: 1.4;
                color: #333333;
                margin: 0;
                padding: 20px;
            }
            .panel {
                border: 1px solid #ddd;
                border-radius: 5px;
                margin: 10px 0;
                padding: 15px;
                background-color: #fafafa;
            }
            .panel-title {
                font-weight: bold;
                font-size: 14pt;
                color: #2c3e50;
                margin-bottom: 10px;
                border-bottom: 1px solid #eee;
                padding-bottom: 5px;
            }
            .recommendation {
                font-weight: bold;
                font-size: 16pt;
                color: #27ae60;
                text-align: center;
                margin: 20px 0;
                padding: 10px;
                border: 2px solid #27ae60;
                border-radius: 5px;
            }
            .section-header {
                font-size: 18pt;
                font-weight: bold;
                color: #2980b9;
                margin: 30px 0 15px 0;
                border-bottom: 2px solid #2980b9;
                padding-bottom: 5px;
            }
            @page {
                size: A4;
                margin: 2cm;
            }
            .page-break {
                page-break-before: always;
            }
        </style>
        """
        
        # Insert styles into HTML head
        if '<head>' in html_content:
            html_content = html_content.replace('<head>', f'<head>{pdf_styles}')
        else:
            html_content = f'<html><head>{pdf_styles}</head><body>{html_content}</body></html>'
            
        return html_content