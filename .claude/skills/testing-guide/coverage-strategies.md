# Coverage Strategies Guide

**Purpose**: Strategies and techniques for achieving and maintaining 80%+ code coverage.

**When to use**: When planning test coverage, identifying gaps, or aiming for comprehensive test suites.

---

## 80% Coverage Target

### Why 80%?

The 80% coverage threshold represents a pragmatic balance between comprehensive testing and development efficiency:

- **High confidence**: Covers the vast majority of code paths
- **Practical**: Achievable without diminishing returns
- **Maintainable**: Doesn't require testing every trivial branch
- **Industry standard**: Widely accepted as "good coverage"

### Coverage Types

**Line Coverage**: Percentage of code lines executed during tests
**Branch Coverage**: Percentage of decision branches (if/else) taken
**Function Coverage**: Percentage of functions called during tests

Aim for 80%+ in all three categories.

---

## Achieving 80%+ Coverage

### 1. Start with Critical Paths

Focus first on the most important code paths:

```python
# Critical path: User authentication
def test_successful_login():
    """Test successful user login (critical path)."""
    user = authenticate("user@example.com", "password")
    assert user is not None
    assert user.is_authenticated is True

def test_failed_login():
    """Test failed login (critical error path)."""
    user = authenticate("user@example.com", "wrong_password")
    assert user is None
```

### 2. Cover Edge Cases

Identify and test boundary conditions and edge cases:

```python
# Edge cases for string processing
@pytest.mark.parametrize("input,expected", [
    ("", ""),                    # Empty string
    ("a", "A"),                  # Single character
    ("hello", "HELLO"),          # Normal case
    ("ALREADY UPPER", "ALREADY UPPER"),  # Already uppercase
    ("123", "123"),              # Numbers only
    ("hello123", "HELLO123"),    # Mixed alphanumeric
    ("hello world", "HELLO WORLD"),  # Multiple words
    ("  spaces  ", "  SPACES  "),  # Leading/trailing spaces
])
def test_uppercase_edge_cases(input, expected):
    """Test uppercase conversion with edge cases."""
    assert to_uppercase(input) == expected
```

### 3. Test Error Handling

Error paths are often missed in coverage. Test all exception scenarios:

```python
def test_division_by_zero():
    """Test error handling for division by zero."""
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)

def test_invalid_file_path():
    """Test error handling for invalid file path."""
    with pytest.raises(FileNotFoundError):
        read_file("/nonexistent/path.txt")

def test_network_timeout():
    """Test error handling for network timeout."""
    with pytest.raises(requests.Timeout):
        fetch_data(timeout=0.001)

def test_invalid_input_validation():
    """Test validation error for invalid input."""
    with pytest.raises(ValueError, match="Input must be positive"):
        validate_input(-1)
```

### 4. Test Boundary Conditions

Test values at the edges of valid ranges:

```python
@pytest.mark.parametrize("age,valid", [
    (0, True),     # Minimum valid
    (1, True),     # Just above minimum
    (17, False),   # Just below threshold
    (18, True),    # Threshold
    (19, True),    # Just above threshold
    (120, True),   # Maximum reasonable
    (121, False),  # Above maximum
    (-1, False),   # Below minimum
])
def test_age_validation_boundaries(age, valid):
    """Test age validation at boundary conditions."""
    assert is_valid_age(age) == valid
```

### 5. Test All Branches

Ensure every if/else branch is tested:

```python
def process_status(status):
    """Process status with multiple branches."""
    if status == "active":
        return "Processing active status"
    elif status == "pending":
        return "Processing pending status"
    elif status == "completed":
        return "Processing completed status"
    else:
        return "Unknown status"

# Test all branches
def test_process_status_active():
    assert process_status("active") == "Processing active status"

def test_process_status_pending():
    assert process_status("pending") == "Processing pending status"

def test_process_status_completed():
    assert process_status("completed") == "Processing completed status"

def test_process_status_unknown():
    assert process_status("unknown") == "Unknown status"
```

---

## Coverage Tools and Configuration

### pytest-cov

```bash
# Install pytest-cov
pip install pytest-cov

# Run tests with coverage report
pytest --cov=mypackage tests/

# Generate HTML coverage report
pytest --cov=mypackage --cov-report=html tests/

# Fail if coverage below 80%
pytest --cov=mypackage --cov-fail-under=80 tests/
```

### coverage.py Configuration

Create `.coveragerc` file:

```ini
[run]
source = mypackage
omit =
    */tests/*
    */migrations/*
    */__pycache__/*
    */venv/*

[report]
precision = 2
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

### Measuring Coverage

```python
# Example: Measure coverage for specific module
pytest --cov=mypackage.auth --cov-report=term-missing tests/test_auth.py

# Output shows uncovered lines:
# mypackage/auth.py    85%   23, 45, 67
```

---

## Strategies for Hard-to-Test Code

### Strategy 1: Extract Logic

Move complex logic into testable functions:

```python
# Before: Hard to test
def process_request(request):
    if request.user.is_authenticated and request.method == "POST":
        data = json.loads(request.body)
        if validate_data(data):
            save_to_database(data)
            return HttpResponse("Success")
    return HttpResponse("Error")

