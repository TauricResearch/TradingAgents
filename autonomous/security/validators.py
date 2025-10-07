"""
Security Validation Layer
=========================

Comprehensive input validation, sanitization, and security checks
to prevent injection attacks and ensure data integrity.
"""

import re
import logging
import hashlib
import hmac
import secrets
from typing import Any, Dict, List, Optional, Union, Type
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
import json

from pydantic import (
    BaseModel, Field, validator, root_validator,
    ValidationError, constr, condecimal, conint
)
from typing_extensions import Annotated

logger = logging.getLogger(__name__)


# === Custom Types with Validation ===

# Ticker symbol: 1-10 uppercase letters/numbers, no special chars
TickerSymbol = Annotated[
    str,
    constr(
        regex=r'^[A-Z0-9]{1,10}$',
        strip_whitespace=True,
        to_upper=True
    )
]

# Price: positive decimal with max 2 decimal places
Price = Annotated[
    Decimal,
    condecimal(
        gt=0,
        max_digits=10,
        decimal_places=2
    )
]

# Quantity: positive integer within reasonable bounds
Quantity = Annotated[
    int,
    conint(
        gt=0,
        le=1000000  # Max 1 million shares
    )
]

# Percentage: 0-100
Percentage = Annotated[
    float,
    Field(ge=0.0, le=100.0)
]


