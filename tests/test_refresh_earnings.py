import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import refresh_earnings as earnings

SYMBOLS = ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _confirmed_page(symbol: str) -> str:
    return f"{symbol}'s next earnings date is CONFIRMED for Friday 12/11/2026"


def test_refresh_requires_exact_watchlist_and_confirmed_future_dates():
    pages = {symbol: _confirmed_page(symbol) for symbol in SYMBOLS}

    payload = earnings.refresh_earnings(SYMBOLS, pages.__getitem__, NOW)

    assert payload == {
        "source": "Wall Street Horizon",
        "retrieved_at": "2026-08-11T12:00:00+00:00",
        "symbols": dict.fromkeys(SYMBOLS, "2026-12-11"),
    }


@pytest.mark.parametrize(
    "page",
    (
        "estimated 12/11/2026",
        "CONFIRMED for Thursday 01/01/2026",
        "CONFIRMED for Friday 12/11/2026; CONFIRMED for Monday 12/14/2026",
    ),
)
def test_refresh_rejects_unconfirmed_past_or_ambiguous_date(page):
    with pytest.raises(ValueError, match="confirmed future earnings date"):
        earnings.refresh_earnings(("AAPL",), lambda symbol: page, NOW)


@pytest.mark.parametrize("symbols", (("AAPL", "AAPL"), ("AAPL", "IBM")))
def test_refresh_rejects_duplicate_or_unsupported_symbols(symbols):
    with pytest.raises(ValueError, match="supported exactly once"):
        earnings.refresh_earnings(symbols, _confirmed_page, NOW)


def test_failed_refresh_does_not_replace_existing_cache(tmp_path):
    target = tmp_path / "earnings.json"
    target.write_text('{"old": true}', encoding="utf-8")

    with pytest.raises(OSError, match="network"):
        earnings.write_earnings_cache(
            target,
            ("AAPL",),
            lambda symbol: (_ for _ in ()).throw(OSError("network")),
            NOW,
        )

    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert list(tmp_path.iterdir()) == [target]


def test_failed_atomic_replace_preserves_cache_and_removes_temporary_file(
    tmp_path, monkeypatch
):
    target = tmp_path / "earnings.json"
    target.write_text('{"old": true}', encoding="utf-8")

    def fail_replace(source, destination):
        assert Path(source).parent == target.parent
        assert Path(destination) == target
        raise OSError("replace failed")

    monkeypatch.setattr(earnings.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        earnings.write_earnings_cache(target, ("AAPL",), _confirmed_page, NOW)

    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert list(tmp_path.iterdir()) == [target]


def test_fetch_page_uses_supported_url_and_fixed_user_agent():
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"earnings page"

    def open_url(request, timeout):
        seen["url"] = request.full_url
        seen["user_agent"] = request.get_header("User-agent")
        seen["timeout"] = timeout
        return Response()

    assert earnings.fetch_page("AAPL", open_url=open_url) == "earnings page"
    assert seen == {
        "url": earnings.WALL_STREET_HORIZON_PAGES["AAPL"],
        "user_agent": earnings.USER_AGENT,
        "timeout": 30,
    }


def test_cli_reads_env_backed_config_and_atomically_writes_exact_watchlist(
    tmp_path, monkeypatch, capsys
):
    target = tmp_path / "cache" / "earnings.json"
    monkeypatch.setattr(
        earnings,
        "DEFAULT_CONFIG",
        {
            "watchlist": "aapl, msft,nvda,amzn,meta,goog,tsla",
            "options_earnings_path": str(target),
        },
    )

    earnings.main(fetch=_confirmed_page, now=NOW)

    assert json.loads(target.read_text(encoding="utf-8"))["symbols"] == dict.fromkeys(
        SYMBOLS, "2026-12-11"
    )
    assert capsys.readouterr().out.strip() == str(target)


def test_cli_rejects_non_seven_symbol_watchlist_without_replacing_cache(tmp_path, monkeypatch):
    target = tmp_path / "earnings.json"
    target.write_text('{"old": true}', encoding="utf-8")
    monkeypatch.setattr(
        earnings,
        "DEFAULT_CONFIG",
        {
            "watchlist": "AAPL,MSFT,NVDA,AMZN,META,GOOG",
            "options_earnings_path": str(target),
        },
    )

    with pytest.raises(ValueError, match="exactly 7 unique symbols"):
        earnings.main(fetch=_confirmed_page, now=NOW)

    assert target.read_text(encoding="utf-8") == '{"old": true}'


def test_direct_script_invocation_reaches_configuration_validation_without_fetching():
    environment = dict(os.environ, TRADINGAGENTS_WATCHLIST="")

    result = subprocess.run(
        [sys.executable, "scripts/refresh_earnings.py"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "watchlist must contain exactly 7 unique symbols" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
