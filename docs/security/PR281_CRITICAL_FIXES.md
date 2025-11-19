# PR #281 Critical Security Fixes

**Priority**: CRITICAL
**Impact**: Prevents path traversal attacks, data loss, and unauthorized file access
**Estimated Total Time**: 15-20 minutes

---

## Fix 1: ChromaDB Reset Flag - Production Hardening

**File**: `/tradingagents/agents/utils/memory.py`
**Line**: 13
**Severity**: HIGH - Allows complete database deletion
**Time to Apply**: 2 minutes

### Why This Matters
Setting `allow_reset=True` in production allows anyone with access to completely wipe the ChromaDB database. This is a data loss risk and should only be enabled in development/testing environments.

### BEFORE
```python
def __init__(self, name, config):
    if config["backend_url"] == "http://localhost:11434/v1":
        self.embedding = "nomic-embed-text"
    else:
        self.embedding = "text-embedding-3-small"
    self.client = OpenAI(base_url=config["backend_url"])
    self.chroma_client = chromadb.Client(Settings(allow_reset=True))  # ⚠️ DANGEROUS
    self.situation_collection = self.chroma_client.create_collection(name=name)
```

### AFTER
```python
def __init__(self, name, config):
    if config["backend_url"] == "http://localhost:11434/v1":
        self.embedding = "nomic-embed-text"
    else:
        self.embedding = "text-embedding-3-small"
    self.client = OpenAI(base_url=config["backend_url"])
    self.chroma_client = chromadb.Client(Settings(allow_reset=False))  # ✓ SECURE
    self.situation_collection = self.chroma_client.create_collection(name=name)
```

---

## Fix 2: Input Validation - Prevent Path Traversal

**File**: `/tradingagents/dataflows/local.py`
**Lines**: 11-50, 51-84, and similar patterns throughout
**Severity**: CRITICAL - Allows arbitrary file access
**Time to Apply**: 8-10 minutes

### Why This Matters
Ticker symbols are directly interpolated into file paths without validation. An attacker could provide input like `../../etc/passwd` or `../../../sensitive_data` to access files outside the intended directory.

### BEFORE
```python
def get_YFin_data_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    # calculate past days
    date_obj = datetime.strptime(curr_date, "%Y-%m-%d")
    before = date_obj - relativedelta(days=look_back_days)
    start_date = before.strftime("%Y-%m-%d")

    # read in data
    data = pd.read_csv(
        os.path.join(
            DATA_DIR,
            f"market_data/price_data/{symbol}-YFin-data-2015-01-01-2025-03-25.csv",  # ⚠️ VULNERABLE
        )
    )
```

### AFTER
```python
import re

def validate_ticker_symbol(symbol: str) -> str:
    """
    Validate and sanitize ticker symbol to prevent path traversal.

    Args:
        symbol: Ticker symbol to validate

    Returns:
        Sanitized ticker symbol

    Raises:
        ValueError: If ticker contains invalid characters
    """
    # Ticker symbols should only contain alphanumeric characters, dots, and hyphens
    if not re.match(r'^[A-Za-z0-9.\-]+$', symbol):
        raise ValueError(f"Invalid ticker symbol: {symbol}")

    # Prevent path traversal patterns
    if '..' in symbol or '/' in symbol or '\\' in symbol:
        raise ValueError(f"Invalid ticker symbol: {symbol}")

    # Limit length (typical tickers are 1-5 characters, extended can be longer)
    if len(symbol) > 10:
        raise ValueError(f"Ticker symbol too long: {symbol}")

    return symbol.upper()  # Normalize to uppercase


def get_YFin_data_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    # Validate ticker symbol
    symbol = validate_ticker_symbol(symbol)  # ✓ SECURE

    # calculate past days
    date_obj = datetime.strptime(curr_date, "%Y-%m-%d")
    before = date_obj - relativedelta(days=look_back_days)
    start_date = before.strftime("%Y-%m-%d")

    # read in data
    data = pd.read_csv(
        os.path.join(
            DATA_DIR,
            f"market_data/price_data/{symbol}-YFin-data-2015-01-01-2025-03-25.csv",  # ✓ SAFE NOW
        )
    )
```

### Additional Changes Required
Apply the `validate_ticker_symbol()` call to ALL functions in `local.py` that accept a ticker parameter:
- `get_YFin_data()` - line 51
- `get_finnhub_news()` - line 85
- `get_finnhub_company_insider_sentiment()` - line 120
- `get_finnhub_company_insider_transactions()` - line 157
- `get_data_in_range()` - line 194
- `get_simfin_balance_sheet()` - line 227
- `get_simfin_cashflow()` - line 274
- `get_simfin_income_statements()` - line 321

**Pattern to apply:**
```python
def function_name(ticker: str, ...):
    ticker = validate_ticker_symbol(ticker)  # Add this as first line
    # ... rest of function
```

---

## Fix 3: CLI Input Validation

**File**: `/cli/main.py`
**Lines**: 499-501, 438
**Severity**: HIGH - Entry point for malicious input
**Time to Apply**: 3-5 minutes

### Why This Matters
The CLI accepts ticker symbols without validation, which feeds directly into the vulnerable file path operations in `local.py`. This is the primary attack vector.

### BEFORE
```python
def get_ticker():
    """Get ticker symbol from user input."""
    return typer.prompt("", default="SPY")  # ⚠️ NO VALIDATION
```

### AFTER
```python
def get_ticker():
    """Get ticker symbol from user input with validation."""
    while True:
        ticker = typer.prompt("", default="SPY")
        try:
            # Validate ticker format (alphanumeric, dots, hyphens only)
            if not ticker or len(ticker) > 10:
                console.print("[red]Error: Ticker must be 1-10 characters[/red]")
                continue

            # Check for path traversal attempts
            if '..' in ticker or '/' in ticker or '\\' in ticker:
                console.print("[red]Error: Invalid characters in ticker symbol[/red]")
                continue

            # Validate characters
            if not all(c.isalnum() or c in '.-' for c in ticker):
                console.print("[red]Error: Ticker can only contain letters, numbers, dots, and hyphens[/red]")
                continue

            return ticker.upper()  # ✓ SECURE AND NORMALIZED
        except Exception as e:
            console.print(f"[red]Error validating ticker: {e}[/red]")
```

---

## Testing Recommendations

After applying these fixes, test with these attack vectors to ensure they're blocked:

```bash
# Test CLI with malicious input
python -m cli.main analyze
# Try entering: ../../etc/passwd
# Try entering: ../../../sensitive_file
# Try entering: AAPL/../../../etc/hosts

# Test programmatically
python -c "
from tradingagents.dataflows.local import validate_ticker_symbol
try:
    validate_ticker_symbol('../../etc/passwd')
    print('FAIL: Attack not blocked')
except ValueError:
    print('PASS: Attack blocked')
"
```

---

## Summary

| Fix | File | Lines Changed | Time | Risk Reduced |
|-----|------|---------------|------|--------------|
| ChromaDB Reset | `memory.py` | 1 | 2 min | Data loss |
| Path Traversal | `local.py` | ~30 | 10 min | File access |
| CLI Validation | `cli/main.py` | ~20 | 5 min | Attack vector |

**Total Estimated Time**: 15-20 minutes
**Security Impact**: Prevents critical path traversal and data loss vulnerabilities

---

## References

- CWE-22: Improper Limitation of a Pathname to a Restricted Directory ('Path Traversal')
- CWE-73: External Control of File Name or Path
- OWASP Top 10: A01:2021 – Broken Access Control
