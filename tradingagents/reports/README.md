# TradingAgents Reports Module

This module provides comprehensive report generation capabilities for TradingAgents analysis results.

## Structure

```
tradingagents/reports/
├── __init__.py                 # Main module interface
├── README.md                   # This documentation
├── generators/                 # Report generators
│   ├── __init__.py
│   └── pdf_generator.py       # PDF generation with Playwright/WeasyPrint
├── formatters/                 # Content formatters
│   ├── __init__.py
│   └── report_formatter.py    # Structures analysis data for reports
└── converters/                 # Content converters
    ├── __init__.py
    └── html_converter.py       # Rich console to HTML conversion
```

## Features

### 🎯 **Automatic PDF Generation**
- Generates PDF reports automatically after each analysis
- Uses Playwright as primary engine (cross-platform, no system dependencies)
- WeasyPrint fallback for compatibility
- Professional styling with proper sections and formatting

### 📋 **Structured Reports**
Reports follow the exact terminal structure:
1. **I. Analyst Team Reports** - Market/Social/News/Fundamentals analysts
2. **II. Research Team Decision** - Bull/Bear/Research Manager analysis
3. **III. Trading Team Plan** - Trader's strategic recommendations
4. **IV. Risk Management Team Decision** - Risk analysts' perspectives
5. **V. Portfolio Manager Decision** - Final investment decision

### 🎨 **Rich Formatting**
- Color-coded sections matching terminal output
- Professional panels and styling
- Markdown content conversion
- Responsive layout for different content types

## Usage

The reports module is automatically integrated into the main CLI workflow. No manual intervention required.

```python
from tradingagents.reports import TradingReportPDFGenerator

# Used automatically in cli/main.py
generator = TradingReportPDFGenerator()
pdf_path = generator.generate_pdf(analysis_data, ticker, date)
```

## Configuration

PDF generation can be configured in `tradingagents/default_config.py`:

```python
"pdf_generation": {
    "enabled": True,
    "output_dir": "results",
    "page_format": "A4",
    "margin": "2cm",
    "font_family": "Arial, sans-serif",
    "font_size": "12pt",
    "auto_generate": True,
}
```

## Dependencies

- **playwright**: Primary PDF generation engine
- **weasyprint**: Fallback PDF generation (optional)
- **rich**: Terminal styling and content formatting
- **jinja2**: HTML templating

## Output

Generated files are saved to:
- `results/{ticker}/{date}/analysis_report.pdf` - Main PDF report
- `results/{ticker}/{date}/analysis_report.html` - HTML backup

Example file sizes:
- PDF: ~900KB (comprehensive analysis with all sections)
- HTML: ~45KB (structured content backup)