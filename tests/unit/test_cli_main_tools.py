"""Tests for cli.main tool call parsing utility functions."""
import pytest
from cli.main import parse_tool_call

class MockToolCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args

def test_parse_tool_call_dict_with_args():
    tool_call = {"name": "get_stock_price", "args": {"ticker": "AAPL"}}
    name, args = parse_tool_call(tool_call)
    assert name == "get_stock_price"
    assert args == {"ticker": "AAPL"}

def test_parse_tool_call_dict_with_arguments():
    tool_call = {"name": "get_stock_price", "arguments": {"ticker": "AAPL"}}
    name, args = parse_tool_call(tool_call)
    assert name == "get_stock_price"
    assert args == {"ticker": "AAPL"}

def test_parse_tool_call_string_valid_dict():
    tool_call = '{"name": "get_news", "args": {"ticker": "TSLA"}}'
    name, args = parse_tool_call(tool_call)
    assert name == "get_news"
    assert args == {"ticker": "TSLA"}

def test_parse_tool_call_string_value_error():
    # 'unknown_variable' is a valid expression but raises ValueError in literal_eval
    tool_call = 'unknown_variable'
    name, args = parse_tool_call(tool_call)
    assert name == "Unknown Tool"
    assert args == {}

def test_parse_tool_call_string_syntax_error():
    # '{"name": "get_news"' is missing a closing brace, raises SyntaxError
    tool_call = '{"name": "get_news"'
    name, args = parse_tool_call(tool_call)
    assert name == "Unknown Tool"
    assert args == {}

def test_parse_tool_call_string_not_dict():
    # A valid string but doesn't evaluate to a dict
    tool_call = '"just a string"'
    name, args = parse_tool_call(tool_call)
    assert name == "Unknown Tool"
    assert args == {}

def test_parse_tool_call_object():
    tool_call = MockToolCall("get_sentiment", {"ticker": "GOOG"})
    name, args = parse_tool_call(tool_call)
    assert name == "get_sentiment"
    assert args == {"ticker": "GOOG"}
