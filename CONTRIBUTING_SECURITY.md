# Security Best Practices for Contributors

Thank you for contributing to TradingAgents! Security is a top priority for this project. This guide outlines security best practices all contributors should follow.

## Table of Contents

1. [General Security Principles](#general-security-principles)
2. [Code Security Guidelines](#code-security-guidelines)
3. [Secure Coding Checklist](#secure-coding-checklist)
4. [Common Vulnerabilities to Avoid](#common-vulnerabilities-to-avoid)
5. [Security Testing](#security-testing)
6. [Code Review Security Focus](#code-review-security-focus)
7. [Tools and Resources](#tools-and-resources)

---

## General Security Principles

### Defense in Depth
Always implement multiple layers of security:
- Input validation
- Output encoding
- Least privilege
- Fail securely

### Secure by Default
- Default configurations should be secure
- Require explicit opt-in for insecure features
- Never expose sensitive data by default

### Zero Trust
- Validate all inputs, even from trusted sources
- Never assume data is safe
- Always sanitize before use

---

## Code Security Guidelines

### 1. Input Validation

**ALWAYS validate all user inputs:**

```python
# ✗ BAD - No validation
def get_stock_data(ticker: str):
    return fetch_data(ticker)

# ✓ GOOD - Proper validation
from tradingagents.security import validate_ticker

def get_stock_data(ticker: str):
    ticker = validate_ticker(ticker)  # Raises ValueError if invalid
    return fetch_data(ticker)
```

**Use the provided validators:**

```python
from tradingagents.security import (
    validate_ticker,
    validate_date,
    sanitize_path_component,
    validate_api_key
)

# Validate ticker symbols
ticker = validate_ticker(user_input)

# Validate dates
date = validate_date(user_input_date)

# Sanitize file paths
safe_filename = sanitize_path_component(user_filename)

# Validate API keys
api_key = validate_api_key(os.getenv("API_KEY"), "API_KEY")
```

### 2. Path Traversal Prevention

**NEVER use user input directly in file paths:**

```python
# ✗ BAD - Path traversal vulnerability
from pathlib import Path
results_dir = Path("./results") / user_ticker / user_date

# ✓ GOOD - Sanitized path
from tradingagents.security import sanitize_path_component
results_dir = Path("./results") / sanitize_path_component(user_ticker) / sanitize_path_component(user_date)
```

### 3. Secret Management

**NEVER hardcode secrets:**

```python
# ✗ BAD - Hardcoded secret
API_KEY = "sk-1234567890abcdef"

# ✗ BAD - Hardcoded path with personal info
DATA_DIR = "/Users/john/Documents/private-data"

# ✓ GOOD - Environment variable
import os
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable not set")

# ✓ GOOD - Configurable path
DATA_DIR = os.getenv("TRADINGAGENTS_DATA_DIR", "./data")
```

### 4. API Security

**Always implement proper error handling and timeouts:**

```python
# ✗ BAD - No timeout, poor error handling
response = requests.get(url)
data = response.json()

# ✓ GOOD - Timeout and proper error handling
try:
    response = requests.get(
        url,
        timeout=30,  # 30 second timeout
        verify=True  # Verify SSL certificates
    )
    response.raise_for_status()
    data = response.json()
except requests.exceptions.Timeout:
    logger.error("Request timed out")
    raise
except requests.exceptions.RequestException as e:
    logger.error(f"Request failed: {e}")
    raise
```

**Use rate limiting:**

```python
from tradingagents.security import RateLimiter

# Apply rate limiting to API calls
@RateLimiter(max_calls=60, period=60)  # 60 calls per minute
def fetch_stock_data(ticker: str):
    return api.get_stock_data(ticker)
```

### 5. URL Construction

**Always encode user input in URLs:**

```python
# ✗ BAD - Direct string interpolation
url = f"https://api.example.com/search?q={user_query}"

# ✓ GOOD - Proper URL encoding
from urllib.parse import quote_plus
url = f"https://api.example.com/search?q={quote_plus(user_query)}"

# ✓ BETTER - Use params argument
import requests
response = requests.get(
    "https://api.example.com/search",
    params={"q": user_query}  # Automatically encoded
)
```

### 6. SQL Injection Prevention

**If you add database functionality:**

```python
# ✗ BAD - SQL injection vulnerability
query = f"SELECT * FROM stocks WHERE ticker = '{user_ticker}'"

# ✓ GOOD - Parameterized query
query = "SELECT * FROM stocks WHERE ticker = ?"
cursor.execute(query, (user_ticker,))
```

### 7. Safe File Operations

**Always validate file paths and use safe methods:**

```python
# ✗ BAD - Unsafe file read
with open(user_provided_path, 'r') as f:
    data = f.read()

# ✓ GOOD - Validated and safe
from pathlib import Path
from tradingagents.security import sanitize_path_component

safe_path = Path("./data") / sanitize_path_component(user_filename)
# Ensure path is within allowed directory
if not safe_path.resolve().is_relative_to(Path("./data").resolve()):
    raise ValueError("Invalid file path")

with open(safe_path, 'r') as f:
    data = f.read()
```

### 8. Logging Security

**Never log sensitive information:**

```python
# ✗ BAD - Logging sensitive data
logger.info(f"API request with key: {api_key}")
logger.debug(f"User password: {password}")

# ✓ GOOD - Safe logging
logger.info(f"API request initiated")
logger.debug(f"User ID: {user_id}")  # OK to log non-sensitive IDs

# ✓ GOOD - Redact sensitive data
def redact_api_key(key: str) -> str:
    if len(key) > 8:
        return f"{key[:4]}...{key[-4:]}"
    return "***"

logger.info(f"Using API key: {redact_api_key(api_key)}")
```

### 9. Error Messages

**Don't leak sensitive information in error messages:**

```python
# ✗ BAD - Leaking internal paths
except Exception as e:
    return f"Error reading file: {str(e)}"  # Might expose paths

# ✓ GOOD - Generic error message
except FileNotFoundError:
    logger.error(f"File not found: {safe_path}")
    return "The requested file was not found"
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return "An error occurred while processing your request"
```

### 10. Type Hints and Validation

**Use type hints for better security:**

```python
from typing import Dict, List, Optional
from datetime import datetime

# ✓ GOOD - Clear types make validation easier
def analyze_stock(
    ticker: str,
    start_date: str,
    end_date: str,
    config: Optional[Dict] = None
) -> Dict[str, float]:
    """
    Analyze stock performance.

    Args:
        ticker: Stock ticker symbol (validated)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        config: Optional configuration dictionary

    Returns:
        Dictionary with analysis results

    Raises:
        ValueError: If inputs are invalid
    """
    ticker = validate_ticker(ticker)
    start_date = validate_date(start_date)
    end_date = validate_date(end_date)

    # Implementation...
    return {"return": 0.15}
```

---

## Secure Coding Checklist

Before submitting a pull request, verify:

- [ ] **Input Validation**
  - [ ] All user inputs are validated
  - [ ] Used appropriate validators from `tradingagents.security`
  - [ ] Edge cases are handled

- [ ] **Path Security**
  - [ ] No user input in file paths without sanitization
  - [ ] Used `sanitize_path_component` for file operations
  - [ ] Paths are restricted to allowed directories

- [ ] **Secret Management**
  - [ ] No hardcoded API keys, passwords, or secrets
  - [ ] Environment variables used for configuration
  - [ ] No personal file paths or usernames in code

- [ ] **API Security**
  - [ ] All HTTP requests have timeouts
  - [ ] SSL verification is enabled
  - [ ] Error handling is comprehensive
  - [ ] Rate limiting is applied where appropriate

- [ ] **Error Handling**
  - [ ] Errors are logged appropriately
  - [ ] Sensitive data is not in error messages
  - [ ] Failures are handled gracefully

- [ ] **Logging**
  - [ ] No sensitive data in logs
  - [ ] Appropriate log levels used
  - [ ] Security events are logged

- [ ] **Code Quality**
  - [ ] Type hints added
  - [ ] Docstrings include security notes
  - [ ] Code is readable and maintainable

- [ ] **Testing**
  - [ ] Security tests added
  - [ ] Edge cases tested
  - [ ] Error paths tested

---

## Common Vulnerabilities to Avoid

### 1. Path Traversal (CWE-22)

```python
# ✗ VULNERABLE
user_file = request.get("file")
with open(f"./data/{user_file}", 'r') as f:
    # Attacker could use: ../../../../etc/passwd
    data = f.read()

# ✓ SECURE
from tradingagents.security import sanitize_path_component
user_file = sanitize_path_component(request.get("file"))
safe_path = Path("./data") / user_file
if not safe_path.resolve().is_relative_to(Path("./data").resolve()):
    raise ValueError("Invalid path")
```

### 2. SQL Injection (CWE-89)

```python
# ✗ VULNERABLE
ticker = request.get("ticker")
query = f"SELECT * FROM stocks WHERE ticker = '{ticker}'"
# Attacker could use: AAPL'; DROP TABLE stocks; --

# ✓ SECURE
query = "SELECT * FROM stocks WHERE ticker = ?"
cursor.execute(query, (ticker,))
```

### 3. Command Injection (CWE-78)

```python
# ✗ VULNERABLE
import subprocess
user_input = request.get("command")
subprocess.run(f"process_data {user_input}", shell=True)

# ✓ SECURE - Don't use shell=True, validate inputs
allowed_commands = ['analyze', 'report', 'export']
if user_input not in allowed_commands:
    raise ValueError("Invalid command")
subprocess.run(["process_data", user_input], shell=False)
```

### 4. SSRF (Server-Side Request Forgery) (CWE-918)

```python
# ✗ VULNERABLE
user_url = request.get("data_source")
response = requests.get(user_url)

# ✓ SECURE
from tradingagents.security.validators import validate_url
user_url = validate_url(user_url, allowed_schemes=['https'])
# URL validator blocks private IPs, localhost, etc.
response = requests.get(user_url, timeout=10)
```

### 5. Insecure Deserialization (CWE-502)

```python
# ✗ VULNERABLE
import pickle
data = pickle.loads(user_provided_data)

# ✓ SECURE - Use safe serialization
import json
try:
    data = json.loads(user_provided_data)
except json.JSONDecodeError:
    raise ValueError("Invalid JSON data")
```

### 6. Information Disclosure (CWE-200)

```python
# ✗ VULNERABLE
@app.route("/debug")
def debug():
    return {"config": app.config, "env": os.environ}

# ✓ SECURE
@app.route("/health")
def health():
    return {"status": "healthy", "version": VERSION}
```

### 7. Insufficient Logging & Monitoring (CWE-778)

```python
# ✗ INSUFFICIENT
def transfer_funds(amount):
    # No logging of financial transaction
    execute_transfer(amount)

# ✓ SECURE
import logging
security_logger = logging.getLogger('security')

def transfer_funds(amount, user_id):
    security_logger.info(
        f"Transfer initiated",
        extra={
            "user_id": user_id,
            "amount": amount,
            "timestamp": datetime.now().isoformat()
        }
    )
    try:
        execute_transfer(amount)
        security_logger.info(f"Transfer completed for user {user_id}")
    except Exception as e:
        security_logger.error(f"Transfer failed for user {user_id}: {e}")
        raise
```

---

## Security Testing

### Write Security Tests

```python
# tests/security/test_input_validation.py
import pytest
from tradingagents.security import validate_ticker, sanitize_path_component

def test_validate_ticker_prevents_path_traversal():
    """Test that ticker validation prevents path traversal."""
    malicious_inputs = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "ticker/../../../secrets"
    ]

    for malicious in malicious_inputs:
        with pytest.raises(ValueError, match="Invalid ticker"):
            validate_ticker(malicious)

def test_sanitize_path_component():
    """Test path sanitization."""
    assert sanitize_path_component("../etc/passwd") == "etcpasswd"
    assert sanitize_path_component("normal_file.txt") == "normal_file.txt"
    assert ".." not in sanitize_path_component("../../data")

def test_api_key_validation():
    """Test API key validation."""
    from tradingagents.security import validate_api_key

    # Should pass
    validate_api_key("sk-1234567890abcdef", "TEST_KEY")

    # Should fail
    with pytest.raises(ValueError):
        validate_api_key(None, "TEST_KEY")

    with pytest.raises(ValueError):
        validate_api_key("", "TEST_KEY")
```

### Run Security Scans

```bash
# Static security analysis
bandit -r tradingagents/ -ll

# Dependency vulnerability scan
safety check
pip-audit

# Secret scanning
gitleaks detect --source=. --verbose
```

---

## Code Review Security Focus

When reviewing code, check for:

### Input Validation
- [ ] All user inputs are validated
- [ ] Validation happens on server side
- [ ] Whitelist approach used where possible

### Authentication & Authorization
- [ ] Proper authentication checks
- [ ] Authorization before sensitive operations
- [ ] Session management is secure

### Data Protection
- [ ] Sensitive data is encrypted
- [ ] No secrets in code or logs
- [ ] Proper error handling doesn't leak info

### API Security
- [ ] Rate limiting implemented
- [ ] Timeouts configured
- [ ] SSL/TLS used for all connections

### Dependencies
- [ ] Dependencies are up to date
- [ ] No known vulnerabilities
- [ ] Minimal dependencies used

---

## Tools and Resources

### Security Tools

1. **Bandit** - Python security linter
   ```bash
   pip install bandit
   bandit -r tradingagents/
   ```

2. **Safety** - Dependency vulnerability scanner
   ```bash
   pip install safety
   safety check
   ```

3. **pip-audit** - Another dependency scanner
   ```bash
   pip install pip-audit
   pip-audit
   ```

4. **Gitleaks** - Secret scanning
   ```bash
   docker run -v $(pwd):/path zricethezav/gitleaks:latest detect --source="/path"
   ```

5. **Pre-commit hooks** - Automated checks
   ```bash
   pip install pre-commit
   pre-commit install
   ```

### Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [NIST Guidelines](https://www.nist.gov/cybersecurity)

---

## Questions?

If you have security questions or concerns:
- Email: yijia.xiao@cs.ucla.edu
- Review: [SECURITY.md](SECURITY.md)
- Check: [SECURITY_AUDIT.md](SECURITY_AUDIT.md)

**Remember: When in doubt, ask before committing!**

Thank you for keeping TradingAgents secure!
