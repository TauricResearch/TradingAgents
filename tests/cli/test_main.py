import pytest
from cli.main import MessageBuffer, extract_content_string

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


def test_message_buffer_completed_reports_count_tracks_active_sections_only():
    buffer = MessageBuffer()
    buffer.init_for_analysis(["market", "news"])

    buffer.report_sections["market_report"] = "done"
    buffer.report_sections["news_report"] = "done"
    buffer.report_sections["investment_plan"] = "done"
    buffer.agent_status["Market Analyst"] = "completed"
    buffer.agent_status["News Analyst"] = "pending"
    buffer.agent_status["Research Manager"] = "completed"

    assert buffer.get_completed_reports_count() == 2


def test_message_buffer_completed_reports_count_ignores_unknown_section():
    buffer = MessageBuffer()
    buffer.init_for_analysis(["market"])

    buffer.report_sections["market_report"] = "done"
    buffer.report_sections["unexpected_report"] = "done"
    buffer.agent_status["Market Analyst"] = "completed"

    assert buffer.get_completed_reports_count() == 1