# After: Testable components
def is_valid_request(user, method):
    """Check if request is valid (easily testable)."""
    return user.is_authenticated and method == "POST"

def test_is_valid_request():
    """Test request validation logic."""
    user = Mock(is_authenticated=True)
    assert is_valid_request(user, "POST") is True
    assert is_valid_request(user, "GET") is False
```

### Strategy 2: Dependency Injection

Make dependencies explicit for easier mocking:

```python
# Before: Hard to test (hardcoded dependency)
def fetch_user_data(user_id):
    db = Database()  # Hard to mock
    return db.query(user_id)

# After: Testable with dependency injection
def fetch_user_data(user_id, database=None):
    db = database or Database()
    return db.query(user_id)

def test_fetch_user_data():
    """Test with injected mock database."""
    mock_db = Mock()
    mock_db.query.return_value = {"id": 1, "name": "Test"}
    result = fetch_user_data(1, database=mock_db)
    assert result["name"] == "Test"
```

### Strategy 3: Mock External Dependencies

Replace external systems with mocks:

```python
@patch('mypackage.api.requests.get')
def test_external_api_call(mock_get):
    """Test function that calls external API."""
    # Arrange
    mock_response = Mock()
    mock_response.json.return_value = {"status": "ok"}
    mock_get.return_value = mock_response

    # Act
    result = fetch_external_data("https://api.example.com")

    # Assert
    assert result["status"] == "ok"
    mock_get.assert_called_once_with("https://api.example.com")
```

---

## Identifying Coverage Gaps

### 1. Use Coverage Reports

```bash
# Generate detailed HTML report
pytest --cov=mypackage --cov-report=html tests/

# Open htmlcov/index.html to see:
# - Red lines: Not covered
# - Green lines: Covered
# - Yellow lines: Partially covered (branch coverage)
```

### 2. Focus on Red Lines

Prioritize testing the most critical uncovered lines first.

### 3. Check Branch Coverage

```bash
# Show branch coverage details
pytest --cov=mypackage --cov-report=term-missing --cov-branch tests/
```

---

## Maintaining High Coverage

### 1. Make Coverage Part of CI/CD

```yaml
# .github/workflows/test.yml
- name: Run tests with coverage
  run: pytest --cov=mypackage --cov-fail-under=80 tests/
```

### 2. Review Coverage in Pull Requests

Use tools like Codecov or Coveralls to track coverage changes in PRs.

### 3. Write Tests First (TDD)

Test-Driven Development naturally leads to high coverage:

1. Write failing test
2. Write minimal code to pass
3. Refactor
4. Result: Every line has a test

### 4. Avoid "Coverage Gaming"

Don't write useless tests just to increase coverage percentage. Focus on meaningful tests that verify behavior.

---

## Practical Example: Achieving 80% Coverage

```python
# Function to test
def calculate_discount(price, customer_type, quantity):
    """Calculate discount based on customer type and quantity."""
    if price <= 0:
        raise ValueError("Price must be positive")

    if customer_type == "premium":
        discount = 0.20
    elif customer_type == "regular":
        discount = 0.10
    else:
        discount = 0.0

    if quantity >= 10:
        discount += 0.05

    final_price = price * (1 - discount)
    return round(final_price, 2)

# Comprehensive test suite (80%+ coverage)
class TestCalculateDiscount:
    """Test discount calculation with full coverage."""

    def test_premium_customer_small_quantity(self):
        """Test premium customer with quantity < 10."""
        assert calculate_discount(100, "premium", 5) == 80.0

    def test_premium_customer_bulk_quantity(self):
        """Test premium customer with quantity >= 10."""
        assert calculate_discount(100, "premium", 10) == 75.0

    def test_regular_customer_small_quantity(self):
        """Test regular customer with quantity < 10."""
        assert calculate_discount(100, "regular", 5) == 90.0

    def test_regular_customer_bulk_quantity(self):
        """Test regular customer with quantity >= 10."""
        assert calculate_discount(100, "regular", 10) == 85.0

    def test_guest_customer_small_quantity(self):
        """Test guest customer with quantity < 10."""
        assert calculate_discount(100, "guest", 5) == 100.0

    def test_guest_customer_bulk_quantity(self):
        """Test guest customer with quantity >= 10."""
        assert calculate_discount(100, "guest", 10) == 95.0

    def test_invalid_price(self):
        """Test error handling for invalid price."""
        with pytest.raises(ValueError, match="Price must be positive"):
            calculate_discount(0, "premium", 5)

    def test_negative_price(self):
        """Test error handling for negative price."""
        with pytest.raises(ValueError, match="Price must be positive"):
            calculate_discount(-10, "premium", 5)

# Result: 100% line coverage, 100% branch coverage
```

---

**For more details**: See `SKILL.md` for complete testing methodology and `pytest-patterns.md` for testing techniques.
