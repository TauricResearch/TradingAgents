"""Example test file for basic functionality."""

import pytest


def test_placeholder():
    """Placeholder test that always passes."""
    assert True


def test_string_concatenation():
    """Test basic string concatenation."""
    result = "hello" + " " + "world"
    assert result == "hello world"


def test_list_operations():
    """Test basic list operations."""
    numbers = [1, 2, 3, 4, 5]
    assert len(numbers) == 5
    assert sum(numbers) == 15
    assert numbers[0] == 1
    assert numbers[-1] == 5


@pytest.mark.unit
def test_dictionary_access():
    """Test dictionary key access."""
    data = {"name": "test", "value": 42}
    assert data["name"] == "test"
    assert data["value"] == 42
