"""Tests for cli.notion_chart_publisher module.

Tests cover:
- Chart PNG + JSON metadata publishing to Notion
- Graceful fallback on failure
- API key handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.graph.transform import ChartJSON, ChartInfo, PriceHistory, ReferenceLine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_chart_json_dict() -> dict:
    """Sample chart JSON dict for testing."""
    return {
        "chart_info": {
            "title": "Test Chart BTC/USDT",
            "current_price": 78068.70,
            "y_axis_range": [72000, 91000],
            "x_label": "Time",
            "y_label": "Price (USDT)",
        },
        "price_history": {
            "dates": ["17/04", "18/04", "19/04"],
            "prices": [77736, 75500, 73758],
        },
        "reference_lines": [
            {
                "price": 89262,
                "label": "TP Max",
                "color": "green",
                "linestyle": "solid",
                "linewidth": 1.5,
                "align": "right",
            },
            {
                "price": 76500,
                "label": "HARD SL",
                "color": "darkred",
                "linestyle": "dashdot",
                "linewidth": 2.0,
                "align": "right",
            },
        ],
    }


@pytest.fixture
def sample_chart_png(tmp_path: Path) -> Path:
    """Create a sample PNG file for testing."""
    # Create a minimal valid PNG file
    png_path = tmp_path / "chart.png"
    # PNG magic bytes + minimal IHDR and IEND chunks
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D,  # IHDR length
        0x49, 0x48, 0x44, 0x52,  # IHDR type
        0x00, 0x00, 0x00, 0x01,  # width = 1
        0x00, 0x00, 0x00, 0x01,  # height = 1
        0x08, 0x02,  # bit depth = 8, color type = 2 (RGB)
        0x00, 0x00, 0x00,  # compression, filter, interlace
        0x90, 0x77, 0x53, 0xDE,  # IHDR CRC
        0x00, 0x00, 0x00, 0x00,  # IEND length
        0x49, 0x45, 0x4E, 0x44,  # IEND type
        0xAE, 0x42, 0x60, 0x82,  # IEND CRC
    ])
    png_path.write_bytes(png_data)
    return png_path


# ---------------------------------------------------------------------------
# publish_chart_to_notion Tests
# ---------------------------------------------------------------------------


class TestPublishChartToNotion:
    """Tests for publish_chart_to_notion function."""

    def test_skips_without_api_key(
        self, sample_chart_png: Path, sample_chart_json_dict: dict, tmp_path: Path
    ):
        """Skips publishing if NOTION_API_KEY is not set."""
        from cli.notion_chart_publisher import publish_chart_to_notion

        with patch.dict("os.environ", {"NOTION_API_KEY": ""}, clear=False):
            # Should not raise, just log warning and return
            publish_chart_to_notion(
                sample_chart_png,
                sample_chart_json_dict,
                "test-page-id",
                api_key=None,
            )

    def test_skips_if_png_not_found(
        self, sample_chart_json_dict: dict, tmp_path: Path
    ):
        """Skips publishing if PNG file doesn't exist."""
        from cli.notion_chart_publisher import publish_chart_to_notion

        nonexistent = tmp_path / "nonexistent.png"
        # Should not raise, just log warning and return
        publish_chart_to_notion(
            nonexistent,
            sample_chart_json_dict,
            "test-page-id",
            api_key="test-key",
        )

    def test_appends_blocks_to_page(
        self, sample_chart_png: Path, sample_chart_json_dict: dict
    ):
        """Appends blocks to Notion page."""
        from cli.notion_chart_publisher import publish_chart_to_notion

        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_patch.return_value = mock_response

            publish_chart_to_notion(
                sample_chart_png,
                sample_chart_json_dict,
                "test-page-id-12345678901234567890123456789012",
                api_key="test-key",
            )

            # Verify API was called
            mock_patch.assert_called_once()
            call_args = mock_patch.call_args

            # Verify URL contains page ID
            assert "test-page-id-12345678901234567890123456789012" in call_args[0][0]

            # Verify blocks were included
            request_data = call_args[1]["json"]
            assert "children" in request_data
            assert len(request_data["children"]) > 0

    def test_includes_chart_info_callout(
        self, sample_chart_png: Path, sample_chart_json_dict: dict
    ):
        """Includes chart info as callout block."""
        from cli.notion_chart_publisher import publish_chart_to_notion

        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_patch.return_value = mock_response

            publish_chart_to_notion(
                sample_chart_png,
                sample_chart_json_dict,
                "test-page-id",
                api_key="test-key",
            )

            request_data = mock_patch.call_args[1]["json"]
            blocks = request_data["children"]

            # Find callout block
            callout_blocks = [b for b in blocks if b.get("type") == "callout"]
            assert len(callout_blocks) > 0

            # Verify chart info is in callout
            callout_text = callout_blocks[0]["callout"]["rich_text"][0]["text"]["content"]
            assert "Test Chart BTC/USDT" in callout_text

    def test_includes_reference_lines_table(
        self, sample_chart_png: Path, sample_chart_json_dict: dict
    ):
        """Includes reference lines as table block."""
        from cli.notion_chart_publisher import publish_chart_to_notion

        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_patch.return_value = mock_response

            publish_chart_to_notion(
                sample_chart_png,
                sample_chart_json_dict,
                "test-page-id",
                api_key="test-key",
            )

            request_data = mock_patch.call_args[1]["json"]
            blocks = request_data["children"]

            # Find table block
            table_blocks = [b for b in blocks if b.get("type") == "table"]
            assert len(table_blocks) > 0

            # Verify table has correct headers
            table = table_blocks[0]["table"]
            assert table["has_column_header"] is True

    def test_handles_api_error_gracefully(
        self, sample_chart_png: Path, sample_chart_json_dict: dict
    ):
        """Handles Notion API error gracefully."""
        from cli.notion_chart_publisher import publish_chart_to_notion

        with patch("requests.patch") as mock_patch:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_patch.return_value = mock_response

            # Should not raise, just log warning
            publish_chart_to_notion(
                sample_chart_png,
                sample_chart_json_dict,
                "test-page-id",
                api_key="test-key",
            )

    def test_handles_network_error_gracefully(
        self, sample_chart_png: Path, sample_chart_json_dict: dict
    ):
        """Handles network error gracefully."""
        from cli.notion_chart_publisher import publish_chart_to_notion
        import requests

        with patch("requests.patch") as mock_patch:
            mock_patch.side_effect = requests.RequestException("Network error")

            # Should not raise, just log warning
            publish_chart_to_notion(
                sample_chart_png,
                sample_chart_json_dict,
                "test-page-id",
                api_key="test-key",
            )

    def test_uses_env_api_key_if_not_provided(
        self, sample_chart_png: Path, sample_chart_json_dict: dict
    ):
        """Uses NOTION_API_KEY from environment if not provided."""
        from cli.notion_chart_publisher import publish_chart_to_notion

        with patch.dict("os.environ", {"NOTION_API_KEY": "env-api-key"}, clear=False):
            with patch("requests.patch") as mock_patch:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_patch.return_value = mock_response

                publish_chart_to_notion(
                    sample_chart_png,
                    sample_chart_json_dict,
                    "test-page-id",
                    api_key=None,  # Not provided, should use env
                )

                # Verify Authorization header uses env key
                call_kwargs = mock_patch.call_args[1]
                headers = call_kwargs["headers"]
                assert "Bearer env-api-key" in headers["Authorization"]


