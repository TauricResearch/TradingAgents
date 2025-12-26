# Pytest Patterns Guide

**Purpose**: Comprehensive guide to pytest patterns including fixtures, mocking, and parametrization.

**When to use**: When writing tests with pytest, creating reusable test components, or testing with multiple scenarios.

---

## Fixtures

Pytest fixtures are functions that provide reusable test setup and teardown. They enable dependency injection for tests and promote DRY (Don't Repeat Yourself) principles.

### Basic Fixture Pattern

```python
import pytest

@pytest.fixture
def sample_data():
    """Provide sample data for tests."""
    return {"name": "Test User", "email": "test@example.com"}

def test_user_data(sample_data):
    """Test uses fixture via function parameter."""
    assert sample_data["name"] == "Test User"
    assert "email" in sample_data
```

### Fixture Scopes

Fixtures can have different scopes to control when they're created and destroyed:

- **function** (default): Created/destroyed for each test function
- **class**: Created once per test class
- **module**: Created once per test module
- **session**: Created once per test session

```python
@pytest.fixture(scope="function")
def temp_file():
    """Create temporary file for each test."""
    file = Path("temp.txt")
    file.write_text("test data")
    yield file
    file.unlink()  # Cleanup after test

@pytest.fixture(scope="module")
def database_connection():
    """Shared database connection for all tests in module."""
    conn = create_connection("test.db")
    yield conn
    conn.close()

@pytest.fixture(scope="session")
def test_config():
    """Global test configuration for entire test session."""
    config = load_config("test_config.yaml")
    return config
```

### Autouse Fixtures

Fixtures can run automatically for all tests without explicit parameters:

```python
@pytest.fixture(autouse=True)
def reset_state():
    """Automatically reset state before each test."""
    global_state.clear()
    yield
    global_state.clear()  # Cleanup after test

def test_operation():
    """This test automatically uses reset_state fixture."""
    assert len(global_state) == 0
    global_state.add("item")
    assert len(global_state) == 1
```

### Fixture Composition

Fixtures can depend on other fixtures:

```python
@pytest.fixture
def database():
    """Create test database."""
    db = Database(":memory:")
    db.create_tables()
    return db

@pytest.fixture
def user_repository(database):
    """Create user repository with database."""
    return UserRepository(database)

@pytest.fixture
def authenticated_user(user_repository):
    """Create and authenticate a test user."""
    user = user_repository.create("test@example.com", "password")
    token = user_repository.authenticate(user.id)
    return user, token

def test_user_operations(authenticated_user):
    """Test uses composed fixture."""
    user, token = authenticated_user
    assert user.email == "test@example.com"
    assert token is not None
```

---

## Mocking

Mocking allows you to replace real objects with test doubles that simulate behavior. This is essential for isolating units under test and avoiding external dependencies.

### Basic Mock Pattern

```python
from unittest.mock import Mock, patch

def test_api_call_with_mock():
    """Test API call using mock object."""
    # Arrange
    mock_client = Mock()
    mock_client.get.return_value = {"status": "success"}

    # Act
    result = process_api_response(mock_client)

    # Assert
    mock_client.get.assert_called_once()
    assert result["status"] == "success"
```

### Patching Functions

Use `@patch` decorator to replace functions during testing:

```python
@patch('mymodule.external_api_call')
def test_function_with_patch(mock_api):
    """Test function that calls external API."""
    # Arrange
    mock_api.return_value = {"data": "test"}

    # Act
    result = my_function_that_calls_api()

    # Assert
    mock_api.assert_called_once_with(expected_param="value")
    assert result == "processed: test"
```

### Mock Return Values and Side Effects

Control mock behavior with `return_value` and `side_effect`:

```python
def test_mock_return_value():
    """Test mock with simple return value."""
    mock_obj = Mock()
    mock_obj.method.return_value = 42

    assert mock_obj.method() == 42
    assert mock_obj.method(any_arg="ignored") == 42

def test_mock_side_effect():
    """Test mock with side effects (multiple returns or exceptions)."""
    mock_obj = Mock()

    # Return different values on successive calls
    mock_obj.method.side_effect = [1, 2, 3]
    assert mock_obj.method() == 1
    assert mock_obj.method() == 2
    assert mock_obj.method() == 3

    # Raise exception
    mock_obj.error_method.side_effect = ValueError("Test error")
    with pytest.raises(ValueError, match="Test error"):
        mock_obj.error_method()
```

### Mock File Operations

Use `mock_open` for file I/O testing:

```python
from unittest.mock import mock_open

@patch('builtins.open', mock_open(read_data='file content'))
def test_read_file():
    """Test function that reads file."""
    content = read_config_file("config.txt")
    assert content == "file content"

@patch('builtins.open', mock_open())
def test_write_file(mock_file):
    """Test function that writes file."""
    write_log("test.log", "log message")

    mock_file.assert_called_once_with("test.log", "w")
    handle = mock_file()
    handle.write.assert_called_once_with("log message")
```

### Asserting Mock Calls

Verify how mocks were called:

```python
def test_mock_assertions():
    """Test various mock assertion patterns."""
    mock_obj = Mock()

    # Call mock multiple times
    mock_obj.method(1, 2)
    mock_obj.method(3, 4, key="value")
    mock_obj.other_method()

    # Assertions
    mock_obj.method.assert_called()  # Called at least once
    mock_obj.method.assert_called_with(3, 4, key="value")  # Last call
    assert mock_obj.method.call_count == 2

    # Check all calls
    assert mock_obj.method.call_args_list == [
        ((1, 2), {}),
        ((3, 4), {"key": "value"})
    ]
```

---

## Parametrization

Parametrization allows running the same test with different input values, reducing code duplication and improving test coverage.

### Basic Parametrization

```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
    (5, 10),
])
def test_double(input, expected):
    """Test doubling function with multiple inputs."""
    assert double(input) == expected
```

### Named Test Cases

Use `ids` parameter to give test cases descriptive names:

```python
@pytest.mark.parametrize("email,valid", [
    ("user@example.com", True),
    ("invalid.email", False),
    ("@example.com", False),
    ("user@", False),
], ids=["valid_email", "missing_at", "missing_local", "missing_domain"])
def test_email_validation(email, valid):
    """Test email validation with named test cases."""
    assert is_valid_email(email) == valid
```

### Multiple Parameters

Parametrize multiple arguments independently:

```python
@pytest.mark.parametrize("x", [1, 2, 3])
@pytest.mark.parametrize("y", [10, 20])
def test_addition(x, y):
    """Test runs 6 times (3 * 2 combinations)."""
    result = x + y
    assert result > x
    assert result > y
```

### Complex Parametrization

Use dictionaries or objects for complex test cases:

```python
@pytest.mark.parametrize("test_case", [
    {
        "input": {"username": "admin", "password": "secret"},
        "expected_status": 200,
        "expected_role": "admin"
    },
    {
        "input": {"username": "user", "password": "pass"},
        "expected_status": 200,
        "expected_role": "user"
    },
    {
        "input": {"username": "invalid", "password": "wrong"},
        "expected_status": 401,
        "expected_role": None
    },
], ids=["admin_login", "user_login", "invalid_login"])
def test_authentication(test_case):
    """Test authentication with complex scenarios."""
    response = authenticate(test_case["input"])
    assert response.status_code == test_case["expected_status"]
    if test_case["expected_role"]:
        assert response.user.role == test_case["expected_role"]
```

### Parametrization with Fixtures

Combine parametrization with fixtures for powerful test scenarios:

```python
@pytest.fixture
def api_client():
    """Create API client for tests."""
    client = APIClient("http://test.example.com")
    yield client
    client.close()

@pytest.mark.parametrize("endpoint,expected_fields", [
    ("/users", ["id", "name", "email"]),
    ("/posts", ["id", "title", "content"]),
    ("/comments", ["id", "text", "author"]),
])
def test_api_endpoints(api_client, endpoint, expected_fields):
    """Test multiple API endpoints with same client fixture."""
    response = api_client.get(endpoint)
    assert response.status_code == 200
    data = response.json()
    for field in expected_fields:
        assert field in data[0]
```

### Exception Testing with Parametrization

Test multiple error conditions:

```python
@pytest.mark.parametrize("invalid_input,error_type,error_message", [
    (None, TypeError, "Input cannot be None"),
    ("", ValueError, "Input cannot be empty"),
    (-1, ValueError, "Input must be positive"),
    (0, ValueError, "Input must be positive"),
], ids=["none_input", "empty_input", "negative_input", "zero_input"])
def test_validation_errors(invalid_input, error_type, error_message):
    """Test validation raises appropriate errors."""
    with pytest.raises(error_type, match=error_message):
        validate_input(invalid_input)
```

---

## Best Practices

### Combine Patterns Effectively

```python
@pytest.fixture
def mock_database():
    """Mock database for testing."""
    db = Mock()
    db.query.return_value = [{"id": 1, "name": "Test"}]
    return db

@pytest.mark.parametrize("user_id,expected_name", [
    (1, "Test"),
    (2, None),
])
def test_user_lookup(mock_database, user_id, expected_name):
    """Combine fixture, mock, and parametrization."""
    # Arrange
    if user_id == 2:
        mock_database.query.return_value = []

    # Act
    user = find_user(mock_database, user_id)

    # Assert
    if expected_name:
        assert user.name == expected_name
    else:
        assert user is None
```

### Keep Tests Focused

Each test should verify one specific behavior. Use descriptive names and clear assertions.

### Use Fixtures for Setup

Extract common setup logic into fixtures rather than repeating code in each test.

### Parametrize Similar Tests

If you find yourself copying a test with minor variations, use parametrization instead.

---

**For more details**: See `SKILL.md` for complete testing methodology and `test-templates/` for working examples.
