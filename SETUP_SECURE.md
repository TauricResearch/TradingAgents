# Secure Setup Guide for TradingAgents

This guide will help you set up TradingAgents with security best practices in mind.

## Prerequisites

- Python 3.10 or higher
- Git
- API keys for OpenAI and Alpha Vantage

## Step 1: Clone the Repository

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

## Step 2: Create Virtual Environment

**Always use a virtual environment** to isolate dependencies:

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate
```

## Step 3: Install Dependencies Securely

```bash
# Upgrade pip first
pip install --upgrade pip

# Install dependencies from requirements.txt
pip install -r requirements.txt

# Optional: Install development dependencies
pip install pytest bandit black flake8 mypy safety
```

### Verify Dependency Security

```bash
# Check for known vulnerabilities
pip install safety
safety check

# Or use pip-audit
pip install pip-audit
pip-audit
```

## Step 4: Configure Environment Variables

**CRITICAL: Never hardcode API keys in your code!**

### Create .env File

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your actual values
# Use your preferred editor (nano, vim, code, etc.)
nano .env
```

### Fill in Your API Keys

Edit `.env` to include your actual API keys:

```bash
# Required API Keys
OPENAI_API_KEY=sk-your-actual-openai-key-here
ALPHA_VANTAGE_API_KEY=your-actual-alpha-vantage-key-here

# Optional: Custom directories
TRADINGAGENTS_DATA_DIR=/secure/path/to/data
TRADINGAGENTS_RESULTS_DIR=/secure/path/to/results

# Optional: Logging
LOG_LEVEL=INFO
```

### Verify .env is Gitignored

```bash
# Verify .env is in .gitignore
cat .gitignore | grep ".env"

# Should output: .env
```

## Step 5: Secure Your API Keys

### Get API Keys

