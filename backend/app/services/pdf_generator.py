# -*- coding: utf-8 -*-
"""
PDF Generation Service for Analyst Reports
Converts markdown reports to PDF format with Chinese character support
Includes Heikin Ashi candlestick charts and volume bar charts
"""
import io
import re
import warnings
from typing import Optional, List, Dict
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import markdown

# Suppress matplotlib font warnings globally
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
import logging
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

# Matplotlib for chart generation
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import numpy as np

# Configure matplotlib to use available system fonts
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Liberation Sans', 'FreeSans', 'Helvetica', 'Arial', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False


class PDFGenerator:
    """Generate PDF reports from markdown content"""
    
    # Emoji to safe ASCII character mapping for PDF compatibility
    # STSong-Light font has issues with certain Unicode symbols
    # Using ONLY ASCII characters to ensure perfect rendering
    EMOJI_TO_UNICODE = {
        # Status & Indicators - ASCII only
        '✅': '[OK]',
        '❌': '[X]',
        '⚠️': '[!]',
        '⚡': '*',
        '🔔': 'o',
        
        # Rating & Quality - ASCII only
        '⭐': '*',
        '🌟': '*',
        '💎': '+',
        '🏆': '#',
        
        # Charts & Analytics - ASCII or empty
        '📊': '',
        '📈': '^',
        '📉': 'v',
        '📋': '-',
        '📌': '*',
        
        # Money & Business - ASCII currency letters
        '💰': '$',
        '💵': '$',
        '💴': 'Y',  # 日元
        '💶': 'E',  # 歐元
        '💷': 'P',  # 英鎊  
        '💸': '$',
        '💹': '^',
        
        # Direction & Movement - ASCII arrows
        '🚀': '^^',
        '⬆️': '^',
        '⬇️': 'v',
        '➡️': '>',
        '⬅️': '<',
        '🔼': '^',
        '🔽': 'v',
        
        # Symbols - ASCII only
        '🎯': 'o',
        '🔥': '*',
        '💡': '*',
        '⚙️': '*',
        '🔧': '>',
        '🔨': '>',
        
        # AI & Tech - remove or simple ASCII
        '🤖': '',
        '💻': '',
        '📱': '',
        '🖥️': '',
        
        # People & Roles - remove
        '👤': '',
        '👥': '',
        '🔬': '',
        '📚': '',
        
        # Time - simple ASCII
        '⏰': 'o',
        '📅': '-',
        '⏱️': 'o',
        
        # Other common emojis - ASCII or remove
        '✨': '*',
        '🎨': '',
        '📝': '-',
        '📄': '-',
        '🗂️': '=',
        '🌐': 'o',
        '🔗': '~',
        '💼': '',
    }
    """Generate PDF reports from markdown content"""
    
    def __init__(self):
        """Initialize PDF generator with Chinese font support"""
        import os
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
        # Initialize font variables
        self.custom_font = None
        self.chinese_font = None
        
        # CRITICAL FIX: Use ReportLab's built-in CID fonts for proper character spacing
        # CID fonts (Adobe-GB1, Adobe-CNS1) are specifically designed for PDF rendering
        # and don't have the character spacing issues that TTC files have
        try:
            # Method 1: Try using built-in CID fonts (best for Chinese PDFs)
            # These fonts have PERFECT character spacing without gaps
            try:
                # Try STSong-Light (for Traditional + Simplified Chinese)
                pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                self.custom_font = 'STSong-Light'
                self.chinese_font = 'STSong-Light'
                print(f"✅ Using STSong-Light CID font - Perfect Chinese character spacing")
            except:
                # Fallback to MSung-Light (Traditional Chinese)
                try:
                    pdfmetrics.registerFont(UnicodeCIDFont('MSung-Light'))
                    self.custom_font = 'MSung-Light'
                    self.chinese_font = 'MSung-Light'
                    print(f"✅ Using MSung-Light CID font - Perfect Traditional Chinese spacing")
                except:
                    # Last CID font attempt: STSongStd-Light
                    try:
                        pdfmetrics.registerFont(UnicodeCIDFont('STSongStd-Light'))
                        self.custom_font = 'STSongStd-Light'
                        self.chinese_font = 'STSongStd-Light'
                        print(f"✅ Using STSongStd-Light CID font")
                    except:
                        raise Exception("No CID fonts available")
        except:
            # Method 2: Fallback to TTF fonts if CID fonts fail
            print("⚠️  CID fonts not available, trying TTF fonts...")
            try:
                # Try Arial Unicode MS (TTF file, not TTC)
                arial_unicode_path = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
                if os.path.exists(arial_unicode_path):
                    pdfmetrics.registerFont(TTFont('ArialUnicode', arial_unicode_path))
                    self.custom_font = 'ArialUnicode'
                    self.chinese_font = 'ArialUnicode'
                    print(f"✅ Using Arial Unicode MS (TTF) - Good Chinese support")
                else:
                    raise Exception("Arial Unicode not found")
            except Exception as e:
                # Final fallback: Use built-in Helvetica
                print(f"❌ Font registration failed: {e}")
                print(f"⚠️  Using Helvetica (limited Chinese character support)")
                self.custom_font = 'Helvetica'
                self.chinese_font = 'Helvetica'
        
        # Set primary font
        self.primary_font = self.custom_font if self.custom_font else self.chinese_font
    
    def _calculate_heikin_ashi(self, price_data: List[Dict]) -> List[Dict]:
        """
        Calculate Heikin Ashi values from regular OHLC data
        
        Args:
            price_data: List of dicts with Open, High, Low, Close
            
        Returns:
            List of dicts with HA_Open, HA_High, HA_Low, HA_Close
        """
        if not price_data:
            return []
        
        ha_data = []
        
        for i, candle in enumerate(price_data):
            open_price = candle.get('Open', 0)
            high_price = candle.get('High', 0)
            low_price = candle.get('Low', 0)
            close_price = candle.get('Adj Close', candle.get('Close', 0))
            
            # Current HA Close = (Open + High + Low + Close) / 4
            ha_close = (open_price + high_price + low_price + close_price) / 4
            
            if i == 0:
                # First candle: HA Open = (Open + Close) / 2
                ha_open = (open_price + close_price) / 2
            else:
                # HA Open = (Previous HA Open + Previous HA Close) / 2
                prev_ha = ha_data[i - 1]
                ha_open = (prev_ha['HA_Open'] + prev_ha['HA_Close']) / 2
            
            # HA High = Max(High, HA Open, HA Close)
            ha_high = max(high_price, ha_open, ha_close)
            
            # HA Low = Min(Low, HA Open, HA Close)
            ha_low = min(low_price, ha_open, ha_close)
            
            ha_data.append({
                'Date': candle.get('Date', ''),
                'HA_Open': ha_open,
                'HA_High': ha_high,
                'HA_Low': ha_low,
                'HA_Close': ha_close,
                'Volume': candle.get('Volume', 0),
            })
        
        return ha_data
    
    def _generate_price_chart(self, price_data: List[Dict], ticker: str) -> bytes:
        """
        Generate Heikin Ashi candlestick chart and volume bar chart as PNG image
        
        Args:
            price_data: List of price data dicts
            ticker: Stock ticker symbol
            
        Returns:
            PNG image as bytes
        """
        if not price_data or len(price_data) < 2:
            return None
        
        # Calculate Heikin Ashi data
        ha_data = self._calculate_heikin_ashi(price_data)
        
        # Prepare data for plotting
        dates = []
        ha_opens = []
        ha_highs = []
        ha_lows = []
        ha_closes = []
        volumes = []
        
        for i, d in enumerate(ha_data):
            dates.append(i)  # Use index for x-axis
            ha_opens.append(d['HA_Open'])
            ha_highs.append(d['HA_High'])
            ha_lows.append(d['HA_Low'])
            ha_closes.append(d['HA_Close'])
            volumes.append(d['Volume'])
        
        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), 
                                        gridspec_kw={'height_ratios': [3, 1]},
                                        sharex=True)
        fig.patch.set_facecolor('white')
        
        # Plot Heikin Ashi candlesticks
        width = 0.8
        for i in range(len(dates)):
            # Determine color: green if close > open (bullish), red otherwise
            if ha_closes[i] >= ha_opens[i]:
                color = '#22c55e'  # Green for bullish
                body_color = '#22c55e'
            else:
                color = '#ef4444'  # Red for bearish
                body_color = '#ef4444'
            
            # Draw the wick (high-low line)
            ax1.plot([dates[i], dates[i]], [ha_lows[i], ha_highs[i]], 
                    color=color, linewidth=1)
            
            # Draw the body (open-close rectangle)
            body_bottom = min(ha_opens[i], ha_closes[i])
            body_height = abs(ha_closes[i] - ha_opens[i])
            rect = Rectangle((dates[i] - width/2, body_bottom), width, body_height,
                            facecolor=body_color, edgecolor=color, linewidth=0.5)
            ax1.add_patch(rect)
        
        # Style price chart
        ax1.set_ylabel('Price ($)', fontsize=10)
        ax1.set_title(f'{ticker} Heikin Ashi Chart', fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.set_facecolor('#fafafa')
        
        # Plot volume bars
        volume_colors = ['#22c55e' if ha_closes[i] >= ha_opens[i] else '#ef4444' 
                        for i in range(len(dates))]
        ax2.bar(dates, volumes, width=width, color=volume_colors, alpha=0.7)
        
        # Style volume chart
        ax2.set_ylabel('Volume', fontsize=10)
        ax2.set_xlabel('Trading Days', fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.set_facecolor('#fafafa')
        
        # Format volume y-axis
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(
            lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.0f}K' if x >= 1e3 else f'{x:.0f}'
        ))
        
        # Add date labels at intervals
        if len(ha_data) > 0:
            # Show first, middle, and last date labels
            label_indices = [0, len(ha_data)//2, len(ha_data)-1]
            labels = []
            positions = []
            for idx in label_indices:
                if idx < len(ha_data):
                    date_str = ha_data[idx].get('Date', '')
                    if date_str:
                        # Format date to show only month/day
                        try:
                            if len(date_str) >= 10:
                                labels.append(date_str[5:10])  # MM-DD
                            else:
                                labels.append(date_str)
                        except:
                            labels.append(date_str)
                        positions.append(idx)
            
            if positions and labels:
                ax2.set_xticks(positions)
                ax2.set_xticklabels(labels)
        
        # Tight layout
        plt.tight_layout()
        
        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        
        return buf.getvalue()
    
    def generate_analyst_report_pdf(
        self,
        analyst_name: str,
        ticker: str,
        analysis_date: str,
        report_content: str,
        price_data: list = None,
        price_stats: dict = None,
    ) -> bytes:
        """
        Generate a PDF from analyst report content
        
        Args:
            analyst_name: Name of the analyst
            ticker: Stock ticker symbol
            analysis_date: Date of analysis
            report_content: Markdown formatted report content
            price_data: Optional list of price data dicts with Date, Open, High, Low, Close, Volume
            price_stats: Optional dict with growth_rate, duration_days, start_date, end_date, start_price, end_price
            
        Returns:
            PDF file content as bytes
        """
        buffer = io.BytesIO()
        
        # Create PDF document with reduced margins for more content space
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm,
        )
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Custom styles with proper spacing and wrapping
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=self.primary_font,
            fontSize=24,
            textColor=HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER,
            wordWrap='CJK',
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontName=self.primary_font,
            fontSize=12,
            textColor=HexColor('#666666'),
            spaceAfter=12,
            alignment=TA_CENTER,
            wordWrap='CJK',
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=self.primary_font,
            fontSize=16,
            textColor=HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=16,
            wordWrap='CJK',
        )
        
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontName=self.primary_font,
            fontSize=9,
            leading=14,
            textColor=HexColor('#333333'),
            spaceAfter=8,
            wordWrap='CJK',
            splitLongWords=True,
            allowOrphans=0,
            allowWidows=0,
        )
        
        # === PAGE 1: Price Information (if price data is provided) ===
        if price_stats and price_data:
            # Page 1 Title
            price_title = f"{ticker} 價格資訊"
            elements.append(Paragraph(price_title, title_style))
            elements.append(Spacer(1, 0.3*cm))
            
            # Analysis date
            elements.append(Paragraph(f"分析日期：{analysis_date}", subtitle_style))
            elements.append(Spacer(1, 0.8*cm))
            
            # Price statistics style
            stat_style = ParagraphStyle(
                'StatStyle',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=12,
                leading=18,
                textColor=HexColor('#333333'),
                spaceAfter=6,
                wordWrap='CJK',
            )
            
            stat_label_style = ParagraphStyle(
                'StatLabelStyle',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=10,
                textColor=HexColor('#666666'),
                spaceAfter=2,
                wordWrap='CJK',
            )
            
            stat_value_style = ParagraphStyle(
                'StatValueStyle',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=16,
                textColor=HexColor('#1a1a1a'),
                spaceAfter=12,
                wordWrap='CJK',
            )
            
            # Growth rate with color
            growth_rate = price_stats.get('growth_rate', 0)
            growth_color = '#22c55e' if growth_rate >= 0 else '#ef4444'  # green/red
            growth_text = f"+{growth_rate:.2f}%" if growth_rate >= 0 else f"{growth_rate:.2f}%"
            
            growth_value_style = ParagraphStyle(
                'GrowthValueStyle',
                parent=stat_value_style,
                fontSize=20,
                textColor=HexColor(growth_color),
            )
            
            # Add price statistics
            elements.append(Paragraph("總報酬率", stat_label_style))
            elements.append(Paragraph(growth_text, growth_value_style))
            elements.append(Spacer(1, 0.3*cm))
            
            duration_days = price_stats.get('duration_days', 0)
            elements.append(Paragraph("分析期間", stat_label_style))
            elements.append(Paragraph(f"{duration_days} 天", stat_value_style))
            
            start_date = price_stats.get('start_date', 'N/A')
            end_date = price_stats.get('end_date', 'N/A')
            elements.append(Paragraph("日期區間", stat_label_style))
            elements.append(Paragraph(f"{start_date} ~ {end_date}", stat_style))
            elements.append(Spacer(1, 0.3*cm))
            
            start_price = price_stats.get('start_price', 0)
            end_price = price_stats.get('end_price', 0)
            elements.append(Paragraph("起始價格", stat_label_style))
            elements.append(Paragraph(f"${start_price:.2f}", stat_value_style))
            
            elements.append(Paragraph("結束價格", stat_label_style))
            elements.append(Paragraph(f"${end_price:.2f}", stat_value_style))
            
            # Add Heikin Ashi Chart and Volume Chart
            if price_data and len(price_data) >= 5:
                try:
                    # Generate chart image
                    chart_bytes = self._generate_price_chart(price_data, ticker)
                    
                    if chart_bytes:
                        elements.append(Spacer(1, 0.5*cm))
                        elements.append(Paragraph("價格走勢與交易量", heading_style))
                        elements.append(Spacer(1, 0.3*cm))
                        
                        # Create image from bytes
                        chart_buffer = io.BytesIO(chart_bytes)
                        
                        # Add chart image to PDF (width fits A4 page with margins)
                        chart_img = Image(chart_buffer, width=17*cm, height=10.2*cm)
                        elements.append(chart_img)
                        
                except Exception as e:
                    # If chart generation fails, fall back to text summary
                    print(f"Chart generation failed: {e}")
                    elements.append(Spacer(1, 0.5*cm))
                    elements.append(Paragraph("最近交易數據", heading_style))
                    elements.append(Spacer(1, 0.2*cm))
                    
                    # Show last 5 trading days as text fallback
                    recent_data = price_data[-5:] if len(price_data) >= 5 else price_data
                    for day in reversed(recent_data):
                        date = day.get('Date', 'N/A')
                        close = day.get('Close', 0)
                        adj_close = day.get('Adj Close', close)
                        volume = day.get('Volume', 0)
                        
                        # Format volume
                        if volume >= 1000000000:
                            vol_str = f"{volume/1000000000:.2f}B"
                        elif volume >= 1000000:
                            vol_str = f"{volume/1000000:.2f}M"
                        elif volume >= 1000:
                            vol_str = f"{volume/1000:.2f}K"
                        else:
                            vol_str = str(volume)
                        
                        day_text = f"{date}：收盤 ${adj_close:.2f}，成交量 {vol_str}"
                        elements.append(Paragraph(day_text, stat_style))
            
            # Page break before analyst content
            elements.append(PageBreak())
        
        # === PAGE 2+: Analyst Report Content ===
        # Add title
        title = f"{analyst_name}"
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 0.3*cm))
        
        # Add metadata
        metadata = f"{ticker} | {analysis_date}"
        elements.append(Paragraph(metadata, subtitle_style))
        elements.append(Spacer(1, 0.5*cm))
        
        # STEP 1: Replace emojis with Unicode symbols BEFORE markdown cleaning
        report_content = self._replace_emojis(report_content)
        analyst_name = self._replace_emojis(analyst_name)
        
        # STEP 2: Clean markdown formatting
        content = self._clean_markdown(report_content)
        
        # Split content into paragraphs
        paragraphs = content.split('\n')
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                elements.append(Spacer(1, 0.2*cm))
                continue
            
            # Check if it's a heading
            if para.startswith('# '):
                text = para[2:]
                elements.append(Paragraph(text, heading_style))
            elif para.startswith('## '):
                text = para[3:]
                elements.append(Paragraph(text, heading_style))
            elif para.startswith('### '):
                text = para[4:]
                elements.append(Paragraph(text, heading_style))
            else:
                # Regular paragraph - escape HTML chars and handle special characters
                text = self._escape_html(para)
                # Ensure proper UTF-8 handling
                elements.append(Paragraph(text, body_style))
        
        # Build PDF
        doc.build(elements)
        
        # Get the PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        return pdf_content
    
    def _clean_markdown(self, text: str) -> str:
        """
        Clean markdown formatting for PDF - IMPROVED VERSION
        Simplified regex patterns to prevent encoding artifacts
        
        Args:
            text: Markdown text
            
        Returns:
            Cleaned text
        """
        import unicodedata
        
        # 0. Normalize Unicode to prevent encoding issues
        text = unicodedata.normalize('NFKC', text)
        
        # 1. Remove markdown links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # 2. Remove bold markers (simplified version)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        
        # 3. Remove italic markers (SIMPLIFIED - avoid complex lookahead/lookbehind)
        # Only match single * or _ that are NOT part of ** or __
        text = re.sub(r'(?<![\*])\*([^\*]+?)\*(?![\*])', r'\1', text)
        text = re.sub(r'(?<![_])_([^_]+?)_(?![_])', r'\1', text)
        
        # 4. Remove code blocks
        text = re.sub(r'```[^`]*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`([^`]+?)`', r'\1', text)
        
        # 5. Clean up bullet points - USE ASCII DASH, NOT UNICODE BULLET
        # Unicode bullet • (U+2022) renders as '煉' in STSong-Light font!
        text = re.sub(r'^\s*[\*\-\+]\s+', '- ', text, flags=re.MULTILINE)
        
        # 6. Remove horizontal rules
        text = re.sub(r'^[\-\*_]{3,}\s*$', '', text, flags=re.MULTILINE)
        
        # 7. Clean table separators (simplified)
        text = re.sub(r'^\s*\|?\s*:?-+:?\s*\|?\s*$', '', text, flags=re.MULTILINE)
        
        # 8. Remove table | symbols (keep content)
        text = re.sub(r'^\s*\|', '', text, flags=re.MULTILINE)
        text = re.sub(r'\|\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\|', ' | ', text)
        
        # 9. Clean excess spaces
        text = re.sub(r' {2,}', ' ', text)
        
        # 10. Clean excess blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 11. Remove isolated markdown symbols (SIMPLIFIED - no complex patterns)
        # Remove lines that only contain markdown symbols
        text = re.sub(r'^[\*_`~#\-\+]+\s*$', '', text, flags=re.MULTILINE)
        
        # 12. REMOVED problematic Unicode filter that was corrupting Chinese characters
        # The string comparison '\u4e00' <= char <= '\u9fff' was comparing UTF-8 bytes,
        # not Unicode code points, causing characters like '經' to be corrupted.
        # Unicode normalization at the start (line 237) is sufficient.
        
        return text.strip()
    
    def _escape_html(self, text: str) -> str:
        """
        Escape HTML special characters for PDF - IMPROVED VERSION
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text
        """
        # Escape in order to avoid double-escaping
        replacements = [
            ('&', '&amp;'),
            ('<', '&lt;'),
            ('>', '&gt;'),
            ('"', '&quot;'),
            ("'", '&apos;'),
        ]
        
        for old, new in replacements:
            text = text.replace(old, new)
        
        return text
    
    def _replace_emojis(self, text: str) -> str:
        """
        Replace emoji characters with Unicode text symbols for PDF compatibility
        
        Emojis don't render well in PDFs, especially with CID fonts.
        This method replaces common emojis with Unicode text symbols that
        display reliably across all PDF viewers.
        
        Args:
            text: Text containing potential emoji characters
            
        Returns:
            Text with emojis replaced by Unicode symbols
        """
        if not text:
            return text
        
        # Replace each emoji with its Unicode symbol equivalent
        for emoji, unicode_symbol in self.EMOJI_TO_UNICODE.items():
            text = text.replace(emoji, unicode_symbol)
        
        return text
