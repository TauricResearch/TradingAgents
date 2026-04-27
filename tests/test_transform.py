"""Tests for tradingagents.graph.transform module.

Tests cover:
- ChartJSON pydantic model validation
- transform_to_json() with mocked LLM
- Retry logic on transient failures
- Error handling for malformed LLM output
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from tradingagents.graph.transform import (
    ChartInfo,
    ChartJSON,
    PriceHistory,
    ReferenceLine,
    transform_to_json,
    _parse_llm_response,
    _TRANSFORM_MODEL,
    _TRANSFORM_PROVIDER,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_chart_json_dict() -> dict:
    """Sample chart JSON matching transform_flow.json schema."""
    return {
        "chart_info": {
            "title": "BTC/USDT Trading Plan (2026-04-26)",
            "current_price": 78068.70,
            "y_axis_range": [72000, 91000],
            "x_label": "Date",
            "y_label": "Price (USDT)",
        },
        "price_history": {
            "dates": ["17/04", "18/04", "19/04", "20/04", "21/04"],
            "prices": [77736, 75500, 73758, 76000, 77500],
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
                "price": 78068,
                "label": "ENTRY (40%)",
                "color": "orange",
                "linestyle": "solid",
                "linewidth": 2.0,
                "align": "left",
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
def sample_final_state() -> dict:
    """Sample final_state from graph execution."""
    return {
        "market_report": "Market analysis shows BTC trading at $78,000...",
        "sentiment_report": "Social sentiment is bullish...",
        "news_report": "Recent news indicates...",
        "fundamentals_report": "Fundamentals analysis...",
        "investment_debate_state": {
            "bull_history": "Bull case: Strong support at $75,000...",
            "bear_history": "Bear case: Resistance at $80,000...",
            "judge_decision": "Decision: Long position recommended...",
        },
        "final_trade_decision": "Entry: $78,000, TP: $85,000, SL: $75,000",
    }


# ---------------------------------------------------------------------------
# Pydantic Model Tests
# ---------------------------------------------------------------------------


class TestChartInfo:
    """Tests for ChartInfo model."""

    def test_valid_chart_info(self, sample_chart_json_dict):
        """ChartInfo accepts valid data."""
        info = ChartInfo(**sample_chart_json_dict["chart_info"])
        assert info.title == sample_chart_json_dict["chart_info"]["title"]
        assert info.current_price == 78068.70
        assert info.y_axis_range == [72000, 91000]

    def test_y_axis_range_must_have_two_elements(self):
        """y_axis_range must have exactly 2 elements."""
        with pytest.raises(ValidationError):
            ChartInfo(
                title="Test",
                current_price=100.0,
                y_axis_range=[100],  # Only 1 element
            )

        with pytest.raises(ValidationError):
            ChartInfo(
                title="Test",
                current_price=100.0,
                y_axis_range=[100, 200, 300],  # 3 elements
            )

    def test_default_labels(self):
        """Default x_label and y_label are set."""
        info = ChartInfo(title="Test", current_price=100.0, y_axis_range=[90, 110])
        assert info.x_label == "Date"
        assert info.y_label == "Price (USDT)"


class TestPriceHistory:
    """Tests for PriceHistory model."""

    def test_valid_price_history(self, sample_chart_json_dict):
        """PriceHistory accepts valid data."""
        history = PriceHistory(**sample_chart_json_dict["price_history"])
        assert len(history.dates) == 5
        assert len(history.prices) == 5

    def test_dates_and_prices_must_not_be_empty(self):
        """dates and prices must have at least 1 element."""
        with pytest.raises(ValidationError):
            PriceHistory(dates=[], prices=[100])

        with pytest.raises(ValidationError):
            PriceHistory(dates=["01/01"], prices=[])


class TestReferenceLine:
    """Tests for ReferenceLine model."""

    def test_valid_reference_line(self, sample_chart_json_dict):
        """ReferenceLine accepts valid data."""
        ref = ReferenceLine(**sample_chart_json_dict["reference_lines"][0])
        assert ref.price == 89262
        assert ref.label == "TP Max"
        assert ref.color == "green"

    def test_defaults(self):
        """Default values are applied."""
        ref = ReferenceLine(price=100, label="Test")
        assert ref.color == "gray"
        assert ref.linestyle == "solid"
        assert ref.linewidth == 1.0
        assert ref.align == "right"


class TestChartJSON:
    """Tests for ChartJSON model."""

    def test_valid_chart_json(self, sample_chart_json_dict):
        """ChartJSON accepts valid data."""
        chart = ChartJSON(**sample_chart_json_dict)
        assert chart.chart_info.title == sample_chart_json_dict["chart_info"]["title"]
        assert len(chart.reference_lines) == 3

    def test_reference_lines_must_not_be_empty(self):
        """reference_lines must have at least 1 element."""
        with pytest.raises(ValidationError):
            ChartJSON(
                chart_info={
                    "title": "Test",
                    "current_price": 100.0,
                    "y_axis_range": [90, 110],
                },
                price_history={"dates": ["01/01"], "prices": [100]},
                reference_lines=[],
            )


# ---------------------------------------------------------------------------
# LLM Response Parsing Tests
# ---------------------------------------------------------------------------


class TestParseLLMResponse:
    """Tests for _parse_llm_response function."""

    def test_parse_valid_json(self, sample_chart_json_dict):
        """Parse valid JSON string into ChartJSON."""
        json_str = json.dumps(sample_chart_json_dict)
        result = _parse_llm_response(json_str)
        assert isinstance(result, ChartJSON)
        assert result.chart_info.title == sample_chart_json_dict["chart_info"]["title"]

    def test_parse_json_with_markdown_fences(self, sample_chart_json_dict):
        """Parse JSON wrapped in markdown code fences."""
        json_str = f"```json\n{json.dumps(sample_chart_json_dict)}\n```"
        result = _parse_llm_response(json_str)
        assert isinstance(result, ChartJSON)

    def test_parse_json_with_simple_fence(self, sample_chart_json_dict):
        """Parse JSON wrapped in simple code fence."""
        json_str = f"```\n{json.dumps(sample_chart_json_dict)}\n```"
        result = _parse_llm_response(json_str)
        assert isinstance(result, ChartJSON)

    def test_parse_invalid_json_raises_value_error(self):
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_llm_response("not valid json")

    def test_parse_json_missing_required_field_raises_validation_error(self):
        """JSON missing required field raises ValidationError."""
        invalid_json = json.dumps({
            "chart_info": {"title": "Test"},
            "price_history": {"dates": ["01/01"], "prices": [100]},
            "reference_lines": [{"price": 100, "label": "Test"}],
        })
        with pytest.raises(ValidationError):
            _parse_llm_response(invalid_json)


# ---------------------------------------------------------------------------
# transform_to_json Tests
# ---------------------------------------------------------------------------


class TestTransformToJson:
    """Tests for transform_to_json function."""

    def test_model_is_hard_coded(self):
        """Verify model is hard-coded to gpt-5.3-codex-high."""
        assert _TRANSFORM_PROVIDER == "openai"
        assert _TRANSFORM_MODEL == "gpt-5.3-codex-high"

    def test_missing_api_key_raises_environment_error(self, sample_final_state):
        """Missing OPENAI_API_KEY raises EnvironmentError."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            with pytest.raises(EnvironmentError, match="OPENAI_API_KEY"):
                transform_to_json(
                    sample_final_state,
                    "BTCUSDT",
                    "2026-04-26",
                    api_key=None,
                )

    def test_successful_transform(
        self, sample_final_state, sample_chart_json_dict, mock_llm_client
    ):
        """Successful transform returns ChartJSON."""
        # Mock LLM response
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps(sample_chart_json_dict)
        )
        mock_llm_client.get_llm.return_value = mock_llm

        with patch(
            "tradingagents.llm_clients.create_llm_client",
            return_value=mock_llm_client,
        ):
            result = transform_to_json(
                sample_final_state,
                "BTCUSDT",
                "2026-04-26",
                api_key="test-key",
            )

        assert isinstance(result, ChartJSON)
        assert result.chart_info.title == sample_chart_json_dict["chart_info"]["title"]

    def test_retry_on_transient_error(
        self, sample_final_state, sample_chart_json_dict, mock_llm_client
    ):
        """Retry on transient errors (429, 500, 503)."""
        mock_llm = MagicMock()
        # First call: rate limit error
        mock_llm.invoke.side_effect = [
            Exception("429 Rate limit exceeded"),
            MagicMock(content=json.dumps(sample_chart_json_dict)),
        ]
        mock_llm_client.get_llm.return_value = mock_llm

        with patch(
            "tradingagents.llm_clients.create_llm_client",
            return_value=mock_llm_client,
        ):
            with patch("time.sleep"):  # Skip actual sleep
                result = transform_to_json(
                    sample_final_state,
                    "BTCUSDT",
                    "2026-04-26",
                    api_key="test-key",
                )

        assert isinstance(result, ChartJSON)
        assert mock_llm.invoke.call_count == 2

    def test_retry_on_invalid_json(
        self, sample_final_state, sample_chart_json_dict, mock_llm_client
    ):
        """Retry on invalid JSON from LLM."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            MagicMock(content="invalid json"),
            MagicMock(content=json.dumps(sample_chart_json_dict)),
        ]
        mock_llm_client.get_llm.return_value = mock_llm

        with patch(
            "tradingagents.llm_clients.create_llm_client",
            return_value=mock_llm_client,
        ):
            with patch("time.sleep"):  # Skip actual sleep
                result = transform_to_json(
                    sample_final_state,
                    "BTCUSDT",
                    "2026-04-26",
                    api_key="test-key",
                )

        assert isinstance(result, ChartJSON)
        assert mock_llm.invoke.call_count == 2

    def test_raises_runtime_error_after_max_retries(
        self, sample_final_state, mock_llm_client
    ):
        """Raise RuntimeError after max retries."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("Persistent error")
        mock_llm_client.get_llm.return_value = mock_llm

        with patch(
            "tradingagents.llm_clients.create_llm_client",
            return_value=mock_llm_client,
        ):
            with patch("time.sleep"):  # Skip actual sleep
                with pytest.raises(RuntimeError, match="failed after"):
                    transform_to_json(
                        sample_final_state,
                        "BTCUSDT",
                        "2026-04-26",
                        api_key="test-key",
                    )

    def test_uses_custom_base_url(
        self, sample_final_state, sample_chart_json_dict, mock_llm_client
    ):
        """Custom base_url is passed to LLM client."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps(sample_chart_json_dict)
        )
        mock_llm_client.get_llm.return_value = mock_llm

        with patch(
            "tradingagents.llm_clients.create_llm_client",
            return_value=mock_llm_client,
        ) as mock_create:
            transform_to_json(
                sample_final_state,
                "BTCUSDT",
                "2026-04-26",
                base_url="https://custom.api.com",
                api_key="test-key",
            )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["base_url"] == "https://custom.api.com"