class SecurityLevel(str, Enum):
    """Security validation levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# === Input Validators ===

class TickerValidator(BaseModel):
    """Validator for ticker symbols"""
    ticker: TickerSymbol

    @validator('ticker')
    def validate_ticker(cls, v):
        """Additional ticker validation"""
        # Check against blacklist of invalid tickers
        blacklist = ['TEST', 'DUMMY', 'NULL', 'UNDEFINED']
        if v in blacklist:
            raise ValueError(f"Invalid ticker: {v}")

        # Check for SQL injection patterns
        if cls._contains_sql_injection(v):
            raise ValueError("Potential SQL injection detected")

        return v

    @staticmethod
    def _contains_sql_injection(value: str) -> bool:
        """Check for SQL injection patterns"""
        sql_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|CREATE|ALTER)\b)",
            r"(-{2}|\/\*|\*\/)",  # SQL comments
            r"(;|\||&&)",  # Command separators
            r"(\bOR\b.*=.*)",  # OR conditions
            r"('|\")",  # Quotes
        ]

        for pattern in sql_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return True
        return False


class OrderValidator(BaseModel):
    """Comprehensive order validation"""
    ticker: TickerSymbol
    side: str = Field(regex=r'^(BUY|SELL)$')
    quantity: Quantity
    order_type: str = Field(regex=r'^(MARKET|LIMIT|STOP|STOP_LIMIT)$')
    limit_price: Optional[Price] = None
    stop_price: Optional[Price] = None
    time_in_force: str = Field(
        default="DAY",
        regex=r'^(DAY|GTC|IOC|FOK)$'
    )
    account_id: Optional[constr(max_length=50)] = None
    notes: Optional[constr(max_length=500)] = None

    @root_validator
    def validate_prices(cls, values):
        """Validate price requirements based on order type"""
        order_type = values.get('order_type')
        limit_price = values.get('limit_price')
        stop_price = values.get('stop_price')

        if order_type == 'LIMIT' and not limit_price:
            raise ValueError("Limit price required for LIMIT orders")

        if order_type in ['STOP', 'STOP_LIMIT'] and not stop_price:
            raise ValueError("Stop price required for STOP orders")

        if order_type == 'STOP_LIMIT' and not limit_price:
            raise ValueError("Limit price required for STOP_LIMIT orders")

        # Check for unreasonable prices
        if limit_price and limit_price > 100000:
            raise ValueError(f"Limit price ${limit_price} exceeds maximum")

        if stop_price and limit_price:
            side = values.get('side')
            if side == 'BUY' and stop_price < limit_price:
                raise ValueError("Stop price must be above limit for buy stop orders")
            elif side == 'SELL' and stop_price > limit_price:
                raise ValueError("Stop price must be below limit for sell stop orders")

        return values

    @validator('notes')
    def sanitize_notes(cls, v):
        """Sanitize notes field"""
        if v:
            # Remove potential XSS/injection content
            v = cls._sanitize_string(v)
        return v

    @staticmethod
    def _sanitize_string(value: str) -> str:
        """Remove dangerous characters from string"""
        # Remove HTML/Script tags
        value = re.sub(r'<[^>]*>', '', value)

        # Remove JavaScript
        value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)

        # Remove SQL keywords
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'EXEC', 'UNION']
        for keyword in sql_keywords:
            value = re.sub(rf'\b{keyword}\b', '', value, flags=re.IGNORECASE)

        return value.strip()


class ConfigValidator(BaseModel):
    """Validator for configuration settings"""
    max_position_size: Percentage
    max_daily_loss: Percentage
    max_orders_per_day: conint(gt=0, le=1000)
    confidence_threshold: Percentage
    stop_loss_percent: Percentage
    api_keys: Dict[str, str] = Field(default_factory=dict)

    @validator('api_keys')
    def validate_api_keys(cls, v):
        """Validate API key format"""
        for key_name, key_value in v.items():
            # Check for exposed secrets
            if cls._is_placeholder(key_value):
                raise ValueError(f"Invalid API key for {key_name}")

            # Check key format (basic validation)
            if len(key_value) < 10:
                raise ValueError(f"API key {key_name} is too short")

            # Check for common test keys
            if key_value in ['test', 'demo', '12345', 'password']:
                raise ValueError(f"Invalid API key for {key_name}")

        return v

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        """Check if value is a placeholder"""
        placeholders = [
            'your_key_here',
            'placeholder',
            'xxxx',
            'todo',
            'changeme'
        ]
        return any(p in value.lower() for p in placeholders)


class WebhookValidator(BaseModel):
    """Validator for webhook URLs"""
    url: constr(
        regex=r'^https:\/\/(discord\.com|hooks\.slack\.com|api\.telegram\.org)\/.*',
        max_length=500
    )
    enabled: bool = True

    @validator('url')
    def validate_webhook_url(cls, v):
        """Validate webhook URL security"""
        # Check for localhost/internal IPs (SSRF prevention)
        internal_patterns = [
            r'localhost',
            r'127\.0\.0\.1',
            r'0\.0\.0\.0',
            r'192\.168\.',
            r'10\.',
            r'172\.(1[6-9]|2[0-9]|3[0-1])\.'
        ]

        for pattern in internal_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Webhook URL cannot point to internal network")

        return v


# === Request Signing & Verification ===

class RequestSigner:
    """Sign and verify requests for authentication"""

    def __init__(self, secret_key: str):
        """
        Initialize request signer

        Args:
            secret_key: Secret key for signing
        """
        self.secret_key = secret_key.encode('utf-8')

    def sign_request(self, data: Dict[str, Any]) -> str:
        """
        Sign a request payload

        Args:
            data: Request data

        Returns:
            Signature string
        """
        # Sort keys for consistent signing
        sorted_data = json.dumps(data, sort_keys=True)

        # Create HMAC signature
        signature = hmac.new(
            self.secret_key,
            sorted_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def verify_request(self,
                       data: Dict[str, Any],
                       signature: str) -> bool:
        """
        Verify a request signature

        Args:
            data: Request data
            signature: Provided signature

        Returns:
            True if signature is valid
        """
        expected_signature = self.sign_request(data)

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_signature, signature)


# === Rate Limiting ===

class RateLimiter:
    """Rate limiting for API endpoints"""

    def __init__(self):
        self.requests: Dict[str, List[datetime]] = {}

    def check_rate_limit(self,
                        identifier: str,
                        max_requests: int = 100,
                        window_seconds: int = 60) -> bool:
        """
        Check if request is within rate limit

        Args:
            identifier: Client identifier (IP, API key, etc.)
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds

        Returns:
            True if within limit
        """
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)

        # Get request history
        if identifier not in self.requests:
            self.requests[identifier] = []

        # Remove old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > window_start
        ]

        # Check limit
        if len(self.requests[identifier]) >= max_requests:
            return False

        # Add current request
        self.requests[identifier].append(now)
        return True


# === Secure Configuration ===

class SecureConfig:
    """Secure configuration management"""

    def __init__(self, config_data: Dict[str, Any]):
        """
        Initialize secure config

        Args:
            config_data: Configuration dictionary
        """
        self.config = self._sanitize_config(config_data)
        self._validate_security_settings()

    def _sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize configuration data"""
        sanitized = {}

        for key, value in config.items():
            # Skip sensitive keys from logs
            if any(sensitive in key.lower() for sensitive in
                   ['password', 'secret', 'key', 'token']):
                # Don't include actual value in sanitized version
                sanitized[key] = "***REDACTED***" if value else None
            else:
                if isinstance(value, str):
                    # Sanitize strings
                    sanitized[key] = self._sanitize_value(value)
                elif isinstance(value, dict):
                    # Recursively sanitize nested dicts
                    sanitized[key] = self._sanitize_config(value)
                else:
                    sanitized[key] = value

        return sanitized

    def _sanitize_value(self, value: str) -> str:
        """Sanitize a configuration value"""
        # Remove potential command injection
        dangerous_chars = [';', '|', '&', '$', '`', '\\', '\n', '\r']
        for char in dangerous_chars:
            value = value.replace(char, '')

        # Remove path traversal
        value = value.replace('../', '').replace('..\\', '')

        return value

    def _validate_security_settings(self):
        """Validate security-critical settings"""
        # Check for secure defaults
        if self.config.get('ssl_enabled', True) is False:
            logger.warning("SSL is disabled - this is insecure!")

        if self.config.get('debug_mode', False) is True:
            logger.warning("Debug mode is enabled - disable in production!")

        if self.config.get('allow_all_origins', False) is True:
            logger.warning("CORS allow_all_origins is enabled - security risk!")


# === API Security ===

