# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of TradingAgents seriously. If you believe you have found a security vulnerability, please report it to us as described below.

**Please do NOT report security vulnerabilities through public GitHub issues.**

### How to Report

Please report security vulnerabilities by emailing: **yijia.xiao@cs.ucla.edu**

Include the following information in your report:

1. **Type of vulnerability** (e.g., SQL injection, XSS, path traversal)
2. **Full paths of source file(s)** related to the vulnerability
3. **Location** of the affected source code (tag/branch/commit or direct URL)
4. **Step-by-step instructions** to reproduce the issue
5. **Proof-of-concept or exploit code** (if possible)
6. **Impact** of the vulnerability

### What to Expect

- We will acknowledge your email within **48 hours**
- We will provide a more detailed response within **7 days**
- We will work to verify and fix the vulnerability as quickly as possible
- We will credit you in our security advisory (unless you prefer to remain anonymous)

## Security Best Practices for Users

### API Key Management

1. **Never commit API keys** to version control
2. **Use environment variables** or `.env` files (which are gitignored)
3. **Rotate keys regularly** - at least every 90 days
4. **Use different keys** for development and production
5. **Monitor API usage** for unusual patterns

Example `.env` file:
```bash
OPENAI_API_KEY=your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here
TRADINGAGENTS_DATA_DIR=/path/to/safe/data/directory
TRADINGAGENTS_RESULTS_DIR=/path/to/safe/results/directory
```

### Input Validation

Always validate user inputs when using TradingAgents:

```python
from tradingagents.utils import validate_ticker, validate_date

# Validate ticker
try:
    ticker = validate_ticker(user_input_ticker)
except ValueError as e:
    print(f"Invalid ticker: {e}")

# Validate date
try:
    date = validate_date(user_input_date)
except ValueError as e:
    print(f"Invalid date: {e}")
```

### Secure File Paths

The framework now automatically sanitizes file paths. However, you should still:

1. **Never use user input directly** in file paths
2. **Use the built-in sanitization** functions
3. **Validate all file operations**

```python
from tradingagents.security import sanitize_path_component
from pathlib import Path

# Safe file path construction
ticker = sanitize_path_component(user_input_ticker)
date = sanitize_path_component(user_input_date)
safe_path = Path(results_dir) / ticker / date
```

### Rate Limiting

To avoid hitting API rate limits:

```python
from tradingagents.security import RateLimiter

# Limit to 60 calls per minute
@RateLimiter(max_calls=60, period=60)
def my_api_call():
    # Your API call here
    pass
```

### Logging and Monitoring

1. **Enable security logging** in production
2. **Monitor for unusual patterns**:
   - Excessive API calls
   - Failed authentication attempts
   - Unusual ticker symbols
3. **Set up alerts** for security events

### Network Security

1. **Always use HTTPS** for API calls
2. **Verify SSL certificates**
3. **Set appropriate timeouts**
4. **Use VPN or private networks** when possible

### Data Protection

1. **Encrypt sensitive data** at rest
2. **Don't log API keys** or sensitive data
3. **Implement data retention policies**
4. **Follow GDPR/CCPA** if applicable

## Known Security Enhancements

The following security enhancements have been implemented:

### Version 0.1.1 (Current)

- **Path traversal protection**: All file paths are now sanitized
- **Input validation**: Ticker symbols and dates are validated
- **API key validation**: Keys are validated before use
- **Rate limiting**: Built-in rate limiter to prevent quota exhaustion
- **Secure defaults**: Hardcoded paths removed, environment variables used
- **URL validation**: Protection against SSRF attacks
- **Timeout enforcement**: All network requests have timeouts

### Pending Security Enhancements

- Comprehensive test suite with security tests
- Automated secret scanning in CI/CD
- Dependency vulnerability scanning
- Security headers for any web interfaces
- Audit logging for security events

## Security Disclosure Policy

### Timeline

- **Day 0**: Vulnerability reported to security team
- **Day 1-2**: Acknowledgment sent to reporter
- **Day 3-7**: Vulnerability verified and severity assessed
- **Day 7-30**: Fix developed and tested
- **Day 30-45**: Fix released and advisory published
- **Day 45+**: Full disclosure (if agreed with reporter)

### Severity Levels

| Severity | Description | Response Time |
|----------|-------------|---------------|
| Critical | Actively exploited, remote code execution, data breach | 24-48 hours |
| High | Authentication bypass, privilege escalation | 1 week |
| Medium | Information disclosure, DoS | 2 weeks |
| Low | Limited impact, requires specific conditions | 1 month |

## Security Acknowledgments

We would like to thank the following people for their responsible disclosure of security vulnerabilities:

- *Your name could be here!*

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CWE/SANS Top 25](https://www.sans.org/top25-software-errors/)

## Security Contacts

- **Security Email**: yijia.xiao@cs.ucla.edu
- **GitHub Security Advisories**: https://github.com/TauricResearch/TradingAgents/security/advisories

## Legal

This security policy is provided "as is" without warranty of any kind. The TradingAgents team reserves the right to modify this policy at any time.

Last updated: 2025-11-14
