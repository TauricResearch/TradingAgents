"""
Input validation and sanitization functions.
"""

import re
from datetime import datetime
from typing import Optional
import os


def validate_ticker(ticker: str, max_length: int = 10) -> str:
    """
    Validate and sanitize stock ticker symbol.

    Args:
        ticker: Ticker symbol to validate
        max_length: Maximum allowed length for ticker

    Returns:
        Sanitized ticker symbol in uppercase

    Raises:
        ValueError: If ticker is invalid

    Examples:
        >>> validate_ticker("AAPL")
        'AAPL'
        >>> validate_ticker("nvda")
        'NVDA'
        >>> validate_ticker("../etc/passwd")
        Traceback (most recent call last):
        ValueError: Invalid ticker symbol...
    """
    if not ticker:
        raise ValueError("Ticker symbol cannot be empty")

    if not isinstance(ticker, str):
        raise ValueError("Ticker symbol must be a string")

    # Remove whitespace
    ticker = ticker.strip().upper()

    # Check length
    if len(ticker) > max_length:
        raise ValueError(f"Ticker symbol too long (max {max_length} characters)")

    # Only allow alphanumeric characters, dots, and hyphens (common in international tickers)
    # Examples: AAPL, BRK.A, RDS-B
    if not re.match(r'^[A-Z0-9.-]+$', ticker):
        raise ValueError(
            "Invalid ticker symbol. Only alphanumeric characters, dots, and hyphens are allowed"
        )

    # Prevent path traversal
    if '..' in ticker or '/' in ticker or '\\' in ticker:
        raise ValueError("Invalid ticker symbol: path traversal detected")

    return ticker


def validate_date(date_str: str, allow_future: bool = False) -> str:
    """
    Validate date string.

    Args:
        date_str: Date string in YYYY-MM-DD format
        allow_future: Whether to allow future dates

    Returns:
        Validated date string

    Raises:
        ValueError: If date is invalid

    Examples:
        >>> validate_date("2024-01-15")
        '2024-01-15'
        >>> validate_date("2024-13-01")
        Traceback (most recent call last):
        ValueError: Invalid date format...
    """
    if not date_str:
        raise ValueError("Date cannot be empty")

    if not isinstance(date_str, str):
        raise ValueError("Date must be a string")

    # Remove whitespace
    date_str = date_str.strip()

    # Validate format and parse
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format. Use YYYY-MM-DD: {e}")

    # Check if date is in the future
    if not allow_future and date_obj.date() > datetime.now().date():
        raise ValueError("Date cannot be in the future")

    # Check if date is too far in the past (before stock markets existed)
    if date_obj.year < 1900:
        raise ValueError("Date cannot be before 1900")

    # Prevent path traversal via date
    if '..' in date_str or '/' in date_str or '\\' in date_str:
        raise ValueError("Invalid date: path traversal detected")

    return date_str


def sanitize_path_component(value: str, max_length: int = 255) -> str:
    """
    Sanitize a value for safe use in file paths.

    Args:
        value: Value to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized value safe for use in file paths

    Examples:
        >>> sanitize_path_component("AAPL")
        'AAPL'
        >>> sanitize_path_component("../../../etc/passwd")
        'etcpasswd'
        >>> sanitize_path_component("2024-01-15")
        '2024-01-15'
    """
    if not value:
        raise ValueError("Path component cannot be empty")

    if not isinstance(value, str):
        value = str(value)

    # Remove path traversal attempts
    value = value.replace('..', '')

    # Remove path separators
    value = value.replace('/', '').replace('\\', '')

    # Remove null bytes
    value = value.replace('\0', '')

    # Allow only safe characters: alphanumeric, dash, underscore, dot
    # This allows dates (2024-01-15) and tickers (AAPL, BRK.A)
    value = re.sub(r'[^a-zA-Z0-9_.-]', '_', value)

    # Remove leading/trailing dots or dashes
    value = value.strip('.-')

    # Check length
    if len(value) > max_length:
        raise ValueError(f"Path component too long (max {max_length} characters)")

    if not value:
        raise ValueError("Path component cannot be empty after sanitization")

    return value


def validate_api_key(api_key: Optional[str], key_name: str = "API_KEY") -> str:
    """
    Validate that an API key is set and not empty.

    Args:
        api_key: API key to validate
        key_name: Name of the API key (for error messages)

    Returns:
        The validated API key

    Raises:
        ValueError: If API key is not set or empty

    Examples:
        >>> validate_api_key("sk-1234567890", "OPENAI_API_KEY")
        'sk-1234567890'
        >>> validate_api_key(None, "OPENAI_API_KEY")
        Traceback (most recent call last):
        ValueError: OPENAI_API_KEY is not set...
    """
    if not api_key:
        raise ValueError(
            f"{key_name} is not set. "
            f"Please set it in your .env file or environment variables."
        )

    if not isinstance(api_key, str):
        raise ValueError(f"{key_name} must be a string")

    # Remove whitespace
    api_key = api_key.strip()

    if not api_key:
        raise ValueError(f"{key_name} cannot be empty")

    # Warn if API key looks suspicious (too short, contains spaces, etc.)
    if len(api_key) < 10:
        import warnings
        warnings.warn(
            f"{key_name} seems unusually short. Please verify it's correct.",
            UserWarning
        )

    if ' ' in api_key:
        raise ValueError(f"{key_name} should not contain spaces")

    return api_key


def validate_url(url: str, allowed_schemes: list = None) -> str:
    """
    Validate URL to prevent SSRF and other URL-based attacks.

    Args:
        url: URL to validate
        allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])

    Returns:
        Validated URL

    Raises:
        ValueError: If URL is invalid or uses disallowed scheme
    """
    from urllib.parse import urlparse

    if allowed_schemes is None:
        allowed_schemes = ['http', 'https']

    if not url:
        raise ValueError("URL cannot be empty")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}")

    # Check scheme
    if parsed.scheme not in allowed_schemes:
        raise ValueError(
            f"Invalid URL scheme: {parsed.scheme}. "
            f"Allowed schemes: {', '.join(allowed_schemes)}"
        )

    # Prevent localhost/private IP access (SSRF protection)
    if parsed.hostname:
        import ipaddress
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if ip.is_private or ip.is_loopback:
                raise ValueError("Access to private/loopback addresses is not allowed")
        except ValueError:
            # Not an IP address, that's fine
            pass

        # Block common private network hostnames
        private_hostnames = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
        if parsed.hostname.lower() in private_hostnames:
            raise ValueError("Access to localhost is not allowed")

    return url
