"""Tests for report generator module.

Issue #44: [BT-43] Report generator - PDF/HTML reports
"""

import json
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.backtest import (
    # Backtest engine
    BacktestResult,
    BacktestTrade,
    BacktestSnapshot,
    BacktestConfig,
    OrderSide,
    # Report generator
    ReportFormat,
    ReportSection,
    ChartType,
    ReportConfig,
    ChartData,
    ReportContent,
    ReportResult,
    ReportGenerator,
    create_report_generator,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_config() -> BacktestConfig:
    """Create sample backtest configuration."""
    return BacktestConfig(
        initial_capital=Decimal("100000"),
    )


@pytest.fixture
def sample_trades() -> list[BacktestTrade]:
    """Create sample trades for testing."""
    trades = []
    base_date = datetime(2023, 1, 3)

    # Winning trade
    trades.append(BacktestTrade(
        timestamp=base_date,
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        price=Decimal("150.00"),
        commission=Decimal("1.00"),
        slippage=Decimal("0.50"),
        pnl=Decimal("500.00"),
    ))

    # Losing trade
    trades.append(BacktestTrade(
        timestamp=base_date + timedelta(days=5),
        symbol="GOOGL",
        side=OrderSide.BUY,
        quantity=Decimal("50"),
        price=Decimal("100.00"),
        commission=Decimal("1.00"),
        slippage=Decimal("0.25"),
        pnl=Decimal("-200.00"),
    ))

    # Another winning trade
    trades.append(BacktestTrade(
        timestamp=base_date + timedelta(days=10),
        symbol="MSFT",
        side=OrderSide.BUY,
        quantity=Decimal("75"),
        price=Decimal("300.00"),
        commission=Decimal("1.50"),
        slippage=Decimal("0.75"),
        pnl=Decimal("750.00"),
    ))

    return trades


@pytest.fixture
def sample_snapshots() -> list[BacktestSnapshot]:
    """Create sample snapshots for testing."""
    snapshots = []
    base_date = datetime(2023, 1, 1)

    for i in range(30):
        equity = Decimal("100000") + Decimal(str(i * 100 - 50 * (i % 5)))
        snapshots.append(BacktestSnapshot(
            timestamp=base_date + timedelta(days=i),
            cash=equity * Decimal("0.3"),
            positions_value=equity * Decimal("0.7"),
            total_value=equity,
        ))

    return snapshots


@pytest.fixture
def sample_result(sample_trades, sample_snapshots) -> BacktestResult:
    """Create sample backtest result."""
    return BacktestResult(
        initial_capital=Decimal("100000"),
        final_value=Decimal("101050"),
        total_return=Decimal("1.05"),
        total_trades=3,
        winning_trades=2,
        losing_trades=1,
        win_rate=Decimal("66.67"),
        profit_factor=Decimal("6.25"),
        max_drawdown=Decimal("0.50"),
        sharpe_ratio=Decimal("1.85"),
        sortino_ratio=Decimal("2.50"),
        total_commission=Decimal("3.50"),
        total_slippage=Decimal("1.50"),
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 1, 30),
        trades=sample_trades,
        snapshots=sample_snapshots,
    )


# ============================================================================
# Test Enums
# ============================================================================

class TestReportFormat:
    """Tests for ReportFormat enum."""

    def test_values(self):
        """Test enum values."""
        assert ReportFormat.HTML.value == "html"
        assert ReportFormat.PDF.value == "pdf"
        assert ReportFormat.JSON.value == "json"
        assert ReportFormat.MARKDOWN.value == "markdown"

    def test_all_formats(self):
        """Test all formats exist."""
        formats = list(ReportFormat)
        assert len(formats) == 4


class TestReportSection:
    """Tests for ReportSection enum."""

    def test_values(self):
        """Test enum values."""
        assert ReportSection.SUMMARY.value == "summary"
        assert ReportSection.EQUITY_CURVE.value == "equity_curve"
        assert ReportSection.DRAWDOWN.value == "drawdown"
        assert ReportSection.TRADE_LIST.value == "trade_list"

    def test_all_sections(self):
        """Test all sections exist."""
        sections = list(ReportSection)
        assert len(sections) >= 8


class TestChartType:
    """Tests for ChartType enum."""

    def test_values(self):
        """Test enum values."""
        assert ChartType.LINE.value == "line"
        assert ChartType.BAR.value == "bar"
        assert ChartType.HEATMAP.value == "heatmap"


