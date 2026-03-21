import pytest
from cli.main import extract_content_string

def test_extract_content_string_empty():
    assert extract_content_string(None) is None
    assert extract_content_string("") is None
    assert extract_content_string("   ") is None

def test_extract_content_string_valid_eval():
    assert extract_content_string("[]") is None
    assert extract_content_string("{}") is None
    assert extract_content_string('""') is None

def test_extract_content_string_invalid_eval_valueerror():
    # simulating ValueError in literal_eval
    assert extract_content_string("not_a_valid_python_literal") == "not_a_valid_python_literal"

def test_extract_content_string_invalid_eval_syntaxerror():
    # simulating SyntaxError in literal_eval
    assert extract_content_string("{[}") == "{[}"

def test_extract_content_string_dict():
    assert extract_content_string({"text": "hello"}) == "hello"
    assert extract_content_string({"text": "   "}) is None

def test_extract_content_string_list():
    assert extract_content_string([{"type": "text", "text": "hello"}, " world"]) == "hello world"
