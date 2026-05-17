import pytest

from tradingagents.web.i18n import LANGUAGE_OPTIONS, t


@pytest.mark.unit
def test_web_language_options_default_to_english():
    assert LANGUAGE_OPTIONS[0] == ("English", "English")


@pytest.mark.unit
def test_web_language_options_include_cli_report_languages():
    languages = [key for key, _ in LANGUAGE_OPTIONS]

    assert languages == [
        "English",
        "Chinese",
        "Japanese",
        "Korean",
        "Hindi",
        "Spanish",
        "Portuguese",
        "French",
        "German",
        "Arabic",
        "Russian",
    ]


@pytest.mark.unit
def test_web_i18n_uses_requested_language_and_english_fallback():
    assert t("Chinese", "analysis_setup") == "分析设置"
    assert t("Chinese", "quick_deployment") == "Quick deployment name"
    assert t("Unknown", "analysis_setup") == "Analysis Setup"
