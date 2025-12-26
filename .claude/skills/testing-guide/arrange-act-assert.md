# Arrange-Act-Assert Pattern Guide

**Purpose**: The AAA pattern is a standard structure for writing clear, maintainable tests.

**When to use**: For all unit and integration tests to ensure consistent, readable test structure.

---

## The AAA Pattern

The Arrange-Act-Assert (AAA) pattern divides tests into three distinct phases:

1. **Arrange**: Set up test data, mock dependencies, configure initial state
2. **Act**: Execute the code under test
3. **Assert**: Verify the expected outcomes

This structure makes tests self-documenting and easy to understand.

---

## Arrange Phase

The Arrange phase prepares everything needed for the test.

### Setting Up Test Data

```python
def test_user_creation():
    """Test user creation with valid data."""
    # Arrange
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "secure_password"
    }

    # Act
    user = create_user(user_data)

    # Assert
    assert user.username == "testuser"
    assert user.email == "test@example.com"
```

### Mocking Dependencies

```python
def test_api_call_with_mock():
    """Test API call with mocked HTTP client."""
    # Arrange
    mock_client = Mock()
    mock_client.get.return_value = {
        "status": "success",
        "data": {"id": 1, "name": "Test"}
    }
    api = APIService(client=mock_client)

    # Act
    result = api.fetch_user(user_id=1)

    # Assert
    assert result["name"] == "Test"
    mock_client.get.assert_called_once_with("/users/1")
```

### Configuring Initial State

```python
def test_shopping_cart_total():
    """Test shopping cart total calculation."""
    # Arrange
    cart = ShoppingCart()
    cart.add_item("Product A", price=10.00, quantity=2)
    cart.add_item("Product B", price=5.00, quantity=3)

    # Act
    total = cart.calculate_total()

    # Assert
    assert total == 35.00
```

---

## Act Phase

The Act phase executes the code under test. Keep this phase minimal - ideally one line.

### Single Action

```python
def test_string_uppercase():
    """Test string conversion to uppercase."""
    # Arrange
    input_string = "hello world"

    # Act
    result = input_string.upper()

    # Assert
    assert result == "HELLO WORLD"
```

### Method Call with Parameters

```python
def test_calculate_discount():
    """Test discount calculation."""
    # Arrange
    calculator = DiscountCalculator()
    original_price = 100.00
    discount_rate = 0.20

    # Act
    final_price = calculator.apply_discount(original_price, discount_rate)

    # Assert
    assert final_price == 80.00
```

### Exception Testing

```python
def test_division_by_zero():
    """Test that division by zero raises error."""
    # Arrange
    calculator = Calculator()

    # Act & Assert (combined for exception testing)
    with pytest.raises(ZeroDivisionError):
        calculator.divide(10, 0)
```

---

## Assert Phase

The Assert phase verifies the expected outcomes.

### Simple Assertions

```python
def test_list_append():
    """Test appending to list."""
    # Arrange
    my_list = [1, 2, 3]

    # Act
    my_list.append(4)

    # Assert
    assert len(my_list) == 4
    assert my_list[-1] == 4
```

### Multiple Assertions

It's acceptable to have multiple assertions that verify different aspects of the outcome:

```python
def test_user_registration():
    """Test user registration creates user correctly."""
    # Arrange
    registration_data = {
        "email": "newuser@example.com",
        "password": "secure123"
    }

    # Act
    user = register_user(registration_data)

    # Assert
    assert user.email == "newuser@example.com"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.id is not None
```

### Asserting Side Effects

```python
def test_log_message_written():
    """Test that log message is written to file."""
    # Arrange
    logger = Logger("test.log")
    message = "Test log message"

    # Act
    logger.write(message)

    # Assert
    with open("test.log") as f:
        content = f.read()
        assert message in content
```

### Asserting Mock Calls

```python
def test_notification_sent():
    """Test that notification is sent to user."""
    # Arrange
    mock_notifier = Mock()
    service = UserService(notifier=mock_notifier)
    user = User(email="test@example.com")

    # Act
    service.notify_user(user, "Welcome message")

    # Assert
    mock_notifier.send.assert_called_once_with(
        to=user.email,
        message="Welcome message"
    )
```

---

## Before and After Examples

### Before: Unclear Test Structure

