"""PDF report generator for portfolio analysis results."""
import datetime
import io
import re
from pathlib import Path
from typing import Dict, Any

from tradingagents.portfolio.models import PortfolioAnalysisResult


def generate_portfolio_charts(result: PortfolioAnalysisResult) -> Dict[str, io.BytesIO]:
    """
    Generate charts for portfolio analysis.

    Args:
        result: Portfolio analysis result

    Returns:
        Dictionary of chart names to BytesIO buffers
    """
    charts = {}

    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import numpy as np
    except ImportError:
        print("Warning: matplotlib required for chart generation")
        return charts

    portfolio = result.portfolio
    metrics = result.portfolio_metrics

    # Chart 1: Portfolio Allocation Pie Chart
    try:
        fig, ax = plt.subplots(figsize=(8, 8))
        weights = portfolio.get_position_weights()

        colors = plt.cm.Set3(np.linspace(0, 1, len(weights)))
        wedges, texts, autotexts = ax.pie(
            weights.values(),
            labels=weights.keys(),
            autopct='%1.1f%%',
            colors=colors,
            startangle=90
        )

        # Make percentage text bold
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(10)

        ax.set_title('Portfolio Allocation', fontsize=16, fontweight='bold', pad=20)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        charts['allocation'] = buf
    except Exception as e:
        print(f"Error generating allocation chart: {e}")

    # Chart 2: Correlation Heatmap
    if 'correlation_matrix' in metrics:
        try:
            import seaborn as sns

            corr_matrix = metrics['correlation_matrix']
            tickers = list(corr_matrix.keys())

            # Convert to numpy array
            corr_array = np.array([[corr_matrix[t1][t2] for t2 in tickers] for t1 in tickers])

            fig, ax = plt.subplots(figsize=(10, 8))
            sns.heatmap(
                corr_array,
                annot=True,
                fmt='.2f',
                cmap='coolwarm',
                center=0,
                vmin=-1,
                vmax=1,
                square=True,
                linewidths=1,
                cbar_kws={"shrink": 0.8},
                ax=ax,
                xticklabels=tickers,
                yticklabels=tickers
            )

            ax.set_title('Position Correlation Matrix', fontsize=16, fontweight='bold', pad=20)
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            charts['correlation'] = buf
        except ImportError:
            print("Warning: seaborn required for correlation heatmap")
        except Exception as e:
            print(f"Error generating correlation chart: {e}")

    # Chart 3: Sector Allocation
    if 'sector_weights' in metrics:
        try:
            sector_weights = metrics['sector_weights']

            fig, ax = plt.subplots(figsize=(10, 6))
            sectors = list(sector_weights.keys())
            weights_list = list(sector_weights.values())

            colors = plt.cm.Paired(np.linspace(0, 1, len(sectors)))
            bars = ax.barh(sectors, weights_list, color=colors)

            ax.set_xlabel('Portfolio Weight (%)', fontsize=12)
            ax.set_title('Sector Allocation', fontsize=16, fontweight='bold', pad=20)
            ax.grid(True, alpha=0.3, axis='x')

            # Add value labels on bars
            for bar, weight in zip(bars, weights_list):
                width = bar.get_width()
                ax.text(
                    width,
                    bar.get_y() + bar.get_height() / 2,
                    f' {weight:.1f}%',
                    ha='left',
                    va='center',
                    fontweight='bold'
                )

            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            charts['sectors'] = buf
        except Exception as e:
            print(f"Error generating sector chart: {e}")

    # Chart 4: Position Performance
    try:
        fig, ax = plt.subplots(figsize=(10, 6))

        tickers = []
        performance = []
        colors_list = []

        for ticker, position in portfolio.positions.items():
            if position.unrealized_gain_loss_pct is not None:
                tickers.append(ticker)
                perf = position.unrealized_gain_loss_pct
                performance.append(perf)
                colors_list.append('green' if perf >= 0 else 'red')

        bars = ax.barh(tickers, performance, color=colors_list, alpha=0.7)

        ax.set_xlabel('Unrealized Gain/Loss (%)', fontsize=12)
        ax.set_title('Position Performance', fontsize=16, fontweight='bold', pad=20)
        ax.axvline(x=0, color='black', linestyle='-', linewidth=0.8)
        ax.grid(True, alpha=0.3, axis='x')

        # Add value labels
        for bar, perf in zip(bars, performance):
            width = bar.get_width()
            ax.text(
                width,
                bar.get_y() + bar.get_height() / 2,
                f' {perf:+.1f}%',
                ha='left' if width >= 0 else 'right',
                va='center',
                fontweight='bold'
            )

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        charts['performance'] = buf
    except Exception as e:
        print(f"Error generating performance chart: {e}")

    return charts


