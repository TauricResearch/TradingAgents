"""Tests for tradingagents.graph.chart_renderer module.

Tests cover:
- Chart rendering from ChartJSON
- PNG output validation
- Error handling for invalid data
- No LLM imports in module
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tradingagents.graph.transform import ChartJSON, ChartInfo, PriceHistory, ReferenceLine
from tradingagents.graph.chart_renderer import (
    draw_chart,
    validate_chart_image,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_chart_json() -> ChartJSON:
    """Sample ChartJSON for testing."""
    return ChartJSON(
        chart_info=ChartInfo(
            title="Test Chart BTC/USDT",
            current_price=78068.70,
            y_axis_range=[72000, 91000],
            x_label="Time",
            y_label="Price (USDT)",
        ),
        price_history=PriceHistory(
            dates=["17/04", "18/04", "19/04", "20/04", "21/04"],
            prices=[77736, 75500, 73758, 76000, 77500],
        ),
        reference_lines=[
            ReferenceLine(
                price=89262,
                label="TP Max",
                color="green",
                linestyle="solid",
                linewidth=1.5,
                align="right",
            ),
            ReferenceLine(
                price=78068,
                label="ENTRY",
                color="orange",
                linestyle="solid",
                linewidth=2.0,
                align="left",
            ),
            ReferenceLine(
                price=76500,
                label="HARD SL",
                color="darkred",
                linestyle="dashdot",
                linewidth=2.0,
                align="right",
            ),
        ],
    )


@pytest.fixture
def output_path(tmp_path: Path) -> Path:
    """Temporary output path for chart PNG."""
    return tmp_path / "chart.png"


# ---------------------------------------------------------------------------
# draw_chart Tests
# ---------------------------------------------------------------------------


class TestDrawChart:
    """Tests for draw_chart function."""

    def test_creates_png_file(self, sample_chart_json: ChartJSON, output_path: Path):
        """draw_chart creates a PNG file."""
        result = draw_chart(sample_chart_json, output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_png_is_valid_image(self, sample_chart_json: ChartJSON, output_path: Path):
        """Output PNG is a valid image."""
        draw_chart(sample_chart_json, output_path)

        assert validate_chart_image(output_path)

    def test_creates_parent_directories(self, sample_chart_json: ChartJSON, tmp_path: Path):
        """Creates parent directories if they don't exist."""
        output_path = tmp_path / "nested" / "dir" / "chart.png"
        result = draw_chart(sample_chart_json, output_path)

        assert result.exists()
        assert validate_chart_image(result)

    def test_raises_value_error_on_dates_prices_mismatch(self, output_path: Path):
        """Raises ValueError when dates and prices have different lengths."""
        # Now validation happens at Pydantic level, not in draw_chart
        with pytest.raises(ValidationError, match="must have equal length"):
            PriceHistory(
                dates=["01/01", "02/01", "03/01"],
                prices=[100, 200],  # Mismatch: 3 dates, 2 prices
            )

    def test_raises_value_error_on_insufficient_data_points(self, output_path: Path):
        """Raises ValueError when less than 2 data points."""
        invalid_chart = ChartJSON(
            chart_info=ChartInfo(
                title="Test",
                current_price=100.0,
                y_axis_range=[90, 110],
            ),
            price_history=PriceHistory(
                dates=["01/01"],
                prices=[100],  # Only 1 data point
            ),
            reference_lines=[
                ReferenceLine(price=100, label="Test"),
            ],
        )

        with pytest.raises(ValueError, match="at least 2 data points"):
            draw_chart(invalid_chart, output_path)

    def test_renders_reference_lines(self, sample_chart_json: ChartJSON, output_path: Path):
        """Chart includes all reference lines."""
        draw_chart(sample_chart_json, output_path)

        # We can't easily verify visual content, but we can verify the file was created
        # and has reasonable size (indicating content was rendered)
        assert output_path.stat().st_size > 1000  # Should be at least 1KB

    def test_handles_various_linestyles(self, output_path: Path):
        """Handles various line styles (solid, dashed, dotted, dashdot)."""
        chart = ChartJSON(
            chart_info=ChartInfo(
                title="Test",
                current_price=100.0,
                y_axis_range=[90, 110],
            ),
            price_history=PriceHistory(
                dates=["01/01", "02/01"],
                prices=[100, 105],
            ),
            reference_lines=[
                ReferenceLine(price=110, label="Solid", linestyle="solid"),
                ReferenceLine(price=105, label="Dashed", linestyle="dashed"),
                ReferenceLine(price=95, label="Dotted", linestyle="dotted"),
                ReferenceLine(price=90, label="Dashdot", linestyle="dashdot"),
            ],
        )

        result = draw_chart(chart, output_path)
        assert result.exists()

    def test_handles_left_and_right_alignment(self, output_path: Path):
        """Handles left and right label alignment."""
        chart = ChartJSON(
            chart_info=ChartInfo(
                title="Test",
                current_price=100.0,
                y_axis_range=[90, 110],
            ),
            price_history=PriceHistory(
                dates=["01/01", "02/01"],
                prices=[100, 105],
            ),
            reference_lines=[
                ReferenceLine(price=110, label="Right", align="right"),
                ReferenceLine(price=90, label="Left", align="left"),
            ],
        )

        result = draw_chart(chart, output_path)
        assert result.exists()

    def test_handles_various_colors(self, output_path: Path):
        """Handles various color specifications."""
        chart = ChartJSON(
            chart_info=ChartInfo(
                title="Test",
                current_price=100.0,
                y_axis_range=[90, 110],
            ),
            price_history=PriceHistory(
                dates=["01/01", "02/01"],
                prices=[100, 105],
            ),
            reference_lines=[
                ReferenceLine(price=110, label="Green", color="green"),
                ReferenceLine(price=105, label="Red", color="red"),
                ReferenceLine(price=95, label="Blue", color="blue"),
                ReferenceLine(price=90, label="Orange", color="orange"),
                ReferenceLine(price=85, label="DarkRed", color="darkred"),
            ],
        )

        result = draw_chart(chart, output_path)
        assert result.exists()


