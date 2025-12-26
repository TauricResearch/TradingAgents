"""Tests for BaseVendor abstract class.

Issue #11: [DATA-10] Interface routing - add new data vendors
"""

import pytest
import time
import threading
from typing import Dict, Any
from unittest.mock import Mock, patch

from tradingagents.dataflows.base_vendor import (
    BaseVendor,
    SimpleVendor,
    VendorResponse,
)

pytestmark = pytest.mark.unit


class ConcreteVendor(BaseVendor):
    """Concrete implementation for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._vendor_name = "test_vendor"

    @property
    def name(self) -> str:
        return self._vendor_name

    def _transform_query(self, method: str, **kwargs) -> Dict[str, Any]:
        return {"method": method, **kwargs}

    def _extract_data(self, method: str, query: Dict[str, Any]) -> Any:
        return {"raw": "data", "query": query}

    def _transform_data(self, method: str, raw_data: Any, query: Dict[str, Any]) -> Any:
        return {"transformed": raw_data}


class TestVendorResponse:
    """Tests for VendorResponse dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        response = VendorResponse()
        assert response.data is None
        assert response.success is True
        assert response.vendor_name == ""
        assert response.method_name == ""
        assert response.execution_time_ms == 0.0
        assert response.error_message == ""
        assert response.metadata == {}

    def test_custom_values(self):
        """Test custom values are preserved."""
        response = VendorResponse(
            data={"test": "data"},
            success=True,
            vendor_name="yfinance",
            method_name="get_stock",
            execution_time_ms=150.5,
            metadata={"source": "api"}
        )
        assert response.data == {"test": "data"}
        assert response.vendor_name == "yfinance"
        assert response.method_name == "get_stock"
        assert response.execution_time_ms == 150.5

    def test_failure_response(self):
        """Test failed response."""
        response = VendorResponse(
            success=False,
            error_message="API Error"
        )
        assert response.success is False
        assert response.error_message == "API Error"

    def test_is_empty_with_none(self):
        """Test is_empty returns True for None data."""
        response = VendorResponse(data=None)
        assert response.is_empty is True

    def test_is_empty_with_empty_list(self):
        """Test is_empty returns True for empty list."""
        response = VendorResponse(data=[])
        assert response.is_empty is True

    def test_is_empty_with_empty_dict(self):
        """Test is_empty returns True for empty dict."""
        response = VendorResponse(data={})
        assert response.is_empty is True

    def test_is_empty_with_empty_string(self):
        """Test is_empty returns True for empty string."""
        response = VendorResponse(data="")
        assert response.is_empty is True

    def test_is_empty_with_data(self):
        """Test is_empty returns False when data exists."""
        response = VendorResponse(data={"test": "data"})
        assert response.is_empty is False


