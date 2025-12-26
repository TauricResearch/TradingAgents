"""Base vendor abstract class for data provider implementations.

This module provides the abstract base class that all data vendors must inherit from,
implementing a 3-stage data pipeline: transform_query → extract_data → transform_data.

Issue #11: [DATA-10] Interface routing - add new data vendors
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TypeVar, Generic
import threading
import time
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class VendorResponse(Generic[T]):
    """Standardized response from vendor data operations.

    Attributes:
        data: The extracted data
        success: Whether the operation succeeded
        vendor_name: Name of the vendor that provided the data
        method_name: Name of the method called
        execution_time_ms: Time taken in milliseconds
        error_message: Error message if operation failed
        metadata: Additional metadata about the response
    """
    data: Optional[T] = None
    success: bool = True
    vendor_name: str = ""
    method_name: str = ""
    execution_time_ms: float = 0.0
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Check if response contains no data."""
        if self.data is None:
            return True
        if isinstance(self.data, (list, dict, str)):
            return len(self.data) == 0
        return False


class BaseVendor(ABC):
    """Abstract base class for all data vendors.

    Implements a 3-stage pipeline pattern:
    1. transform_query: Normalize input parameters
    2. extract_data: Fetch raw data from source
    3. transform_data: Normalize output format

    Thread-safe call counting with configurable retry logic.

    Example:
        class YFinanceVendor(BaseVendor):
            @property
            def name(self) -> str:
                return "yfinance"

            def _transform_query(self, method, **kwargs):
                # Normalize ticker symbol
                return {"symbol": kwargs["ticker"].upper()}

            def _extract_data(self, method, query):
                # Fetch from yfinance
                return yf.Ticker(query["symbol"]).history()

            def _transform_data(self, method, raw_data, query):
                # Convert to standard format
                return {"ohlcv": raw_data.to_dict()}
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        timeout: Optional[float] = None
    ):
        """Initialize vendor with retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
            retry_backoff: Multiplier for delay after each retry
            timeout: Optional timeout for operations in seconds
        """
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff
        self._timeout = timeout
        self._call_count = 0
        self._call_count_lock = threading.Lock()
        self._last_call_time: Optional[datetime] = None
        self._error_count = 0
        self._success_count = 0

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the vendor name."""
        pass

    @property
    def call_count(self) -> int:
        """Get the total number of calls made (thread-safe)."""
        with self._call_count_lock:
            return self._call_count

    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage."""
        total = self._error_count + self._success_count
        if total == 0:
            return 0.0
        return (self._error_count / total) * 100

    def reset_stats(self) -> None:
        """Reset call statistics."""
        with self._call_count_lock:
            self._call_count = 0
            self._error_count = 0
            self._success_count = 0
            self._last_call_time = None

    @abstractmethod
    def _transform_query(self, method: str, **kwargs) -> Dict[str, Any]:
        """Transform input parameters to vendor-specific format.

        Args:
            method: The method being called
            **kwargs: Input parameters

        Returns:
            Transformed query parameters
        """
        pass

    @abstractmethod
    def _extract_data(self, method: str, query: Dict[str, Any]) -> Any:
        """Extract raw data from the vendor.

        Args:
            method: The method being called
            query: Transformed query parameters

        Returns:
            Raw data from the vendor
        """
        pass

    @abstractmethod
    def _transform_data(
        self,
        method: str,
        raw_data: Any,
        query: Dict[str, Any]
    ) -> Any:
        """Transform raw data to standardized format.

        Args:
            method: The method being called
            raw_data: Raw data from extract_data
            query: Original query parameters

        Returns:
            Transformed data in standard format
        """
        pass

    def _should_retry(self, exception: Exception) -> bool:
        """Determine if operation should be retried for given exception.

        Override this method to customize retry logic.

        Args:
            exception: The exception that occurred

        Returns:
            True if operation should be retried
        """
        # Default: retry on network-related errors
        retryable_types = (
            ConnectionError,
            TimeoutError,
            OSError,
        )
        return isinstance(exception, retryable_types)

    def execute(
        self,
        method: str,
        **kwargs
    ) -> VendorResponse:
        """Execute a vendor method with full pipeline.

        Runs the 3-stage pipeline with retry logic:
        1. transform_query
        2. extract_data (with retries)
        3. transform_data

        Args:
            method: Name of the method to execute
            **kwargs: Parameters for the method

        Returns:
            VendorResponse with result or error information
        """
        start_time = time.time()

        # Increment call count (thread-safe)
        with self._call_count_lock:
            self._call_count += 1
            self._last_call_time = datetime.now()

        response = VendorResponse(
            vendor_name=self.name,
            method_name=method
        )

        try:
            # Stage 1: Transform query
            query = self._transform_query(method, **kwargs)
            logger.debug(f"[{self.name}] Transformed query for {method}: {query}")

            # Stage 2: Extract data with retries
            raw_data = self._extract_with_retry(method, query)

            # Stage 3: Transform data
            transformed = self._transform_data(method, raw_data, query)

            response.data = transformed
            response.success = True
            self._success_count += 1

        except Exception as e:
            response.success = False
            response.error_message = str(e)
            self._error_count += 1
            logger.error(f"[{self.name}] Error executing {method}: {e}")

        finally:
            response.execution_time_ms = (time.time() - start_time) * 1000

        return response

    def _extract_with_retry(self, method: str, query: Dict[str, Any]) -> Any:
        """Execute extract_data with retry logic.

        Args:
            method: Method name
            query: Query parameters

        Returns:
            Raw data from vendor

        Raises:
            Last exception if all retries fail
        """
        last_exception: Optional[Exception] = None
        delay = self._retry_delay

        for attempt in range(self._max_retries + 1):
            try:
                return self._extract_data(method, query)

            except Exception as e:
                last_exception = e

                if not self._should_retry(e):
                    logger.debug(f"[{self.name}] Non-retryable error: {e}")
                    raise

                if attempt < self._max_retries:
                    logger.warning(
                        f"[{self.name}] Retry {attempt + 1}/{self._max_retries} "
                        f"after error: {e}. Waiting {delay:.1f}s"
                    )
                    time.sleep(delay)
                    delay *= self._retry_backoff

        # All retries exhausted
        raise last_exception  # type: ignore


class SimpleVendor(BaseVendor):
    """Simplified vendor for wrapping existing functions.

    Useful for migrating existing vendor implementations to the new pattern
    without major refactoring.

    Example:
        vendor = SimpleVendor(
            vendor_name="yfinance",
            methods={
                "get_stock_data": get_yfinance_stock,
                "get_fundamentals": get_yfinance_fundamentals,
            }
        )
    """

    def __init__(
        self,
        vendor_name: str,
        methods: Dict[str, callable],
        **kwargs
    ):
        """Initialize simple vendor with existing functions.

        Args:
            vendor_name: Name of the vendor
            methods: Dictionary mapping method names to callables
            **kwargs: Additional BaseVendor configuration
        """
        super().__init__(**kwargs)
        self._vendor_name = vendor_name
        self._methods = methods

    @property
    def name(self) -> str:
        """Return the vendor name."""
        return self._vendor_name

    def _transform_query(self, method: str, **kwargs) -> Dict[str, Any]:
        """Pass through query parameters unchanged."""
        return kwargs

    def _extract_data(self, method: str, query: Dict[str, Any]) -> Any:
        """Call the wrapped function."""
        if method not in self._methods:
            raise ValueError(f"Method '{method}' not found in vendor '{self.name}'")

        func = self._methods[method]
        return func(**query)

    def _transform_data(
        self,
        method: str,
        raw_data: Any,
        query: Dict[str, Any]
    ) -> Any:
        """Return data unchanged."""
        return raw_data

    def add_method(self, method_name: str, func: callable) -> None:
        """Add a method to the vendor.

        Args:
            method_name: Name of the method
            func: Callable to execute
        """
        self._methods[method_name] = func

    def get_methods(self) -> List[str]:
        """Get list of available methods."""
        return list(self._methods.keys())