# ============================================================================
# Test Data Classes
# ============================================================================

class TestReportConfig:
    """Tests for ReportConfig dataclass."""

    def test_default_creation(self):
        """Test default configuration."""
        config = ReportConfig()
        assert config.title == "Backtest Report"
        assert config.author == ""
        assert config.chart_width == 800
        assert config.chart_height == 400
        assert config.decimal_places == 2
        assert config.include_trade_list is True
        assert config.max_trades_shown == 100
        assert config.include_timestamp is True

    def test_custom_creation(self):
        """Test custom configuration."""
        config = ReportConfig(
            title="My Report",
            author="Test Author",
            chart_width=1024,
            chart_height=768,
            decimal_places=4,
            include_trade_list=False,
            max_trades_shown=50,
        )
        assert config.title == "My Report"
        assert config.author == "Test Author"
        assert config.chart_width == 1024
        assert config.chart_height == 768
        assert config.decimal_places == 4
        assert config.include_trade_list is False
        assert config.max_trades_shown == 50

    def test_color_scheme(self):
        """Test default color scheme."""
        config = ReportConfig()
        assert "primary" in config.color_scheme
        assert "secondary" in config.color_scheme
        assert "success" in config.color_scheme
        assert "danger" in config.color_scheme

    def test_include_sections_default(self):
        """Test default sections include all."""
        config = ReportConfig()
        # Default includes all sections
        assert len(config.include_sections) > 0


class TestChartData:
    """Tests for ChartData dataclass."""

    def test_creation(self):
        """Test chart data creation."""
        chart = ChartData(
            chart_type=ChartType.LINE,
            title="Test Chart",
            x_data=[1, 2, 3],
            y_data=[10, 20, 30],
            x_label="X Axis",
            y_label="Y Axis",
        )
        assert chart.chart_type == ChartType.LINE
        assert chart.title == "Test Chart"
        assert chart.x_data == [1, 2, 3]
        assert chart.y_data == [10, 20, 30]
        assert chart.x_label == "X Axis"
        assert chart.y_label == "Y Axis"

    def test_default_values(self):
        """Test default values."""
        chart = ChartData(
            chart_type=ChartType.BAR,
            title="Test",
            x_data=[],
            y_data=[],
        )
        assert chart.x_label == ""
        assert chart.y_label == ""
        assert chart.series_names == []
        assert chart.colors == []


class TestReportContent:
    """Tests for ReportContent dataclass."""

    def test_creation(self):
        """Test content creation."""
        now = datetime.now()
        content = ReportContent(
            title="Test Report",
            generated_at=now,
        )
        assert content.title == "Test Report"
        assert content.generated_at == now
        assert content.sections == {}
        assert content.charts == {}
        assert content.metadata == {}


