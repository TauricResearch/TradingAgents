import pytest
from datetime import datetime, timezone

from tradingagents.sensing.envelope import Envelope


def _env(text="Apple beats", source_tags=None):
    return Envelope(
        source="polygon_news",
        ingested_ts=datetime.now(timezone.utc).isoformat(),
        external_id="x:1", text=text,
        source_tags=source_tags or {},
        raw_path="p",
    )


@pytest.mark.unit
def test_prompt_includes_watchlist_csv():
    from tradingagents.sensing.prompts import build_salience_prompt
    text = build_salience_prompt(env=_env(), watchlist=["AAPL", "TSLA"], macro_context="")
    assert "AAPL, TSLA" in text


@pytest.mark.unit
def test_prompt_empty_macro_substituted():
    from tradingagents.sensing.prompts import build_salience_prompt
    text = build_salience_prompt(env=_env(), watchlist=[], macro_context="")
    assert "(none)" in text or "may be empty" in text


@pytest.mark.unit
def test_prompt_truncates_text_to_800():
    from tradingagents.sensing.prompts import build_salience_prompt
    long_text = "x" * 5000
    text = build_salience_prompt(env=_env(text=long_text),
                                  watchlist=["AAPL"], macro_context="")
    assert "x" * 800 in text
    assert "x" * 5000 not in text


@pytest.mark.unit
def test_prompt_includes_source_tags_json():
    from tradingagents.sensing.prompts import build_salience_prompt
    env = _env(source_tags={"tickers": ["AAPL"], "category": "earnings"})
    text = build_salience_prompt(env=env, watchlist=[], macro_context="")
    assert '"tickers"' in text and '"AAPL"' in text


@pytest.mark.unit
def test_prompt_documents_anchors():
    from tradingagents.sensing.prompts import build_salience_prompt
    text = build_salience_prompt(env=_env(), watchlist=[], macro_context="")
    assert "0.0-0.3" in text
    assert "0.85-1.0" in text
