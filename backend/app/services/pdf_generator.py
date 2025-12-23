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

# ============================================
# PDF LABELS FOR INTERNATIONALIZATION
# ============================================
PDF_LABELS = {
    'en': {
        # Cover page
        'cover_title': 'TradingAgentsX Analysis Report',
        'cover_subtitle': 'AI-Powered Multi-Perspective Investment Analysis',
        
        # TOC
        'toc_title': 'Table of Contents',
        'report_content': 'Report Content',
        'price_chart': 'Price Chart & Volume',
        
        # Stats
        'price_stats': 'Price Statistics',
        'item': 'Item',
        'value': 'Value',
        'total_return': 'Total Return',
        'analysis_period': 'Analysis Period',
        'days': 'days',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'start_price': 'Start Price',
        'end_price': 'End Price',
        'chart_failed': 'Chart generation failed',
        
        # Teams
        'analysts_team': 'Analysts Team',
        'research_team': 'Research Team',
        'trading_risk_team': 'Trading & Risk Team',
        'members': 'members',
        
        # Analyst names
        'market_analyst': 'Market Analyst',
        'fundamentals_analyst': 'Fundamentals Analyst',
        'social_analyst': 'Social Media Analyst',
        'news_analyst': 'News Analyst',
        'bull_researcher': 'Bull Researcher',
        'bear_researcher': 'Bear Researcher',
        'research_manager': 'Research Manager',
        'aggressive_debator': 'Aggressive Analyst',
        'conservative_debator': 'Conservative Analyst',
        'neutral_debator': 'Neutral Analyst',
        'risk_manager': 'Risk Manager',
        'trader': 'Trader',
    },
    'zh-TW': {
        # Cover page
        'cover_title': 'TradingAgentsX 分析報告',
        'cover_subtitle': 'AI 驅動的多角度投資分析',
        
        # TOC
        'toc_title': '目錄',
        'report_content': '報告內容',
        'price_chart': '價格走勢圖 & 交易量柱狀圖',
        
        # Stats
        'price_stats': '價格統計',
        'item': '項目',
        'value': '數值',
        'total_return': '總報酬率',
        'analysis_period': '分析期間',
        'days': '天',
        'start_date': '開始日期',
        'end_date': '結束日期',
        'start_price': '起始價格',
        'end_price': '結束價格',
        'chart_failed': '圖表生成失敗',
        
        # Teams
        'analysts_team': '分析師團隊',
        'research_team': '研究團隊',
        'trading_risk_team': '交易與風險團隊',
        'members': '位',
        
        # Analyst names
        'market_analyst': '市場分析師',
        'fundamentals_analyst': '基本面分析師',
        'social_analyst': '社群媒體分析師',
        'news_analyst': '新聞分析師',
        'bull_researcher': '看漲研究員',
        'bear_researcher': '看跌研究員',
        'research_manager': '研究經理',
        'aggressive_debator': '激進分析師',
        'conservative_debator': '保守分析師',
        'neutral_debator': '中立分析師',
        'risk_manager': '風險經理',
        'trader': '交易員',
    }
}