# ---------------------------------------------------------------------------
# upload_image_to_notion Tests
# ---------------------------------------------------------------------------


class TestUploadImageToNotion:
    """Tests for upload_image_to_notion function."""

    def test_skips_without_api_key(self, sample_chart_png: Path):
        """Skips upload if NOTION_API_KEY is not set."""
        from cli.notion_chart_publisher import upload_image_to_notion

        with patch.dict("os.environ", {"NOTION_API_KEY": ""}, clear=False):
            result = upload_image_to_notion(sample_chart_png, api_key=None)
            assert result is None

    def test_skips_if_file_not_found(self, tmp_path: Path):
        """Skips upload if file doesn't exist."""
        from cli.notion_chart_publisher import upload_image_to_notion

        nonexistent = tmp_path / "nonexistent.png"
        result = upload_image_to_notion(nonexistent, api_key="test-key")
        assert result is None

    def test_returns_upload_id_on_success(self, sample_chart_png: Path):
        """Returns upload ID on successful upload."""
        from cli.notion_chart_publisher import upload_image_to_notion

        with patch("requests.post") as mock_post:
            # Mock create upload response
            create_response = MagicMock()
            create_response.status_code = 200
            create_response.json.return_value = {"id": "upload-abc123"}
            
            # Mock send file response
            send_response = MagicMock()
            send_response.status_code = 200
            
            mock_post.side_effect = [create_response, send_response]

            result = upload_image_to_notion(sample_chart_png, api_key="test-key")

            assert result == "upload-abc123"
            assert mock_post.call_count == 2

    def test_returns_none_on_api_error(self, sample_chart_png: Path):
        """Returns None on API error."""
        from cli.notion_chart_publisher import upload_image_to_notion

        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_post.return_value = mock_response

            result = upload_image_to_notion(sample_chart_png, api_key="test-key")
            assert result is None

    def test_returns_none_on_exception(self, sample_chart_png: Path):
        """Returns None on exception."""
        from cli.notion_chart_publisher import upload_image_to_notion

        with patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("Unexpected error")

            result = upload_image_to_notion(sample_chart_png, api_key="test-key")
            assert result is None