class TestBaseVendorAbstract:
    """Tests for BaseVendor abstract method enforcement."""

    def test_cannot_instantiate_base_vendor(self):
        """Test that BaseVendor cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseVendor()

    def test_can_instantiate_concrete_vendor(self):
        """Test that concrete implementation can be instantiated."""
        vendor = ConcreteVendor()
        assert vendor is not None
        assert vendor.name == "test_vendor"


class TestBaseVendorConfiguration:
    """Tests for BaseVendor configuration."""

    def test_default_configuration(self):
        """Test default configuration values."""
        vendor = ConcreteVendor()
        assert vendor._max_retries == 3
        assert vendor._retry_delay == 1.0
        assert vendor._retry_backoff == 2.0
        assert vendor._timeout is None

    def test_custom_configuration(self):
        """Test custom configuration values."""
        vendor = ConcreteVendor(
            max_retries=5,
            retry_delay=0.5,
            retry_backoff=3.0,
            timeout=30.0
        )
        assert vendor._max_retries == 5
        assert vendor._retry_delay == 0.5
        assert vendor._retry_backoff == 3.0
        assert vendor._timeout == 30.0


class TestBaseVendorExecution:
    """Tests for BaseVendor execute method."""

    def test_successful_execution(self):
        """Test successful execution returns VendorResponse."""
        vendor = ConcreteVendor()
        response = vendor.execute("get_data", ticker="AAPL")

        assert isinstance(response, VendorResponse)
        assert response.success is True
        assert response.vendor_name == "test_vendor"
        assert response.method_name == "get_data"
        assert response.execution_time_ms > 0

    def test_execution_increments_call_count(self):
        """Test that execute increments call count."""
        vendor = ConcreteVendor()
        assert vendor.call_count == 0

        vendor.execute("method1")
        assert vendor.call_count == 1

        vendor.execute("method2")
        assert vendor.call_count == 2

    def test_call_count_thread_safe(self):
        """Test that call_count is thread-safe."""
        vendor = ConcreteVendor()
        errors = []

        def execute_many():
            try:
                for _ in range(100):
                    vendor.execute("test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=execute_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert vendor.call_count == 500


class TestBaseVendorRetry:
    """Tests for BaseVendor retry logic."""

    def test_retry_on_connection_error(self):
        """Test retry on connection error."""
        attempt_count = [0]

        class RetryVendor(ConcreteVendor):
            def _extract_data(self, method, query):
                attempt_count[0] += 1
                if attempt_count[0] < 3:
                    raise ConnectionError("Network error")
                return {"data": "success"}

        vendor = RetryVendor(retry_delay=0.01)
        response = vendor.execute("test")

        assert attempt_count[0] == 3
        assert response.success is True

    def test_no_retry_on_value_error(self):
        """Test no retry on non-retryable error."""
        class NoRetryVendor(ConcreteVendor):
            def _extract_data(self, method, query):
                raise ValueError("Invalid input")

        vendor = NoRetryVendor(retry_delay=0.01)
        response = vendor.execute("test")

        assert response.success is False
        assert "Invalid input" in response.error_message

    def test_max_retries_exhausted(self):
        """Test that max retries is respected."""
        attempt_count = [0]

        class AlwaysFailVendor(ConcreteVendor):
            def _extract_data(self, method, query):
                attempt_count[0] += 1
                raise ConnectionError("Network error")

        vendor = AlwaysFailVendor(max_retries=3, retry_delay=0.01)
        response = vendor.execute("test")

        assert attempt_count[0] == 4  # 1 initial + 3 retries
        assert response.success is False


class TestBaseVendorStatistics:
    """Tests for BaseVendor statistics."""

    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        class MixedVendor(ConcreteVendor):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self._fail_count = 0

            def _extract_data(self, method, query):
                self._fail_count += 1
                if self._fail_count <= 2:
                    raise ValueError("Error")
                return {"data": "success"}

        vendor = MixedVendor(max_retries=0, retry_delay=0.01)

        # 2 failures
        vendor.execute("test")
        vendor.execute("test")
        # 1 success
        vendor.execute("test")

        # 2 errors out of 3 = 66.67%
        assert 66 < vendor.error_rate < 67

    def test_reset_stats(self):
        """Test reset_stats clears counters."""
        vendor = ConcreteVendor()
        vendor.execute("test")
        vendor.execute("test")

        assert vendor.call_count == 2

        vendor.reset_stats()

        assert vendor.call_count == 0
        assert vendor.error_rate == 0.0


class TestSimpleVendor:
    """Tests for SimpleVendor wrapper class."""

    def test_simple_vendor_creation(self):
        """Test creating a SimpleVendor."""
        mock_func = Mock(return_value={"data": "test"})
        vendor = SimpleVendor(
            vendor_name="test",
            methods={"get_data": mock_func}
        )

        assert vendor.name == "test"

    def test_simple_vendor_execution(self):
        """Test executing a SimpleVendor method."""
        mock_func = Mock(return_value={"data": "test"})
        vendor = SimpleVendor(
            vendor_name="test",
            methods={"get_data": mock_func}
        )

        response = vendor.execute("get_data", ticker="AAPL")

        assert response.success is True
        assert response.data == {"data": "test"}
        mock_func.assert_called_once_with(ticker="AAPL")

    def test_simple_vendor_missing_method(self):
        """Test SimpleVendor with missing method."""
        vendor = SimpleVendor(
            vendor_name="test",
            methods={}
        )

        response = vendor.execute("nonexistent")

        assert response.success is False
        assert "not found" in response.error_message

    def test_simple_vendor_add_method(self):
        """Test adding a method to SimpleVendor."""
        vendor = SimpleVendor(
            vendor_name="test",
            methods={}
        )

        mock_func = Mock(return_value="result")
        vendor.add_method("new_method", mock_func)

        response = vendor.execute("new_method")

        assert response.success is True
        assert response.data == "result"

    def test_simple_vendor_get_methods(self):
        """Test getting list of methods."""
        vendor = SimpleVendor(
            vendor_name="test",
            methods={
                "method1": Mock(),
                "method2": Mock(),
                "method3": Mock()
            }
        )

        methods = vendor.get_methods()

        assert len(methods) == 3
        assert "method1" in methods
        assert "method2" in methods
        assert "method3" in methods


class TestVendorLifecycle:
    """Tests for 3-stage vendor lifecycle."""

    def test_lifecycle_order(self):
        """Test that lifecycle stages execute in order."""
        call_order = []

        class OrderVendor(BaseVendor):
            @property
            def name(self):
                return "order_test"

            def _transform_query(self, method, **kwargs):
                call_order.append("transform_query")
                return kwargs

            def _extract_data(self, method, query):
                call_order.append("extract_data")
                return {"raw": True}

            def _transform_data(self, method, raw_data, query):
                call_order.append("transform_data")
                return raw_data

        vendor = OrderVendor()
        vendor.execute("test")

        assert call_order == ["transform_query", "extract_data", "transform_data"]

    def test_query_passed_to_extract(self):
        """Test that transformed query is passed to extract."""
        class QueryVendor(BaseVendor):
            @property
            def name(self):
                return "query_test"

            def _transform_query(self, method, **kwargs):
                return {"ticker": kwargs.get("ticker", "").upper()}

            def _extract_data(self, method, query):
                return {"symbol": query["ticker"]}

            def _transform_data(self, method, raw_data, query):
                return raw_data

        vendor = QueryVendor()
        response = vendor.execute("test", ticker="aapl")

        assert response.data["symbol"] == "AAPL"

    def test_raw_data_passed_to_transform(self):
        """Test that raw data is passed to transform."""
        class TransformVendor(BaseVendor):
            @property
            def name(self):
                return "transform_test"

            def _transform_query(self, method, **kwargs):
                return kwargs

            def _extract_data(self, method, query):
                return {"raw_value": 42}

            def _transform_data(self, method, raw_data, query):
                return {"processed": raw_data["raw_value"] * 2}

        vendor = TransformVendor()
        response = vendor.execute("test")

        assert response.data["processed"] == 84