1. **OpenAI API Key**:
   - Go to https://platform.openai.com/api-keys
   - Create a new secret key
   - Copy it immediately (you won't see it again)

2. **Alpha Vantage API Key**:
   - Go to https://www.alphavantage.co/support/#api-key
   - Fill in the form to get a free API key
   - Copy the key from the email

### Protect Your Keys

```bash
# Set proper permissions on .env file (Unix-like systems)
chmod 600 .env

# Verify permissions
ls -l .env
# Should show: -rw-------
```

### API Key Best Practices

1. **Use separate keys** for development and production
2. **Rotate keys regularly** (every 90 days recommended)
3. **Set spending limits** in your API provider dashboard
4. **Monitor usage** regularly for unusual activity
5. **Never share keys** via email, Slack, or other insecure channels
6. **Revoke immediately** if you suspect compromise

## Step 6: Create Secure Data Directories

```bash
# Create directories with proper permissions
mkdir -p data results

# Set restrictive permissions (Unix-like systems)
chmod 700 data results

# Verify
ls -ld data results
# Should show: drwx------
```

## Step 7: Verify Installation

```bash
# Test import
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('Success!')"

# Run security validators test
python -c "from tradingagents.security import validate_ticker; print(validate_ticker('AAPL'))"
```

## Step 8: Run Security Checks

### Static Security Analysis

```bash
# Run Bandit security linter
bandit -r tradingagents/ -ll

# Check for common security issues
python -m bandit -r tradingagents/ -f json -o security-report.json
```

### Check for Secrets in Git History

```bash
# Install trufflehog or gitleaks
# Using gitleaks:
docker run -v $(pwd):/path zricethezav/gitleaks:latest detect --source="/path" -v

# Or manually search
git log -p | grep -i "api[_-]key\|secret\|password" | head -20
```

## Step 9: Configure Logging

Create a logging configuration file:

```bash
# Create logs directory
mkdir -p logs
chmod 700 logs

# Create logging config
cat > logging_config.json <<EOF
{
  "version": 1,
  "disable_existing_loggers": false,
  "formatters": {
    "standard": {
      "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    }
  },
  "handlers": {
    "file": {
      "class": "logging.handlers.RotatingFileHandler",
      "filename": "logs/tradingagents.log",
      "maxBytes": 10485760,
      "backupCount": 5,
      "formatter": "standard"
    }
  },
  "root": {
    "level": "INFO",
    "handlers": ["file"]
  }
}
EOF
```

## Step 10: Test the Setup

Create a test script to verify everything works:

```python
# test_setup.py
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.security import validate_ticker, validate_date
from dotenv import load_dotenv
import os

# Load environment
load_dotenv()

# Verify API keys are set
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY not set"
assert os.getenv("ALPHA_VANTAGE_API_KEY"), "ALPHA_VANTAGE_API_KEY not set"
print("✓ API keys are set")

# Verify security validators
try:
    validate_ticker("AAPL")
    print("✓ Ticker validation works")
except Exception as e:
    print(f"✗ Ticker validation failed: {e}")

try:
    validate_date("2024-01-15")
    print("✓ Date validation works")
except Exception as e:
    print(f"✗ Date validation failed: {e}")

# Verify config
config = DEFAULT_CONFIG.copy()
assert config["data_dir"] != "/Users/yluo/Documents/Code/ScAI/FR1-data", \
    "Hardcoded path still present!"
print("✓ Configuration is secure")

# Test basic initialization
try:
    config["quick_think_llm"] = "gpt-4o-mini"
    config["deep_think_llm"] = "gpt-4o-mini"
    ta = TradingAgentsGraph(config=config, debug=False)
    print("✓ TradingAgents initialized successfully")
except Exception as e:
    print(f"✗ Initialization failed: {e}")

print("\n✓ All security checks passed!")
```

Run the test:

```bash
python test_setup.py
```

## Step 11: Set Up Git Hooks (Optional)

Prevent accidental commits of secrets:

```bash
# Install pre-commit hooks
pip install pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml <<EOF
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: detect-private-key
      - id: check-added-large-files
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: ['-ll', '-i']
EOF

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Step 12: Production Deployment Checklist

Before deploying to production:

- [ ] All API keys are stored securely (not in code)
- [ ] `.env` file is never committed to git
- [ ] Debug mode is disabled (`debug=False`)
- [ ] Logging is configured properly
- [ ] File permissions are restrictive (600 for files, 700 for directories)
- [ ] Dependencies are pinned to specific versions
- [ ] Security scanning is enabled in CI/CD
- [ ] Rate limiting is configured
- [ ] Monitoring and alerting are set up
- [ ] Backup strategy is in place
- [ ] Incident response plan exists

## Troubleshooting

### Issue: API Key Not Found

**Error:** `ValueError: OPENAI_API_KEY environment variable is not set`

**Solution:**
```bash
# Verify .env file exists
ls -la .env

# Verify .env is loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('OPENAI_API_KEY'))"

# Check if running from correct directory
pwd
```

### Issue: Permission Denied

**Error:** `PermissionError: [Errno 13] Permission denied`

**Solution:**
```bash
# Fix directory permissions
chmod 700 data results logs

# Fix file permissions
chmod 600 .env
```

### Issue: Import Errors

**Error:** `ModuleNotFoundError: No module named 'tradingagents'`

**Solution:**
```bash
# Verify virtual environment is activated
which python

# Reinstall in development mode
pip install -e .
```

## Security Monitoring

### Set Up Alerts

Monitor for:
1. Unusual API usage patterns
2. Failed authentication attempts
3. Large data transfers
4. Unexpected errors

### Regular Security Tasks

- **Weekly**: Review logs for anomalies
- **Monthly**: Rotate API keys
- **Quarterly**: Update dependencies and scan for vulnerabilities
- **Annually**: Full security audit

## Additional Resources

- [SECURITY.md](SECURITY.md) - Security policy and vulnerability reporting
- [SECURITY_AUDIT.md](SECURITY_AUDIT.md) - Detailed security audit results
- [IMPROVEMENTS.md](IMPROVEMENTS.md) - Suggested improvements and enhancements
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)

## Getting Help

If you encounter security issues:
1. **DO NOT** open a public GitHub issue
2. Email: yijia.xiao@cs.ucla.edu
3. Include detailed steps to reproduce
4. Wait for acknowledgment (within 48 hours)

## Conclusion

You now have a secure installation of TradingAgents! Remember:
- Keep your API keys secret
- Regularly update dependencies
- Monitor for unusual activity
- Follow security best practices

Happy and secure trading!
