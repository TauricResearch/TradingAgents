# Security Patterns Cheatsheet

Quick reference for common security patterns learned from TradingAgents security review.

---

## Input Validation Pattern

### Universal Validator Template
```python
import re

def validate_user_input(value: str, field_name: str) -> str:
    """
    Universal input validation pattern.

    Args:
        value: User-provided input
        field_name: Field name for error messages

    Returns:
        Sanitized, normalized value

    Raises:
        ValueError: If validation fails
    """
    # 1. Check for empty/null
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")

    # 2. Length limits
    if len(value) > 100:  # Adjust as needed
        raise ValueError(f"{field_name} too long (max 100 chars)")

    # 3. Path traversal prevention
    if '..' in value or '/' in value or '\\' in value:
        raise ValueError(f"Invalid characters in {field_name}")

    # 4. Character whitelist (adjust pattern as needed)
    if not re.match(r'^[A-Za-z0-9.\-_]+$', value):
        raise ValueError(f"{field_name} contains invalid characters")

    # 5. Normalize output
    return value.strip().upper()


# Example usage
try:
    ticker = validate_user_input(user_input, "ticker symbol")
except ValueError as e:
    print(f"Validation error: {e}")
```

---

## CLI Validation Loop Pattern

### User-Friendly Input Loop
```python
from rich.console import Console

console = Console()

def get_validated_input(prompt: str, default: str, validator_func) -> str:
    """
    Get validated input from user with retry loop.

    Args:
        prompt: Prompt message to display
        default: Default value
        validator_func: Function that validates and returns sanitized value

    Returns:
        Validated input
    """
    while True:
        value = input(f"{prompt} [{default}]: ") or default
        try:
            return validator_func(value)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("[yellow]Please try again[/yellow]")


# Example usage
def validate_ticker(ticker: str) -> str:
    if not re.match(r'^[A-Z]{1,5}$', ticker.upper()):
        raise ValueError("Ticker must be 1-5 letters")
    return ticker.upper()

ticker = get_validated_input("Enter ticker", "AAPL", validate_ticker)
```

---

## Path Building Pattern

### Safe Path Construction
```python
from pathlib import Path

def build_safe_path(base_dir: Path, user_input: str, extension: str = "") -> Path:
    """
    Safely construct file path from user input.

    Args:
        base_dir: Base directory (trusted)
        user_input: User-provided component (untrusted)
        extension: File extension to append

    Returns:
        Safe, resolved path

    Raises:
        ValueError: If path escapes base directory
    """
    # Validate user input first
    sanitized = validate_user_input(user_input, "path component")

    # Construct path
    if extension:
        candidate_path = base_dir / f"{sanitized}{extension}"
    else:
        candidate_path = base_dir / sanitized

    # Resolve to absolute path
    resolved_path = candidate_path.resolve()

    # Ensure it's still within base directory
    if not str(resolved_path).startswith(str(base_dir.resolve())):
        raise ValueError("Path traversal attempt detected")

    return resolved_path


# Example usage
BASE_DIR = Path("/app/data/market_data")
safe_path = build_safe_path(BASE_DIR, user_ticker, ".csv")
data = pd.read_csv(safe_path)
```

---

## Database Configuration Pattern

### Production-Safe Settings
```python
import os
from enum import Enum

class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

def get_environment() -> Environment:
    """Get current environment from env var."""
    env_str = os.getenv("ENVIRONMENT", "development").lower()
    return Environment(env_str)

def get_db_settings():
    """Get environment-appropriate database settings."""
    env = get_environment()

    if env == Environment.PRODUCTION:
        return {
            "allow_reset": False,      # Never allow in production
            "allow_delete": False,
            "backup_enabled": True,
            "encryption": True,
            "audit_log": True,
        }
    elif env == Environment.STAGING:
        return {
            "allow_reset": False,      # Usually no
            "allow_delete": True,      # Maybe for testing
            "backup_enabled": True,
            "encryption": True,
            "audit_log": True,
        }
    else:  # DEVELOPMENT
        return {
            "allow_reset": True,       # OK for local dev
            "allow_delete": True,
            "backup_enabled": False,
            "encryption": False,       # Optional for dev
            "audit_log": False,
        }


# Example usage
settings = get_db_settings()
client = chromadb.Client(Settings(allow_reset=settings["allow_reset"]))
```

---

## Error Handling Pattern

### Secure Error Messages
```python
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/app/app.log'),  # Detailed logs
        logging.StreamHandler(sys.stdout)              # User-facing logs
    ]
)

logger = logging.getLogger(__name__)

def safe_error_handler(func):
    """
    Decorator for secure error handling.
    Shows generic messages to users, logs details internally.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            # User errors - safe to show
            user_message = str(e)
            logger.warning(f"Validation error in {func.__name__}: {e}")
            return {"error": user_message, "code": "VALIDATION_ERROR"}
        except FileNotFoundError as e:
            # System errors - hide details
            logger.error(f"File not found in {func.__name__}: {e}", exc_info=True)
            return {"error": "Data not available", "code": "NOT_FOUND"}
        except Exception as e:
            # Unexpected errors - definitely hide
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            return {"error": "An error occurred. Please try again.", "code": "INTERNAL_ERROR"}

    return wrapper


# Example usage
@safe_error_handler
def process_ticker(ticker: str):
    validated_ticker = validate_ticker(ticker)  # May raise ValueError
    data = load_data(validated_ticker)          # May raise FileNotFoundError
    return analyze_data(data)                   # May raise any Exception
```

