"""
Base Vendor Abstract Base Class (Issue #11).

This module provides:
1. VendorResponse - Dataclass for standardized vendor responses
2. BaseVendor - ABC defining 3-stage vendor lifecycle

The 3-stage lifecycle pattern:
1. transform_query: Convert parameters to vendor-specific format
2. extract_data: Execute vendor API call and get raw data
3. transform_data: Convert raw data to standardized format

Retry logic with exponential backoff is built into the execute() method.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime


@dataclass
class VendorResponse:
    """
    Standardized response from vendor data extraction.

    Attributes:
        data: The extracted data (any type)
        metadata: Additional metadata about the response
        success: Whether the extraction was successful
        error: Error message if success=False
        timestamp: When the response was created
    """

    data: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class BaseVendor(ABC):
    """
    Abstract base class for all data vendors.

    Implements the template method pattern with a 3-stage lifecycle:
    1. transform_query: Convert input parameters to vendor format
    2. extract_data: Execute vendor API call
    3. transform_data: Convert raw data to standard format

    Concrete vendors must implement all three abstract methods.

    Attributes:
        name: Vendor name for identification
        max_retries: Maximum retry attempts on failure
        retry_delay: Initial delay between retries (seconds)
        backoff_factor: Exponential backoff multiplier

    Usage:
        class MyVendor(BaseVendor):
            def transform_query(self, method, *args, **kwargs):
                return {"ticker": kwargs.get("ticker")}

            def extract_data(self, query):
                return self._api_call(query)

            def transform_data(self, raw_data, method):
                return VendorResponse(data=raw_data, success=True)

        vendor = MyVendor()
        response = vendor.execute("get_stock_data", ticker="AAPL")
    """

    def __init__(
        self,
        name: str = "base_vendor",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0
    ):
        """
        Initialize base vendor with retry configuration.

        Args:
            name: Vendor identifier
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
            backoff_factor: Exponential backoff multiplier
        """
        self.name = name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self._call_count = 0

    @abstractmethod
    def transform_query(self, method: str, *args, **kwargs) -> Dict[str, Any]:
        """
        Stage 1: Transform input parameters into vendor-specific query format.

        Convert generic method parameters into the format required by
        this vendor's API.

        Args:
            method: The method name being called (e.g., "get_stock_data")
            *args: Positional arguments passed to the method
            **kwargs: Keyword arguments passed to the method

        Returns:
            Dict containing transformed query parameters

        Example:
            def transform_query(self, method, *args, **kwargs):
                return {
                    "symbol": kwargs.get("ticker", "").upper(),
                    "period": kwargs.get("period", "1d")
                }
        """
        pass

    @abstractmethod
    def extract_data(self, query: Dict[str, Any]) -> Any:
        """
        Stage 2: Execute vendor-specific API call and extract raw data.

        Make the actual API call using the transformed query and return
        raw data from the vendor.

        Args:
            query: Transformed query from stage 1

        Returns:
            Raw data from vendor API (any type)

        Raises:
            Exception: On API errors, rate limits, network issues, etc.

        Example:
            def extract_data(self, query):
                response = requests.get(self.api_url, params=query)
                response.raise_for_status()
                return response.json()
        """
        pass

    @abstractmethod
    def transform_data(self, raw_data: Any, method: str) -> VendorResponse:
        """
        Stage 3: Transform raw vendor data into standardized format.

        Convert vendor-specific data format into a standardized VendorResponse
        that can be used consistently across different vendors.

        Args:
            raw_data: Raw data from stage 2
            method: The method name being called

        Returns:
            VendorResponse with standardized data

        Example:
            def transform_data(self, raw_data, method):
                standardized = {
                    "symbol": raw_data["ticker"],
                    "price": float(raw_data["close"])
                }
                return VendorResponse(
                    data=standardized,
                    metadata={"source": self.name},
                    success=True
                )
        """
        pass

    def execute(self, method: str, *args, **kwargs) -> VendorResponse:
        """
        Execute the 3-stage vendor lifecycle with retry logic.

        Orchestrates the three stages with exponential backoff retry:
        1. transform_query
        2. extract_data
        3. transform_data

        Args:
            method: The method name to execute
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            VendorResponse from successful execution

        Raises:
            Exception: After all retries exhausted

        Retry Behavior:
            - Retries on any exception from stages 1-3
            - Uses exponential backoff: delay * (backoff_factor ^ attempt)
            - Sleeps between retries, not after final attempt
        """
        for attempt in range(self.max_retries):
            try:
                # Stage 1: Transform query
                query = self.transform_query(method, *args, **kwargs)

                # Stage 2: Extract data
                raw_data = self.extract_data(query)

                # Stage 3: Transform data
                response = self.transform_data(raw_data, method)

                self._call_count += 1
                return response

            except Exception as e:
                if attempt < self.max_retries - 1:
                    # Calculate exponential backoff delay
                    delay = self.retry_delay * (self.backoff_factor ** attempt)
                    time.sleep(delay)
                else:
                    # Final attempt failed, re-raise exception
                    raise