def generate_portfolio_pdf_report(
    result: PortfolioAnalysisResult,
    output_path: Path
) -> Path:
    """
    Generate a comprehensive PDF report for portfolio analysis.

    Args:
        result: Portfolio analysis result
        output_path: Directory where the PDF should be saved

    Returns:
        Path to the generated PDF file
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.platypus import Table, TableStyle, Image
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    except ImportError:
        raise ImportError(
            "reportlab is required for PDF generation. "
            "Install it with: pip install reportlab"
        )

    portfolio = result.portfolio

    # Create the PDF document
    pdf_file = output_path / f"portfolio_analysis_{portfolio.analysis_date}.pdf"
    doc = SimpleDocTemplate(
        str(pdf_file),
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
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
        name='CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
    ))

    # Title
    title = Paragraph(
        f"Portfolio Analysis Report<br/>{portfolio.name}",
        styles['CustomTitle']
    )
    elements.append(title)
    elements.append(Spacer(1, 12))

    # Metadata
    metadata = [
        ['Analysis Date:', portfolio.analysis_date],
        ['Report Generated:', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ['Number of Positions:', str(len(portfolio.positions))],
        ['Total Cost Basis:', f"${portfolio.total_cost_basis:,.2f}"],
    ]

    if portfolio.total_market_value:
        metadata.append(['Total Market Value:', f"${portfolio.total_market_value:,.2f}"])
        metadata.append([
            'Total P/L:',
            f"${portfolio.total_unrealized_gain_loss:,.2f} "
            f"({portfolio.total_unrealized_gain_loss_pct:+.2f}%)"
        ])

    t = Table(metadata, colWidths=[2.5*inch, 3.5*inch])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 30))

    # Helper function to clean text for PDF
    def clean_text(text: str) -> str:
        """Clean text and properly escape for reportlab."""
        # Escape special XML/HTML characters first
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')

        # Convert markdown bold (**text**) to HTML bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

        # Convert markdown italic (*text*) to HTML italic
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)

        # Remove markdown headers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        return text

    # Generate charts
    print("Generating portfolio charts...")
    charts = generate_portfolio_charts(result)

    # Add charts
    if charts:
        elements.append(PageBreak())
        elements.append(Paragraph('Portfolio Visualizations', styles['CustomHeading1']))
        elements.append(Spacer(1, 12))

        if 'allocation' in charts:
            img = Image(charts['allocation'], width=5*inch, height=5*inch)
            elements.append(img)
            elements.append(Spacer(1, 20))

        if 'performance' in charts:
            img = Image(charts['performance'], width=6*inch, height=3.6*inch)
            elements.append(img)
            elements.append(Spacer(1, 20))

        if 'sectors' in charts:
            elements.append(PageBreak())
            img = Image(charts['sectors'], width=6*inch, height=3.6*inch)
            elements.append(img)
            elements.append(Spacer(1, 20))

        if 'correlation' in charts:
            img = Image(charts['correlation'], width=6*inch, height=4.8*inch)
            elements.append(img)
            elements.append(Spacer(1, 20))

    # Portfolio Overview
    elements.append(PageBreak())
    if result.portfolio_recommendation:
        elements.append(Paragraph('Portfolio Overview', styles['CustomHeading1']))
        elements.append(Spacer(1, 12))
        for line in result.portfolio_recommendation.split('\n'):
            if line.strip():
                cleaned_line = clean_text(line)
                try:
                    elements.append(Paragraph(cleaned_line, styles['CustomBody']))
                except Exception as e:
                    print(f"Warning: Could not parse line, adding as plain text: {e}")
                    elements.append(Paragraph(cleaned_line.replace('<', '&lt;').replace('>', '&gt;'), styles['CustomBody']))

    # Risk Assessment
    elements.append(PageBreak())
    if result.risk_assessment:
        elements.append(Paragraph('Risk Assessment', styles['CustomHeading1']))
        elements.append(Spacer(1, 12))
        for line in result.risk_assessment.split('\n'):
            if line.strip():
                cleaned_line = clean_text(line)
                try:
                    elements.append(Paragraph(cleaned_line, styles['CustomBody']))
                except Exception as e:
                    print(f"Warning: Could not parse line, adding as plain text: {e}")
                    elements.append(Paragraph(cleaned_line.replace('<', '&lt;').replace('>', '&gt;'), styles['CustomBody']))

    # Rebalancing Suggestions
    if result.rebalancing_suggestions:
        elements.append(PageBreak())
        elements.append(Paragraph('Rebalancing Suggestions', styles['CustomHeading1']))
        elements.append(Spacer(1, 12))
        for suggestion in result.rebalancing_suggestions:
            text = f"• [{suggestion['type']}] {suggestion['ticker']}: {suggestion['reason']}"
            elements.append(Paragraph(text, styles['CustomBody']))

    # Individual Stock Analyses
    elements.append(PageBreak())
    elements.append(Paragraph('Individual Stock Analyses', styles['CustomHeading1']))
    elements.append(Spacer(1, 20))

    for ticker, analysis in result.individual_analyses.items():
        if not analysis.get('success'):
            elements.append(Paragraph(f"{ticker}: Analysis Failed", styles['Heading2']))
            elements.append(Paragraph(f"Error: {analysis.get('error', 'Unknown error')}", styles['CustomBody']))
            elements.append(Spacer(1, 20))
            continue

        elements.append(Paragraph(ticker, styles['Heading2']))
        decision = analysis.get('decision', 'No decision')
        elements.append(Paragraph(f"<b>Decision:</b> {decision}", styles['CustomBody']))
        elements.append(Spacer(1, 20))

    # Build PDF
    doc.build(elements)

    return pdf_file