class APISecurityValidator:
    """Validator for API security"""

    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """
        Validate API key format and strength

        Args:
            api_key: API key to validate

        Returns:
            True if valid
        """
        # Check length
        if len(api_key) < 32:
            return False

        # Check for common patterns
        if api_key.startswith('sk_test_') or api_key.startswith('pk_test_'):
            logger.warning("Test API key detected")

        # Check entropy (simplified)
        unique_chars = len(set(api_key))
        if unique_chars < 10:
            return False  # Low entropy

        return True

    @staticmethod
    def generate_api_key() -> str:
        """
        Generate a secure API key

        Returns:
            Secure API key
        """
        # Generate 32 bytes of random data
        random_bytes = secrets.token_bytes(32)

        # Convert to hex string
        api_key = f"sk_live_{random_bytes.hex()}"

        return api_key

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """
        Hash an API key for storage

        Args:
            api_key: API key to hash

        Returns:
            Hashed API key
        """
        # Use SHA-256 for hashing
        return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


# === XSS Prevention ===

class XSSPrevention:
    """Cross-site scripting prevention"""

    @staticmethod
    def sanitize_html(text: str) -> str:
        """
        Sanitize HTML content

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text
        """
        # HTML entity encoding
        html_escapes = {
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '&': '&amp;',
            '/': '&#x2F;',
            '`': '&#x60;',
            '=': '&#x3D;'
        }

        for char, escape in html_escapes.items():
            text = text.replace(char, escape)

        return text

    @staticmethod
    def sanitize_json(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize JSON data

        Args:
            data: JSON data

        Returns:
            Sanitized data
        """
        sanitized = {}

        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = XSSPrevention.sanitize_html(value)
            elif isinstance(value, dict):
                sanitized[key] = XSSPrevention.sanitize_json(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    XSSPrevention.sanitize_html(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized


# === Composite Security Validator ===

class SecurityValidator:
    """Main security validator combining all checks"""

    def __init__(self, security_level: SecurityLevel = SecurityLevel.HIGH):
        """
        Initialize security validator

        Args:
            security_level: Security validation level
        """
        self.security_level = security_level
        self.rate_limiter = RateLimiter()
        self.request_signer = None

    def validate_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize order data

        Args:
            order_data: Raw order data

        Returns:
            Validated order data

        Raises:
            ValidationError: If validation fails
        """
        try:
            # Validate with Pydantic
            validated = OrderValidator(**order_data)

            # Additional security checks for high security
            if self.security_level in [SecurityLevel.HIGH, SecurityLevel.CRITICAL]:
                # Check for suspicious patterns
                if self._is_suspicious_order(validated.dict()):
                    raise ValueError("Order flagged as suspicious")

            return validated.dict()

        except ValidationError as e:
            logger.error(f"Order validation failed: {e}")
            raise

    def validate_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration data

        Args:
            config_data: Raw configuration

        Returns:
            Validated configuration

        Raises:
            ValidationError: If validation fails
        """
        try:
            validated = ConfigValidator(**config_data)
            return validated.dict()
        except ValidationError as e:
            logger.error(f"Config validation failed: {e}")
            raise

    def _is_suspicious_order(self, order: Dict[str, Any]) -> bool:
        """
        Check for suspicious order patterns

        Args:
            order: Order data

        Returns:
            True if suspicious
        """
        # Check for unusual quantity
        if order['quantity'] > 10000:
            logger.warning(f"Large order quantity: {order['quantity']}")
            return True

        # Check for price manipulation attempts
        if order.get('limit_price'):
            # Check for penny stock manipulation
            if order['limit_price'] < 1 and order['quantity'] > 1000:
                logger.warning("Potential penny stock manipulation")
                return True

        return False

    def sanitize_user_input(self, input_data: Any) -> Any:
        """
        Sanitize any user input

        Args:
            input_data: User input

        Returns:
            Sanitized input
        """
        if isinstance(input_data, str):
            # Remove dangerous characters
            input_data = re.sub(r'[<>&\'"`]', '', input_data)

            # Truncate to reasonable length
            input_data = input_data[:1000]

        elif isinstance(input_data, dict):
            input_data = XSSPrevention.sanitize_json(input_data)

        return input_data


# === Example Usage ===

def main():
    """Example of using security validators"""

    # Initialize validator
    validator = SecurityValidator(SecurityLevel.HIGH)

    # Validate order
    order_data = {
        "ticker": "AAPL",
        "side": "BUY",
        "quantity": 100,
        "order_type": "LIMIT",
        "limit_price": "150.50",
        "notes": "Test order <script>alert('xss')</script>"
    }

    try:
        validated_order = validator.validate_order(order_data)
        print(f"Validated order: {validated_order}")
    except ValidationError as e:
        print(f"Validation failed: {e}")

    # Generate secure API key
    api_key = APISecurityValidator.generate_api_key()
    print(f"Generated API key: {api_key}")

    # Hash for storage
    hashed = APISecurityValidator.hash_api_key(api_key)
    print(f"Hashed key: {hashed}")

    # Rate limiting
    rate_limiter = RateLimiter()
    for i in range(5):
        allowed = rate_limiter.check_rate_limit("user123", max_requests=3, window_seconds=10)
        print(f"Request {i+1}: {'Allowed' if allowed else 'Blocked'}")


if __name__ == "__main__":
    main()