class TestReportResult:
    """Tests for ReportResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = ReportResult(
            success=True,
            output_path=Path("/tmp/report.html"),
            format=ReportFormat.HTML,
            file_size_bytes=1024,
            generation_time_ms=500,
        )
        assert result.success is True
        assert result.output_path == Path("/tmp/report.html")
        assert result.format == ReportFormat.HTML
        assert result.file_size_bytes == 1024
        assert result.generation_time_ms == 500
        assert result.error is None

    def test_failure_result(self):
        """Test failure result."""
        result = ReportResult(
            success=False,
            format=ReportFormat.PDF,
            error="PDF library not available",
        )
        assert result.success is False
        assert result.output_path is None
        assert result.error == "PDF library not available"


# ============================================================================
# Test ReportGenerator
# ============================================================================

class TestReportGenerator:
    """Tests for ReportGenerator class."""

    def test_initialization(self):
        """Test generator initialization."""
        generator = ReportGenerator()
        assert generator.config is not None
        assert generator.analyzer is not None

    def test_initialization_with_config(self):
        """Test initialization with custom config."""
        config = ReportConfig(title="Custom Title")
        generator = ReportGenerator(config=config)
        assert generator.config.title == "Custom Title"

    def test_generate_html(self, sample_result):
        """Test HTML generation."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            result = generator.generate_html(sample_result, output_path)

            assert result.success is True
            assert result.output_path == output_path
            assert result.format == ReportFormat.HTML
            assert result.file_size_bytes > 0
            assert output_path.exists()

    def test_generate_html_content(self, sample_result):
        """Test HTML content contains expected sections."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check structure
            assert "<!DOCTYPE html>" in content
            assert "<html" in content
            assert "</html>" in content

            # Check sections
            assert "Summary" in content
            assert "Trade Statistics" in content
            assert "Risk Metrics" in content

    def test_generate_json(self, sample_result):
        """Test JSON generation."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            result = generator.generate_json(sample_result, output_path)

            assert result.success is True
            assert result.format == ReportFormat.JSON
            assert output_path.exists()

            # Verify JSON is valid
            data = json.loads(output_path.read_text())
            assert "report" in data
            assert "backtest" in data
            assert "performance" in data
            assert "trades" in data

    def test_generate_json_structure(self, sample_result):
        """Test JSON structure is correct."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            generator.generate_json(sample_result, output_path)

            data = json.loads(output_path.read_text())

            # Check report metadata
            assert "title" in data["report"]
            assert "generated_at" in data["report"]

            # Check backtest data
            assert "initial_capital" in data["backtest"]
            assert "final_capital" in data["backtest"]

            # Check performance metrics
            assert "total_return" in data["performance"]
            assert "sharpe_ratio" in data["performance"]

    def test_generate_markdown(self, sample_result):
        """Test Markdown generation."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            result = generator.generate_markdown(sample_result, output_path)

            assert result.success is True
            assert result.format == ReportFormat.MARKDOWN
            assert output_path.exists()

    def test_generate_markdown_content(self, sample_result):
        """Test Markdown content structure."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            generator.generate_markdown(sample_result, output_path)

            content = output_path.read_text()

            # Check structure
            assert "# " in content  # Title
            assert "## Summary" in content
            assert "## Trade Statistics" in content
            assert "## Risk Metrics" in content
            assert "|" in content  # Tables

    def test_generate_pdf_fallback(self, sample_result):
        """Test PDF generation falls back to HTML if libraries unavailable."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.pdf"
            result = generator.generate_pdf(sample_result, output_path)

            # Should succeed but might fallback to HTML
            assert result.success is True
            # Either PDF worked or fell back to HTML
            assert result.output_path is not None

    def test_generate_generic(self, sample_result):
        """Test generic generate method."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test HTML
            html_path = Path(tmpdir) / "report.html"
            result = generator.generate(sample_result, html_path, ReportFormat.HTML)
            assert result.success is True
            assert result.format == ReportFormat.HTML

            # Test JSON
            json_path = Path(tmpdir) / "report.json"
            result = generator.generate(sample_result, json_path, ReportFormat.JSON)
            assert result.success is True
            assert result.format == ReportFormat.JSON

    def test_custom_title(self, sample_result):
        """Test custom report title."""
        config = ReportConfig(title="My Custom Report")
        generator = ReportGenerator(config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()
            assert "My Custom Report" in content

    def test_custom_author(self, sample_result):
        """Test custom author in report."""
        config = ReportConfig(author="Test Author")
        generator = ReportGenerator(config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()
            assert "Test Author" in content

    def test_max_trades_shown(self, sample_result):
        """Test max trades limit in report."""
        config = ReportConfig(max_trades_shown=1)
        generator = ReportGenerator(config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            generator.generate_json(sample_result, output_path)

            data = json.loads(output_path.read_text())
            # Should only show 1 trade
            assert len(data["trade_list"]) <= 1


class TestHTMLRendering:
    """Tests for HTML rendering."""

    def test_summary_metrics(self, sample_result):
        """Test summary metrics in HTML."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check metrics are present
            assert "Total Return" in content
            assert "Win Rate" in content
            assert "Sharpe Ratio" in content

    def test_trade_list_rendering(self, sample_result):
        """Test trade list in HTML."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check trade table
            assert "Trade List" in content
            assert "Symbol" in content
            assert "AAPL" in content

    def test_css_styling(self, sample_result):
        """Test CSS is included."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check CSS is present
            assert "<style>" in content
            assert "font-family" in content
            assert "color" in content

    def test_responsive_design(self, sample_result):
        """Test responsive design elements."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check viewport meta
            assert "viewport" in content
            # Check grid layout
            assert "grid" in content

    def test_color_scheme_applied(self, sample_result):
        """Test custom color scheme is applied."""
        config = ReportConfig(
            color_scheme={
                "primary": "#ff0000",
                "secondary": "#00ff00",
                "success": "#0000ff",
                "danger": "#ffff00",
                "warning": "#ff00ff",
                "background": "#ffffff",
                "text": "#000000",
                "border": "#cccccc",
            }
        )
        generator = ReportGenerator(config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()
            assert "#ff0000" in content  # primary color


class TestSVGCharts:
    """Tests for SVG chart generation."""

    def test_equity_curve_chart(self, sample_result):
        """Test equity curve SVG chart."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check SVG is present
            assert "<svg" in content
            assert "Equity Curve" in content

    def test_drawdown_chart(self, sample_result):
        """Test drawdown SVG chart."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check drawdown section
            assert "Drawdown" in content


class TestMonthlyReturns:
    """Tests for monthly returns heatmap."""

    def test_monthly_returns_section(self, sample_result):
        """Test monthly returns heatmap is generated."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            generator.generate_html(sample_result, output_path)

            content = output_path.read_text()

            # Check monthly returns section
            assert "Monthly Returns" in content
            assert "heatmap" in content