# ---------------------------------------------------------------------------
# validate_chart_image Tests
# ---------------------------------------------------------------------------


class TestValidateChartImage:
    """Tests for validate_chart_image function."""

    def test_validates_valid_png(self, sample_chart_json: ChartJSON, output_path: Path):
        """Validates a valid PNG file."""
        draw_chart(sample_chart_json, output_path)
        assert validate_chart_image(output_path)

    def test_rejects_nonexistent_file(self, tmp_path: Path):
        """Rejects a nonexistent file."""
        nonexistent = tmp_path / "nonexistent.png"
        assert not validate_chart_image(nonexistent)

    def test_rejects_invalid_image(self, tmp_path: Path):
        """Rejects an invalid image file."""
        invalid_file = tmp_path / "invalid.png"
        invalid_file.write_text("not an image")
        assert not validate_chart_image(invalid_file)


# ---------------------------------------------------------------------------
# No LLM Import Test
# ---------------------------------------------------------------------------


class TestNoLLMImports:
    """Verify chart_renderer does not import LLM modules."""

    def test_no_llm_client_imports(self):
        """Module should not import from llm_clients."""
        import tradingagents.graph.chart_renderer as module

        source = Path(module.__file__).read_text()

        # Should not import from llm_clients
        assert "from tradingagents.llm_clients" not in source
        assert "import tradingagents.llm_clients" not in source

    def test_no_http_calls_in_draw_chart(self, sample_chart_json: ChartJSON, output_path: Path):
        """draw_chart should not make HTTP calls."""
        with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
            draw_chart(sample_chart_json, output_path)

            # No HTTP calls should be made
            mock_get.assert_not_called()
            mock_post.assert_not_called()