```python
def test_order_processing():
    """Test order processing (unclear structure)."""
    order = Order()
    order.add_item(Item("Product", 10.00))
    payment = Payment(amount=10.00)
    assert process_order(order, payment) is True
    assert order.status == "completed"
    assert payment.status == "processed"
```

### After: Clear AAA Structure

```python
def test_order_processing():
    """Test order processing with payment."""
    # Arrange
    order = Order()
    order.add_item(Item("Product", 10.00))
    payment = Payment(amount=10.00)

    # Act
    result = process_order(order, payment)

    # Assert
    assert result is True
    assert order.status == "completed"
    assert payment.status == "processed"
```

---

## AAA Pattern with Fixtures

Fixtures can handle the Arrange phase:

```python
@pytest.fixture
def user_with_account():
    """Arrange: Create user with account."""
    user = User(username="testuser")
    account = Account(balance=100.00)
    user.account = account
    return user

def test_withdraw_money(user_with_account):
    """Test withdrawing money from account."""
    # Arrange (done by fixture)
    user = user_with_account
    withdrawal_amount = 25.00

    # Act
    result = user.account.withdraw(withdrawal_amount)

    # Assert
    assert result is True
    assert user.account.balance == 75.00
```

---

## AAA Pattern with Parametrization

Combine AAA with parametrization:

```python
@pytest.mark.parametrize("input_value,expected_output", [
    (0, "zero"),
    (1, "one"),
    (5, "five"),
    (10, "ten"),
])
def test_number_to_word(input_value, expected_output):
    """Test number to word conversion."""
    # Arrange
    converter = NumberConverter()

    # Act
    result = converter.to_word(input_value)

    # Assert
    assert result == expected_output
```

---

## Common Mistakes

### Mistake 1: Mixing Phases

```python
# ❌ Bad: Arrange and Act mixed
def test_bad_structure():
    user = User("test")
    user.age = 25
    result = user.is_adult()
    user.name = "Test User"
    assert result is True
```

```python
# ✅ Good: Clear phases
def test_good_structure():
    # Arrange
    user = User("test")
    user.age = 25
    user.name = "Test User"

    # Act
    result = user.is_adult()

    # Assert
    assert result is True
```

### Mistake 2: Multiple Actions

```python
# ❌ Bad: Multiple actions
def test_multiple_actions():
    # Arrange
    calculator = Calculator()

    # Act
    result1 = calculator.add(2, 3)
    result2 = calculator.multiply(4, 5)

    # Assert
    assert result1 == 5
    assert result2 == 20
```

```python
# ✅ Good: One action per test
def test_addition():
    # Arrange
    calculator = Calculator()

    # Act
    result = calculator.add(2, 3)

    # Assert
    assert result == 5

def test_multiplication():
    # Arrange
    calculator = Calculator()

    # Act
    result = calculator.multiply(4, 5)

    # Assert
    assert result == 20
```

### Mistake 3: Asserting in Arrange

```python
# ❌ Bad: Assertions in arrange phase
def test_with_assertions_in_arrange():
    # Arrange
    user = create_user("test@example.com")
    assert user is not None  # Don't assert here

    # Act
    result = user.login("password")

    # Assert
    assert result is True
```

```python
# ✅ Good: Only assert in assert phase
def test_without_assertions_in_arrange():
    # Arrange
    user = create_user("test@example.com")

    # Act
    result = user.login("password")

    # Assert
    assert user is not None
    assert result is True
```

---

## Benefits of AAA Pattern

1. **Readability**: Anyone can understand what the test does
2. **Maintainability**: Easy to modify any phase independently
3. **Debugging**: Quick to identify where test fails (arrange, act, or assert)
4. **Consistency**: All tests follow same structure
5. **Self-documenting**: Test structure tells the story

---

## AAA Pattern Checklist

Before committing a test, verify:

- [ ] Arrange phase sets up all necessary data and state
- [ ] Act phase has minimal code (ideally one line)
- [ ] Assert phase verifies expected outcomes
- [ ] Phases are clearly separated (with comments or blank lines)
- [ ] Test has descriptive name and docstring
- [ ] No assertions in Arrange phase
- [ ] No setup in Act phase
- [ ] One primary action being tested

---

**For more details**: See `SKILL.md` for complete testing methodology and `test-templates/` for working examples with AAA pattern.