# Helper to get label by language
def get_pdf_label(key: str, language: str = 'zh-TW') -> str:
    """Get PDF label by key and language."""
    labels = PDF_LABELS.get(language, PDF_LABELS['zh-TW'])
    return labels.get(key, key)


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
        
        # Checkbox symbols - common in reports
        '☒': '[X]',  # Ballot box with X
        '☑': '[V]',  # Ballot box with check
        '☐': '[ ]',  # Empty ballot box
        '✓': 'V',    # Check mark
        '✔': 'V',    # Heavy check mark
        '✗': 'X',    # Ballot X
        '✘': 'X',    # Heavy ballot X
        
        # Special notation symbols
        '※': '*',    # Reference mark
        '△': '^',    # Triangle up
        '▽': 'v',    # Triangle down
        '▲': '^',    # Black triangle up
        '▼': 'v',    # Black triangle down
        '◆': '*',    # Diamond
        '◇': '*',    # White diamond
        '○': 'o',    # White circle
        '●': '*',    # Black circle
        '□': '[ ]',  # White square
        '■': '[*]',  # Black square
        
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
        """Initialize PDF generator with Chinese font support using Noto Serif TC"""
        import os
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
        # Initialize font variables
        self.custom_font = None
        self.custom_font_bold = None
        
        # Get the base path for fonts
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        font_dir = os.path.join(base_dir, 'Cactus_Classical_Serif,Noto_Serif_TC', 'Noto_Serif_TC', 'static')
        
        # Try to register Noto Serif TC fonts (best for Chinese with proper spacing)
        font_paths = [
            (os.path.join(font_dir, 'NotoSerifTC-Regular.ttf'), 'NotoSerifTC'),
            (os.path.join(font_dir, 'NotoSerifTC-Bold.ttf'), 'NotoSerifTC-Bold'),
        ]
        
        fonts_registered = False
        for font_path, font_name in font_paths:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    if font_name == 'NotoSerifTC':
                        self.custom_font = font_name
                    elif font_name == 'NotoSerifTC-Bold':
                        self.custom_font_bold = font_name
                    fonts_registered = True
                    print(f"✅ Registered font: {font_name}")
                except Exception as e:
                    print(f"⚠️ Failed to register {font_name}: {e}")
        
        if fonts_registered and self.custom_font:
            print(f"✅ Using NotoSerifTC fonts - Proper Chinese character spacing")
        else:
            # Fallback to CID fonts
            try:
                from reportlab.pdfbase.cidfonts import UnicodeCIDFont
                pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
                self.custom_font = 'STSong-Light'
                self.custom_font_bold = 'STSong-Light'
                print(f"✅ Using STSong-Light CID font as fallback")
            except:
                # Final fallback
                self.custom_font = 'Helvetica'
                self.custom_font_bold = 'Helvetica-Bold'
                print(f"⚠️ Using Helvetica as final fallback")
        
        # Set primary font
        self.primary_font = self.custom_font
        self.bold_font = self.custom_font_bold if self.custom_font_bold else self.custom_font
    
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
        Clean markdown formatting for PDF - AGGRESSIVE VERSION
        Removes ALL markdown syntax to produce clean text
        
        Args:
            text: Markdown text
            
        Returns:
            Cleaned text with no markdown syntax
        """
        import unicodedata
        
        # 0. Normalize Unicode to prevent encoding issues
        text = unicodedata.normalize('NFKC', text)
        
        # 1. Remove markdown links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # 2. Remove bold markers - MULTIPLE PASSES for nested cases
        # Handle **text** pattern (greedy removal)
        for _ in range(3):  # Multiple passes to handle nested/adjacent
            text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
            text = re.sub(r'__([^_]+)__', r'\1', text)
        
        # 3. Handle remaining isolated ** or __ 
        text = re.sub(r'\*\*', '', text)
        text = re.sub(r'__', '', text)
        
        # 4. Remove italic markers (single * or _)
        text = re.sub(r'(?<![*])\*([^*]+?)\*(?![*])', r'\1', text)
        text = re.sub(r'(?<![_])_([^_]+?)_(?![_])', r'\1', text)
        
        # 5. Remove remaining isolated * that aren't bullet points
        # Keep * at start of line (bullet points)
        text = re.sub(r'(?<!^)(?<!\n)\*(?![*\s])', '', text)
        
        # 6. Remove code blocks
        text = re.sub(r'```[^`]*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`([^`]+?)`', r'\1', text)
        
        # 7. Clean up bullet points - normalize to simple dash
        text = re.sub(r'^\s*[\*\-\+]\s+', '- ', text, flags=re.MULTILINE)
        
        # 8. Remove horizontal rules
        text = re.sub(r'^[\-\*_]{3,}\s*$', '', text, flags=re.MULTILINE)
        
        # 9. Clean table separators
        text = re.sub(r'^\s*\|?\s*:?-+:?\s*\|?\s*$', '', text, flags=re.MULTILINE)
        
        # 10. Remove table | symbols but keep content
        text = re.sub(r'^\s*\|', '', text, flags=re.MULTILINE)
        text = re.sub(r'\|\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\|', ' | ', text)
        
        # 11. Remove heading markers (# ## ### etc)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # 12. Clean excess spaces
        text = re.sub(r' {2,}', ' ', text)
        
        # 13. Clean excess blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 14. Remove isolated markdown symbols on their own lines
        text = re.sub(r'^[\*_`~#\-\+]+\s*$', '', text, flags=re.MULTILINE)
        
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
    
    def generate_combined_report_pdf(
        self,
        ticker: str,
        analysis_date: str,
        reports: list,
        price_data: list = None,
        price_stats: dict = None,
        language: str = "zh-TW",
    ) -> bytes:
        """
        Generate a combined PDF containing all analyst reports with cover page and table of contents
        
        Args:
            ticker: Stock ticker symbol
            analysis_date: Date of analysis
            reports: List of dicts with 'analyst_name' and 'report_content'
            price_data: Optional list of price data dicts
            price_stats: Optional dict with price statistics
            language: Language for PDF labels ('en' or 'zh-TW')
            
        Returns:
            PDF file content as bytes
        """
        from reportlab.platypus import Paragraph, Spacer, PageBreak, Image
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.colors import HexColor
        from reportlab.lib.units import cm
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        
        buffer = io.BytesIO()
        
        # Store language for use in helper methods
        self._current_language = language
        
        # Define team structure with bilingual support
        # Note: 'members' must match the analyst_name keys sent from routes.py
        if language == "en":
            TEAMS = [
                {
                    'name': 'Analysts Team',
                    'count': 4,
                    'members': ['Market Analyst', 'Social Media Analyst', 'News Analyst', 'Fundamentals Analyst'],
                    'display_members': ['Market Analyst', 'Social Media Analyst', 'News Analyst', 'Fundamentals Analyst'],
                },
                {
                    'name': 'Research Team',
                    'count': 3,
                    'members': ['Bull Researcher', 'Bear Researcher', 'Research Manager'],
                    'display_members': ['Bull Researcher', 'Bear Researcher', 'Research Manager'],
                },
                {
                    'name': 'Trading & Risk Team',
                    'count': 5,
                    'members': ['Trader', 'Aggressive Analyst', 'Conservative Analyst', 'Neutral Analyst', 'Risk Manager'],
                    'display_members': ['Trader', 'Aggressive Analyst', 'Conservative Analyst', 'Neutral Analyst', 'Risk Manager'],
                },
            ]
        else:
            TEAMS = [
                {
                    'name': '分析師團隊',
                    'count': 4,
                    'members': ['市場分析師', '社群媒體分析師', '新聞分析師', '基本面分析師'],
                    'display_members': ['市場分析師', '社群媒體分析師', '新聞分析師', '基本面分析師'],
                },
                {
                    'name': '研究團隊',
                    'count': 3,
                    'members': ['看漲研究員', '看跌研究員', '研究經理'],
                    'display_members': ['看漲研究員', '看跌研究員', '研究經理'],
                },
                {
                    'name': '交易與風險團隊',
                    'count': 5,
                    'members': ['交易員', '激進分析師', '保守分析師', '中立分析師', '風險經理'],
                    'display_members': ['交易員', '激進分析師', '保守分析師', '中立分析師', '風險經理'],
                },
            ]
        
        # Create a mapping of analyst names to their reports
        report_map = {r.get('analyst_name', ''): r.get('report_content', '') for r in reports}
        
        # Create PDF document with custom page numbering
        # Cover and TOC don't have page numbers
        # Page numbering starts from chart page = Page 1
        
        buffer = io.BytesIO()
        
        from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, NextPageTemplate, PageBreak as PB
        from reportlab.lib.pagesizes import A4
        from io import BytesIO
        
        # Track pages for numbering (pages after TOC)
        self._page_offset = 2  # Cover + TOC = 2 pages without numbers
        
        def add_page_number(canvas, doc):
            """Add page number to footer for content pages"""
            page_num = doc.page - self._page_offset
            if page_num > 0:
                canvas.saveState()
                canvas.setFont(self.primary_font, 10)
                page_text = f"- {page_num} -"
                canvas.drawCentredString(A4[0] / 2, 1 * cm, page_text)
                canvas.restoreState()
        
        def no_page_number(canvas, doc):
            """No page number for cover and TOC"""
            pass
        
        # Create document
        doc = BaseDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=2*cm,
        )
        
        # Define frames
        frame = Frame(
            doc.leftMargin,
            doc.bottomMargin,
            doc.width,
            doc.height,
            id='normal'
        )
        
        # Define page templates
        # 'cover' and 'toc' templates have no page numbers
        # 'content' template has page numbers
        doc.addPageTemplates([
            PageTemplate(id='cover', frames=frame, onPage=no_page_number),
            PageTemplate(id='toc', frames=frame, onPage=no_page_number),
            PageTemplate(id='content', frames=frame, onPage=add_page_number),
        ])
        
        elements = []
        styles = self._get_styles()
        
        # === COVER PAGE (no page number) ===
        elements.append(NextPageTemplate('cover'))
        elements.extend(self._create_cover_page(ticker, analysis_date, styles, language))
        elements.append(NextPageTemplate('toc'))
        elements.append(PageBreak())
        
        # Check if we have chart data
        has_chart = price_data and len(price_data) >= 5
        
        # === TABLE OF CONTENTS PAGE (no page number) ===
        elements.extend(self._create_toc_page(ticker, analysis_date, reports, price_data, price_stats, styles, has_chart, TEAMS, language))
        elements.append(NextPageTemplate('content'))
        elements.append(PageBreak())
        
        # ========================================
        # CONTENT PAGES WITH PAGE NUMBERS
        # ========================================
        
        # === PRICE CHART PAGE (Page 1, if data available) ===
        if has_chart:
            elements.extend(self._create_chart_page(ticker, price_data, price_stats, styles, language))
            elements.append(PageBreak())
        
        # === ANALYST REPORTS BY TEAM ===
        for team_idx, team in enumerate(TEAMS):
            # Get reports for this team
            team_reports = []
            for member_name in team['members']:
                if member_name in report_map and report_map[member_name]:
                    # Use display name if available (for English mode)
                    display_name = member_name
                    if 'display_members' in team:
                        idx = team['members'].index(member_name)
                        if idx < len(team['display_members']):
                            display_name = team['display_members'][idx]
                    team_reports.append({
                        'analyst_name': member_name,
                        'display_name': display_name,
                        'report_content': report_map[member_name]
                    })
            
            # Skip team if no reports
            if not team_reports:
                continue
            
            # Add team separator page
            elements.extend(self._create_team_separator(team['name'], len(team_reports), styles, language))
            elements.append(PageBreak())
            
            # Add each analyst report in this team
            for report_idx, report in enumerate(team_reports):
                analyst_name = report.get('analyst_name', 'Unknown')
                display_name = report.get('display_name', analyst_name)
                report_content = report.get('report_content', '')
                
                # Add analyst report section (use display_name for header)
                elements.extend(self._create_analyst_section(
                    analyst_name=display_name,
                    ticker=ticker,
                    analysis_date=analysis_date,
                    report_content=report_content,
                    styles=styles,
                ))
                
                # Page break after each analyst
                elements.append(PageBreak())
        
        # Build PDF
        doc.build(elements)
        
        pdf_content = buffer.getvalue()
        buffer.close()
        
        return pdf_content
    
    def _get_styles(self):
        """Get all paragraph styles for the combined PDF"""
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.colors import HexColor
        
        styles = getSampleStyleSheet()
        
        custom_styles = {
            'cover_title': ParagraphStyle(
                'CoverTitle',
                parent=styles['Heading1'],
                fontName=self.primary_font,
                fontSize=48,
                textColor=HexColor('#1a1a1a'),
                alignment=TA_CENTER,
                spaceAfter=20,
                wordWrap='CJK',
                leading=60,  # Line height
            ),
            'cover_subtitle': ParagraphStyle(
                'CoverSubtitle',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=24,
                textColor=HexColor('#666666'),
                alignment=TA_CENTER,
                spaceAfter=40,
                wordWrap='CJK',
            ),
            'cover_info': ParagraphStyle(
                'CoverInfo',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=14,
                textColor=HexColor('#888888'),
                alignment=TA_CENTER,
                spaceAfter=10,
                wordWrap='CJK',
            ),
            'toc_title': ParagraphStyle(
                'TOCTitle',
                parent=styles['Heading1'],
                fontName=self.primary_font,
                fontSize=28,
                textColor=HexColor('#1a1a1a'),
                alignment=TA_CENTER,
                spaceAfter=30,
                wordWrap='CJK',
            ),
            'toc_section': ParagraphStyle(
                'TOCSection',
                parent=styles['Heading2'],
                fontName=self.primary_font,
                fontSize=16,
                textColor=HexColor('#2c3e50'),
                spaceAfter=15,
                spaceBefore=20,
                wordWrap='CJK',
            ),
            'toc_item': ParagraphStyle(
                'TOCItem',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=12,
                textColor=HexColor('#444444'),
                spaceAfter=8,
                leftIndent=20,
                wordWrap='CJK',
            ),
            'section_title': ParagraphStyle(
                'SectionTitle',
                parent=styles['Heading1'],
                fontName=self.primary_font,
                fontSize=24,
                textColor=HexColor('#1a1a1a'),
                spaceAfter=20,
                alignment=TA_CENTER,
                wordWrap='CJK',
            ),
            'section_subtitle': ParagraphStyle(
                'SectionSubtitle',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=12,
                textColor=HexColor('#666666'),
                spaceAfter=15,
                alignment=TA_CENTER,
                wordWrap='CJK',
            ),
            'heading': ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontName=self.primary_font,
                fontSize=16,
                textColor=HexColor('#2c3e50'),
                spaceAfter=12,
                spaceBefore=16,
                wordWrap='CJK',
            ),
            # Report title - for lines like "ORCL(甲骨文公司)技術分析報告"
            'report_title': ParagraphStyle(
                'ReportTitle',
                parent=styles['Heading2'],
                fontName=self.primary_font,
                fontSize=14,
                textColor=HexColor('#1a5276'),  # Dark blue
                spaceAfter=15,
                spaceBefore=10,
                wordWrap='CJK',
            ),
            # Numbered heading - for lines like "1. 市場概況", "2. 技術分析"
            'numbered_heading': ParagraphStyle(
                'NumberedHeading',
                parent=styles['Heading3'],
                fontName=self.primary_font,
                fontSize=11,
                textColor=HexColor('#117864'),  # Dark green
                spaceAfter=8,
                spaceBefore=12,
                wordWrap='CJK',
            ),
            'body': ParagraphStyle(
                'CustomBody',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=9,
                leading=14,
                textColor=HexColor('#333333'),
                spaceAfter=8,
                wordWrap='CJK',
                splitLongWords=True,
            ),
            'stats_label': ParagraphStyle(
                'StatsLabel',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=10,
                textColor=HexColor('#666666'),
                spaceAfter=2,
                wordWrap='CJK',
            ),
            'stats_value': ParagraphStyle(
                'StatsValue',
                parent=styles['Normal'],
                fontName=self.primary_font,
                fontSize=14,
                textColor=HexColor('#1a1a1a'),
                spaceAfter=10,
                wordWrap='CJK',
            ),
        }
        
        return custom_styles
    
    def _create_cover_page(self, ticker: str, analysis_date: str, styles: dict, language: str = 'zh-TW') -> list:
        """Create cover page elements"""
        from reportlab.platypus import Spacer
        from reportlab.lib.units import cm
        
        elements = []
        
        # Add vertical space to center content
        elements.append(Spacer(1, 6*cm))
        
        # Main title: Stock ticker with letter spacing
        # Add spaces between letters for better visual appeal
        spaced_ticker = '  '.join(ticker)  # Insert double space between each letter
        elements.append(Paragraph(spaced_ticker, styles['cover_title']))
        
        # Subtitle: Analysis date with spacing
        elements.append(Paragraph(analysis_date, styles['cover_subtitle']))
        
        # Additional info
        elements.append(Spacer(1, 2*cm))
        elements.append(Paragraph(get_pdf_label('cover_title', language), styles['cover_info']))
        elements.append(Paragraph(get_pdf_label('cover_subtitle', language), styles['cover_info']))
        
        return elements
    
    def _create_toc_page(
        self,
        ticker: str,
        analysis_date: str,
        reports: list,
        price_data: list,
        price_stats: dict,
        styles: dict,
        has_chart: bool = False,
        teams: list = None,
        language: str = 'zh-TW'
    ) -> list:
        """Create a clean table of contents page with page numbers"""
        from reportlab.platypus import Spacer, Table, TableStyle
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor, black, lightgrey
        from reportlab.lib.styles import ParagraphStyle
        
        elements = []
        
        # TOC Title
        elements.append(Paragraph(get_pdf_label('toc_title', language), styles['toc_title']))
        elements.append(Spacer(1, 0.5*cm))
        
        # Track which analysts are in the reports
        report_analyst_names = [r.get('analyst_name', '') for r in reports]
        
        # Build TOC as simple list (no page numbers since reports span multiple pages)
        table_data = []
        table_data.append([
            Paragraph(f'<b>{get_pdf_label("report_content", language)}</b>', styles['toc_section']),
        ])
        
        # Add chart page entry if available
        if has_chart:
            table_data.append([
                Paragraph(f'  {get_pdf_label("price_chart", language)}', styles['toc_item']),
            ])
        
        # Use teams if provided
        if teams:
            for team in teams:
                team_name = team['name']
                team_members = team['members']
                
                # Count how many members have reports
                team_report_count = sum(1 for m in team_members if m in report_analyst_names)
                if team_report_count == 0:
                    continue
                
                # Add team separator entry
                members_label = get_pdf_label('members', language)
                table_data.append([
                    Paragraph(f'<b>{team_name} ({team_report_count} {members_label})</b>', styles['toc_section']),
                ])
                
                # Add each analyst in this team
                for analyst_name in team_members:
                    if analyst_name in report_analyst_names:
                        table_data.append([
                            Paragraph(f'      - {analyst_name}', styles['toc_item']),
                        ])
        
        # Create table (single column)
        col_widths = [16*cm]
        toc_table = Table(table_data, colWidths=col_widths)
        
        # Style the table
        table_style = TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), self.primary_font),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('LINEBELOW', (0, 0), (-1, 0), 1, black),  # Header line
        ])
        toc_table.setStyle(table_style)
        
        elements.append(toc_table)
        
        return elements
    
    def _create_team_separator(
        self,
        team_name: str,
        member_count: int,
        styles: dict,
        language: str = 'zh-TW'
    ) -> list:
        """Create a team separator page"""
        from reportlab.platypus import Spacer
        from reportlab.lib.units import cm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.colors import HexColor
        
        elements = []
        
        # Center the team name vertically
        elements.append(Spacer(1, 8*cm))
        
        # Team name with member count
        team_style = ParagraphStyle(
            'TeamSeparator',
            fontName=self.primary_font,
            fontSize=36,
            textColor=HexColor('#2c3e50'),
            alignment=TA_CENTER,
            spaceAfter=20,
            leading=50,
        )
        
        # Add spaces for better letter spacing (only for Chinese)
        if language == 'zh-TW':
            spaced_name = ' '.join(team_name)
        else:
            spaced_name = team_name
        elements.append(Paragraph(spaced_name, team_style))
        
        # Member count
        count_style = ParagraphStyle(
            'TeamCount',
            fontName=self.primary_font,
            fontSize=24,
            textColor=HexColor('#7f8c8d'),
            alignment=TA_CENTER,
            spaceAfter=10,
        )
        members_label = get_pdf_label('members', language)
        elements.append(Paragraph(f"({member_count} {members_label})", count_style))
        
        return elements
    
    def _create_chart_page(
        self,
        ticker: str,
        price_data: list,
        price_stats: dict,
        styles: dict,
        language: str = 'zh-TW'
    ) -> list:
        """Create a dedicated price chart page"""
        from reportlab.platypus import Spacer, Image, Table, TableStyle
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor, black, lightgrey
        from reportlab.lib.styles import ParagraphStyle
        
        elements = []
        
        # Page title
        elements.append(Paragraph(get_pdf_label('price_chart', language), styles['section_title']))
        elements.append(Spacer(1, 0.5*cm))
        
        # Generate and add chart
        if price_data and len(price_data) >= 5:
            try:
                chart_bytes = self._generate_price_chart(price_data, ticker)
                if chart_bytes:
                    chart_buffer = io.BytesIO(chart_bytes)
                    chart_img = Image(chart_buffer, width=17*cm, height=10.2*cm)
                    elements.append(chart_img)
                    elements.append(Spacer(1, 0.8*cm))
            except Exception as e:
                print(f"Chart generation failed: {e}")
                elements.append(Paragraph(get_pdf_label('chart_failed', language), styles['body']))
        
        # Add price statistics table
        if price_stats:
            elements.append(Paragraph(get_pdf_label('price_stats', language), styles['heading']))
            elements.append(Spacer(1, 0.3*cm))
            
            growth_rate = price_stats.get('growth_rate', 0)
            growth_text = f"+{growth_rate:.2f}%" if growth_rate >= 0 else f"{growth_rate:.2f}%"
            
            # Build stats data with localized labels
            days_label = get_pdf_label('days', language)
            stats_data = [
                [get_pdf_label('item', language), get_pdf_label('value', language)],
                [get_pdf_label('total_return', language), growth_text],
                [get_pdf_label('analysis_period', language), f"{price_stats.get('duration_days', 'N/A')} {days_label}"],
                [get_pdf_label('start_date', language), price_stats.get('start_date', 'N/A')],
                [get_pdf_label('end_date', language), price_stats.get('end_date', 'N/A')],
            ]
            
            # Add start/end prices if available
            if 'start_price' in price_stats:
                stats_data.append([get_pdf_label('start_price', language), f"${price_stats.get('start_price', 0):.2f}"])
            if 'end_price' in price_stats:
                stats_data.append([get_pdf_label('end_price', language), f"${price_stats.get('end_price', 0):.2f}"])
            
            # Create table
            col_widths = [8*cm, 8*cm]
            stats_table = Table(stats_data, colWidths=col_widths)
            
            # Style the table
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#e5e7eb')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), self.primary_font),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, lightgrey),
                ('LINEBELOW', (0, 0), (-1, 0), 1, black),
            ])
            stats_table.setStyle(table_style)
            
            elements.append(stats_table)
        
        return elements
    
    def _parse_markdown_table(self, lines: list, start_idx: int) -> tuple:
        """
        Parse markdown table starting at start_idx
        Returns (table_data, end_idx) where table_data is list of rows
        """
        table_rows = []
        i = start_idx
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Check if line is a table row
            if line.startswith('|') and line.endswith('|'):
                # Parse cells
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                
                # Skip separator rows (like |---|---|---)
                is_separator = all(cell.replace('-', '').replace(':', '').strip() == '' for cell in cells)
                if not is_separator:
                    table_rows.append(cells)
                i += 1
            elif '|' in line and not line.startswith('#'):
                # Handle tables without leading |
                cells = [cell.strip() for cell in line.split('|')]
                is_separator = all(cell.replace('-', '').replace(':', '').strip() == '' for cell in cells)
                if not is_separator and cells:
                    table_rows.append(cells)
                i += 1
            else:
                break
        
        return table_rows, i
    
    def _create_pdf_table(self, table_data: list, styles: dict):
        """Create a PDF table from parsed markdown table data"""
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib.units import cm
        from reportlab.lib.colors import black, lightgrey, white, HexColor
        
        if not table_data or len(table_data) == 0:
            return None
        
        # Convert text to Paragraphs for word wrapping
        pdf_data = []
        for row_idx, row in enumerate(table_data):
            pdf_row = []
            for cell in row:
                # Clean markdown from cell content first
                cell_cleaned = self._clean_markdown(str(cell))
                cell_text = self._escape_html(cell_cleaned)
                if row_idx == 0:  # Header row
                    pdf_row.append(Paragraph(f'<b>{cell_text}</b>', styles['body']))
                else:
                    pdf_row.append(Paragraph(cell_text, styles['body']))
            pdf_data.append(pdf_row)
        
        if not pdf_data:
            return None
        
        # Calculate column widths based on number of columns
        num_cols = len(pdf_data[0]) if pdf_data else 3
        available_width = 17 * cm
        col_width = available_width / num_cols
        col_widths = [col_width] * num_cols
        
        # Create table
        table = Table(pdf_data, colWidths=col_widths)
        
        # Style the table
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#e5e7eb')),  # Header bg
            ('TEXTCOLOR', (0, 0), (-1, 0), black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), self.primary_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, lightgrey),
            ('LINEBELOW', (0, 0), (-1, 0), 1, black),  # Header bottom line
        ]
        
        # Alternate row colors
        for i in range(1, len(pdf_data)):
            if i % 2 == 0:
                style_commands.append(('BACKGROUND', (0, i), (-1, i), HexColor('#f9fafb')))
        
        table.setStyle(TableStyle(style_commands))
        
        return table
    
    def _create_analyst_section(
        self,
        analyst_name: str,
        ticker: str,
        analysis_date: str,
        report_content: str,
        styles: dict
    ) -> list:
        """Create a single analyst report section with proper table support"""
        from reportlab.platypus import Spacer
        from reportlab.lib.units import cm
        
        elements = []
        
        # Section title
        elements.append(Paragraph(analyst_name, styles['section_title']))
        
        # Subtitle with ticker and date
        elements.append(Paragraph(f"{ticker} | {analysis_date}", styles['section_subtitle']))
        elements.append(Spacer(1, 0.5*cm))
        
        # Process report content
        report_content = self._replace_emojis(report_content)
        
        # Split into lines for table detection
        lines = report_content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                elements.append(Spacer(1, 0.2*cm))
                i += 1
                continue
            
            # Check if this is the start of a table
            if '|' in line and not line.startswith('#'):
                table_data, end_idx = self._parse_markdown_table(lines, i)
                if table_data and len(table_data) > 1:  # At least header + 1 row
                    pdf_table = self._create_pdf_table(table_data, styles)
                    if pdf_table:
                        elements.append(Spacer(1, 0.3*cm))
                        elements.append(pdf_table)
                        elements.append(Spacer(1, 0.3*cm))
                    i = end_idx
                    continue
            
            # Clean markdown from the line
            text = self._clean_markdown(line)
            text = self._escape_html(text)
            
            # Detect different content types for styling
            # 1. Report title - contains "報告" but must be a SHORT standalone title
            #    NOT a full sentence (should not contain commas or end with 。)
            is_report_title = (
                '報告' in text and 
                len(text) < 35 and 
                ',' not in text and 
                '，' not in text and
                not text.endswith('。')
            )
            if is_report_title:
                elements.append(Paragraph(text, styles['report_title']))
            # 2. Numbered section heading - SHORT lines that start with "數字." pattern
            #    Only treat as heading if line is SHORT (< 20 chars) - otherwise it's body text
            elif re.match(r'^\d+[\.\、]', text) and len(text) < 20:
                elements.append(Paragraph(text, styles['numbered_heading']))
            # 3. Regular body text (including long paragraphs that start with numbers)
            else:
                elements.append(Paragraph(text, styles['body']))
            
            i += 1
        
        return elements