---

## Configuration File Pattern

### Secure Config Loading
```python
import os
from pathlib import Path
from typing import Dict, Any
import json

class SecureConfig:
    """Secure configuration manager."""

    REQUIRED_KEYS = [
        "DATABASE_URL",
        "API_KEY",
        "SECRET_KEY",
    ]

    SENSITIVE_KEYS = [
        "API_KEY",
        "SECRET_KEY",
        "PASSWORD",
        "TOKEN",
    ]

    def __init__(self, config_path: Path = None):
        self.config_path = config_path or Path(".env")
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._validate_config()

    def _load_config(self):
        """Load configuration from environment variables."""
        # Load from .env file
        if self.config_path.exists():
            with open(self.config_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()

        # Load from environment
        self.config = {
            key: os.getenv(key)
            for key in self.REQUIRED_KEYS
        }

    def _validate_config(self):
        """Validate required keys are present."""
        missing = [key for key in self.REQUIRED_KEYS if not self.config.get(key)]
        if missing:
            raise ValueError(f"Missing required config keys: {missing}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value."""
        return self.config.get(key, default)

    def __repr__(self) -> str:
        """Safe representation that hides sensitive values."""
        safe_config = {
            key: "***REDACTED***" if any(s in key.upper() for s in self.SENSITIVE_KEYS)
            else value
            for key, value in self.config.items()
        }
        return f"SecureConfig({safe_config})"


# Example usage
config = SecureConfig()
api_key = config.get("API_KEY")
print(config)  # Won't leak secrets
```

---

## Testing Pattern

### Security Test Template
```python
import pytest

class TestInputValidation:
    """Security tests for input validation."""

    # Valid inputs that should pass
    @pytest.mark.parametrize("valid_input", [
        "AAPL",
        "MSFT",
        "BRK.B",
        "BRK-A",
    ])
    def test_valid_inputs_pass(self, valid_input):
        """Valid inputs should be accepted."""
        result = validate_ticker_symbol(valid_input)
        assert result == valid_input.upper()

    # Attack vectors that should be blocked
    @pytest.mark.parametrize("attack_vector", [
        "../../etc/passwd",
        "../../../sensitive",
        "AAPL/../../../etc/hosts",
        "..\\..\\windows\\system32",
        "/etc/passwd",
        "\\etc\\passwd",
        "AAPL; rm -rf /",
        "<script>alert('xss')</script>",
        "VERYLONGTICKERSYMBOL",
    ])
    def test_attack_vectors_blocked(self, attack_vector):
        """Attack vectors should be rejected."""
        with pytest.raises(ValueError):
            validate_ticker_symbol(attack_vector)

    # Edge cases
    @pytest.mark.parametrize("edge_case", [
        "",           # Empty string
        None,         # None value
        " ",          # Whitespace only
        "A" * 100,    # Very long input
    ])
    def test_edge_cases_handled(self, edge_case):
        """Edge cases should be handled gracefully."""
        with pytest.raises((ValueError, TypeError)):
            validate_ticker_symbol(edge_case)
```

---

## Quick Reference: Common Vulnerabilities

### Path Traversal (CWE-22)
**Attack:** `../../etc/passwd`
**Fix:** Validate input, use Path.resolve(), check stays in base dir

### Command Injection (CWE-77)
**Attack:** `; rm -rf /`
**Fix:** Never use user input in shell commands, use subprocess with list args

### SQL Injection (CWE-89)
**Attack:** `'; DROP TABLE users; --`
**Fix:** Always use parameterized queries, never string concatenation

### XSS (CWE-79)
**Attack:** `<script>alert('xss')</script>`
**Fix:** Escape output, use Content-Security-Policy headers

### LLM Prompt Injection
**Attack:** `Ignore previous instructions and...`
**Fix:** Sanitize user input, use structured prompts, validate outputs

---

## Environment Variables Best Practices

### .env.example Template
```bash
# DO: Provide example with placeholders
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
API_KEY=your_api_key_here

# DON'T: Put real secrets in .env.example
API_KEY=sk-real-key-12345  # ❌ NEVER DO THIS

# DO: Document how to generate secure values
SECRET_KEY=generate_with_openssl_rand_hex_32

# DO: Specify required format
TICKER_SYMBOL=AAPL  # Format: 1-5 uppercase letters

# DO: Provide security warnings
# WARNING: Never commit .env file to git
# WARNING: Rotate keys every 90 days
```

### .gitignore Template
```gitignore
# Environment variables
.env
.env.local
.env.*.local

# Secrets
secrets/
*.key
*.pem

# Sensitive data
portfolio_data/
*.csv
*.json

# Logs (may contain secrets)
*.log
logs/

# Database files
*.db
*.sqlite
```

---

## Pre-commit Hooks

### .pre-commit-config.yaml
```yaml
repos:
  # Security checks
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: ['-ll', '-i']  # Low severity, interactive

  # File safety
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: detect-private-key
      - id: check-yaml
      - id: check-json
      - id: trailing-whitespace
      - id: end-of-file-fixer
```

---

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security Guide](https://python.readthedocs.io/en/stable/library/security.html)
- [Bandit Security Linter](https://bandit.readthedocs.io/)
- [Safety Dependency Scanner](https://pyup.io/safety/)