class TestErrorHandling:
    """Tests for error handling."""

    def test_invalid_output_path(self, sample_result):
        """Test handling of invalid output path."""
        generator = ReportGenerator()

        # Path to non-existent nested directory
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dirs" / "report.html"
            result = generator.generate_html(sample_result, output_path)

            # Should succeed (creates directories)
            assert result.success is True

    def test_empty_result(self):
        """Test handling of empty result."""
        empty_result = BacktestResult(
            initial_capital=Decimal("100000"),
            final_value=Decimal("100000"),
            total_return=Decimal("0"),
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            trades=[],
            snapshots=[],
        )

        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            result = generator.generate_html(empty_result, output_path)

            assert result.success is True
            assert output_path.exists()


class TestFactoryFunction:
    """Tests for factory function."""

    def test_create_report_generator(self):
        """Test factory function."""
        generator = create_report_generator(
            title="Factory Report",
            author="Factory Author",
            include_trade_list=True,
            max_trades=50,
        )

        assert generator.config.title == "Factory Report"
        assert generator.config.author == "Factory Author"
        assert generator.config.include_trade_list is True
        assert generator.config.max_trades_shown == 50

    def test_create_report_generator_defaults(self):
        """Test factory function with defaults."""
        generator = create_report_generator()

        assert generator.config.title == "Backtest Report"
        assert generator.config.author == ""


class TestModuleExports:
    """Tests for module exports."""

    def test_imports_from_package(self):
        """Test imports work from package."""
        from tradingagents.backtest import (
            ReportFormat,
            ReportSection,
            ChartType,
            ReportConfig,
            ChartData,
            ReportContent,
            ReportResult,
            ReportGenerator,
            create_report_generator,
        )

        # All imports should work
        assert ReportFormat is not None
        assert ReportSection is not None
        assert ChartType is not None
        assert ReportConfig is not None
        assert ChartData is not None
        assert ReportContent is not None
        assert ReportResult is not None
        assert ReportGenerator is not None
        assert create_report_generator is not None


class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self, sample_result):
        """Test complete report generation workflow."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate all formats
            html_result = generator.generate_html(
                sample_result,
                Path(tmpdir) / "report.html",
            )
            json_result = generator.generate_json(
                sample_result,
                Path(tmpdir) / "report.json",
            )
            md_result = generator.generate_markdown(
                sample_result,
                Path(tmpdir) / "report.md",
            )

            # All should succeed
            assert html_result.success is True
            assert json_result.success is True
            assert md_result.success is True

            # All files should exist
            assert (Path(tmpdir) / "report.html").exists()
            assert (Path(tmpdir) / "report.json").exists()
            assert (Path(tmpdir) / "report.md").exists()

    def test_with_pre_computed_analysis(self, sample_result):
        """Test using pre-computed analysis."""
        from tradingagents.backtest import ResultsAnalyzer

        analyzer = ResultsAnalyzer()
        analysis = analyzer.analyze(sample_result)

        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generator.generate_html(
                sample_result,
                Path(tmpdir) / "report.html",
                analysis=analysis,
            )

            assert result.success is True

    def test_generation_time_tracked(self, sample_result):
        """Test that generation time is tracked."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generator.generate_html(
                sample_result,
                Path(tmpdir) / "report.html",
            )

            assert result.generation_time_ms >= 0

    def test_file_size_tracked(self, sample_result):
        """Test that file size is tracked."""
        generator = ReportGenerator()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generator.generate_html(
                sample_result,
                Path(tmpdir) / "report.html",
            )

            assert result.file_size_bytes > 0
