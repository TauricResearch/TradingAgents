"""PDF report generator for TradingAgents analysis results."""
import datetime
import re
from pathlib import Path
from typing import Dict, Any
import io
from cli.chart_generator import (
    generate_stock_price_chart,
    generate_volume_chart,
    generate_technical_indicators_chart
)


def generate_pdf_report(
    final_state: Dict[str, Any],
    ticker: str,
    analysis_date: str,
    output_path: Path,
) -> Path:
    """
    Generate a comprehensive PDF report from the analysis results.

    Args:
        final_state: The final state dictionary containing all analysis results
        ticker: The stock ticker symbol
        analysis_date: The analysis date
        output_path: Path where the PDF should be saved

    Returns:
        Path to the generated PDF file
    """
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.platypus import Table, TableStyle, Image
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    except ImportError:
        raise ImportError(
            "reportlab is required for PDF generation. "
            "Install it with: pip install reportlab"
        )

    # Create the PDF document
    pdf_file = output_path / f"{ticker}_{analysis_date}_analysis_report.pdf"
    doc = SimpleDocTemplate(
        str(pdf_file),
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )

    # Container for the 'Flowable' objects
    elements = []

    # Define styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name='CustomHeading1',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=12,
    ))
    styles.add(ParagraphStyle(
        name='CustomHeading2',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=10,
        spaceBefore=10,
    ))
    styles.add(ParagraphStyle(
        name='CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
    ))

    # Title Page
    title = Paragraph(
        f"TradingAgents Analysis Report<br/>{ticker}",
        styles['CustomTitle']
    )
    elements.append(title)
    elements.append(Spacer(1, 12))

    # Metadata table
    metadata = [
        ['Analysis Date:', analysis_date],
        ['Report Generated:', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ['Ticker Symbol:', ticker],
    ]

    t = Table(metadata, colWidths=[2*inch, 4*inch])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 30))

    # Generate and add charts
    elements.append(PageBreak())
    elements.append(Paragraph('Market Data Visualizations', styles['CustomHeading1']))
    elements.append(Spacer(1, 12))

    # Stock price chart
    print("Generating stock price chart...")
    price_chart = generate_stock_price_chart(ticker, analysis_date)
    if price_chart:
        img = Image(price_chart, width=6*inch, height=3.6*inch)
        elements.append(img)
        elements.append(Spacer(1, 20))

    # Volume chart
    print("Generating volume chart...")
    volume_chart = generate_volume_chart(ticker, analysis_date)
    if volume_chart:
        img = Image(volume_chart, width=6*inch, height=2.4*inch)
        elements.append(img)
        elements.append(Spacer(1, 20))

    # Technical indicators chart
    print("Generating technical indicators chart...")
    tech_chart = generate_technical_indicators_chart(ticker, analysis_date)
    if tech_chart:
        img = Image(tech_chart, width=6*inch, height=4.8*inch)
        elements.append(img)
        elements.append(Spacer(1, 20))

    # Helper function to clean and escape text for PDF
    def clean_text(text: str) -> str:
        """Clean text and properly escape for reportlab."""
        # Remove markdown headers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Escape special XML/HTML characters first
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')

        # Now we can safely add our formatting tags
        # Convert markdown bold (**text** or __text__) to HTML bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

        # Convert markdown italic (*text* or _text_) to HTML italic
        # Be careful not to match ** or __
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
        text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', text)

        # Remove any remaining problematic characters
        text = text.replace('\r', '')

        return text

    # Helper function to add section
    def add_section(title: str, content: str):
        if content:
            elements.append(Paragraph(title, styles['CustomHeading1']))
            elements.append(Spacer(1, 12))

            # Clean the content
            content = clean_text(content)

            # Split content into paragraphs
            paragraphs = content.split('\n\n')
            for para in paragraphs:
                para = para.strip()
                if para:
                    # Replace single newlines with spaces, but preserve structure
                    para = para.replace('\n', ' ')
                    # Clean up multiple spaces
                    para = re.sub(r'\s+', ' ', para)
                    try:
                        elements.append(Paragraph(para, styles['CustomBody']))
                    except Exception as e:
                        # If there's still an error, add as plain text
                        print(f"Warning: Could not parse paragraph, adding as plain text: {e}")
                        elements.append(Paragraph(para.replace('<', '&lt;').replace('>', '&gt;'), styles['CustomBody']))
            elements.append(Spacer(1, 20))

    # I. Analyst Team Reports
    elements.append(PageBreak())
    elements.append(Paragraph('I. Analyst Team Reports', styles['CustomHeading1']))
    elements.append(Spacer(1, 20))

    if final_state.get('market_report'):
        add_section('Market Analysis', final_state['market_report'])

    if final_state.get('sentiment_report'):
        add_section('Social Sentiment Analysis', final_state['sentiment_report'])

    if final_state.get('news_report'):
        add_section('News Analysis', final_state['news_report'])

    if final_state.get('fundamentals_report'):
        add_section('Fundamentals Analysis', final_state['fundamentals_report'])

    # II. Research Team Reports
    if final_state.get('investment_debate_state'):
        elements.append(PageBreak())
        elements.append(Paragraph('II. Research Team Decision', styles['CustomHeading1']))
        elements.append(Spacer(1, 20))

        debate_state = final_state['investment_debate_state']

        if debate_state.get('bull_history'):
            add_section('Bull Researcher Analysis', debate_state['bull_history'])

        if debate_state.get('bear_history'):
            add_section('Bear Researcher Analysis', debate_state['bear_history'])

        if debate_state.get('judge_decision'):
            add_section('Research Manager Decision', debate_state['judge_decision'])

    # III. Trading Team Reports
    if final_state.get('trader_investment_plan'):
        elements.append(PageBreak())
        elements.append(Paragraph('III. Trading Team Plan', styles['CustomHeading1']))
        elements.append(Spacer(1, 20))
        add_section('Trader Plan', final_state['trader_investment_plan'])

    # IV. Risk Management Team Reports
    if final_state.get('risk_debate_state'):
        elements.append(PageBreak())
        elements.append(Paragraph('IV. Risk Management Team Decision', styles['CustomHeading1']))
        elements.append(Spacer(1, 20))

        risk_state = final_state['risk_debate_state']

        if risk_state.get('risky_history'):
            add_section('Aggressive Analyst Analysis', risk_state['risky_history'])

        if risk_state.get('safe_history'):
            add_section('Conservative Analyst Analysis', risk_state['safe_history'])

        if risk_state.get('neutral_history'):
            add_section('Neutral Analyst Analysis', risk_state['neutral_history'])

        # V. Portfolio Manager Decision
        if risk_state.get('judge_decision'):
            elements.append(PageBreak())
            elements.append(Paragraph('V. Portfolio Manager Decision', styles['CustomHeading1']))
            elements.append(Spacer(1, 20))
            add_section('Final Decision', risk_state['judge_decision'])

    # Build PDF
    doc.build(elements)

    return pdf_file
