"""What's new reaches the person at a terminal: a newer release and Tauric's notices.

The check runs at most daily in a background thread that only writes a cache; the
notice shown is read from that cache, so a run never waits on the network, and
unattended runs contact no server at all.
"""

import io
import json
import os
from datetime import date
from types import SimpleNamespace
from unittest import mock

import pytest
from packaging.version import Version
from rich.console import Console

import cli.selections as cli_selections
import cli.updates as updates


class _Tty(io.StringIO):
    def isatty(self):
        return True


# --- who sees it -----------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("stdin_tty, stdout_tty, ci, opt_out, expected", [
    (True, True, None, None, True),
    (False, True, None, None, False),
    (True, False, None, None, False),
    (True, True, "true", None, False),
    (True, True, None, "1", False),
])
def test_only_a_person_at_a_terminal_is_told(monkeypatch, stdin_tty, stdout_tty, ci, opt_out, expected):
    monkeypatch.setattr("sys.stdin", _Tty() if stdin_tty else io.StringIO())
    monkeypatch.setattr("sys.stdout", _Tty() if stdout_tty else io.StringIO())
    for name, value in (("CI", ci), ("TRADINGAGENTS_NO_UPDATE_CHECK", opt_out)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert updates.enabled() is expected


ENV = {
    "TRADINGAGENTS_LLM_PROVIDER": "openai",
    "TRADINGAGENTS_DEEP_THINK_LLM": "gpt-6-sol",
    "TRADINGAGENTS_QUICK_THINK_LLM": "gpt-6-luna",
    "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
    "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
}


@pytest.mark.unit
def test_an_unattended_run_contacts_no_server(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO())      # no terminal
    calls = []
    monkeypatch.setattr(updates.requests, "get", lambda *a, **k: calls.append(a))
    started = []
    monkeypatch.setattr(updates.threading, "Thread", lambda *a, **k: started.append(1))
    with mock.patch.dict(os.environ, ENV, clear=False), \
         mock.patch.object(cli_selections, "ensure_api_key"):
        cli_selections.get_user_selections({"ticker": "AAPL", "date": "2026-09-01", "analysts": "market"})
    assert calls == [] and started == []


# --- what it says -----------------------------------------------------------------

LATEST = {"version": "0.7.0", "url": "https://github.com/TauricResearch/TradingAgents/releases/tag/v0.7.0",
          "summary": "Update notices and a ChatGPT plan provider."}


@pytest.mark.unit
@pytest.mark.parametrize("running, shown", [
    ("0.6.0", True), ("0.7.0.dev0", True),     # a development build of the release is older than it
    ("0.7.0", False), ("0.8.0.dev0", False), ("not-a-version", False),
])
def test_a_newer_release_is_announced_once_in_the_notice(running, shown):
    lines = updates.messages({"latest": LATEST}, running=running, upgrade=lambda: None)
    assert any("0.7.0 is available" in line for line in lines) is shown
    if shown:
        text = "\n".join(lines)
        assert f"you have {running}" in text and LATEST["url"] in text and LATEST["summary"] in text


@pytest.mark.unit
def test_the_notice_names_the_upgrade_command():
    lines = updates.messages({"latest": LATEST}, running="0.6.0", upgrade=lambda: "git -C /src pull && pip install /src")
    assert "Upgrade: git -C /src pull && pip install /src" in "\n".join(lines)


@pytest.mark.unit
def test_remote_text_cannot_style_or_break_the_terminal():
    body = "[bold red]Grab it[/bold red] now\x1b[2J with `--html`, a very long line " + "x" * 400 + "\n\nSecond paragraph."
    summary = updates.summary_of(body)
    assert "\n" not in summary and "Second paragraph" not in summary and len(summary) <= 160
    lines = updates.messages({"latest": {**LATEST, "summary": summary}}, running="0.6.0", upgrade=lambda: None)
    shown = "\n".join(lines)
    assert "[bold red]Grab it" in shown and "\x1b" not in shown   # shown as plain text, controls stripped


@pytest.mark.unit
def test_notices_reach_only_the_versions_they_name():
    cache = {"notices": [
        {"id": "a", "message": "For everyone", "url": None},
        {"id": "b", "message": "Old installs: news is fixed", "max_version": "0.6.0"},
        {"id": "c", "message": "New installs only", "min_version": "0.7.0"},
        {"id": "d", "message": "Expired", "expires": "2020-01-01"},
        {"id": "e", "message": "[link=x]markup[/link]"},
        "a bare string is not a notice",
    ]}
    text = "\n".join(updates.messages(cache, running="0.6.0", upgrade=lambda: None))
    assert "For everyone" in text and "Old installs" in text
    assert "New installs only" not in text and "Expired" not in text
    assert "[link=x]markup[/link]" in text and "bare string" not in text


@pytest.mark.unit
def test_a_notice_shows_through_its_bounds_and_date_and_hides_when_they_cannot_be_read():
    today = date(2026, 10, 16)
    applies = lambda **notice: updates._applies(notice, Version("0.7.0"), today)  # noqa: E731
    assert applies(min_version="0.7.0", max_version="0.7.0", expires="2026-10-16")
    assert applies(expires=None) and applies(min_version=None, max_version=None)
    assert not applies(expires="2026-10-15") and not applies(min_version="0.7.1") and not applies(max_version="0.6.9")
    for unreadable in ("", "seven", [], False):
        assert not applies(min_version=unreadable) and not applies(max_version=unreadable)
    for unreadable in ("", "2026-10-16junk", "20261020", "2026-W42-5", "2026-10-16T23:00-08:00", 20261016):
        assert not applies(expires=unreadable)
    assert not updates._applies({"min_version": "0.7.0"}, Version("0.7.0.dev0"), today)


@pytest.mark.unit
def test_a_notice_is_shown_as_plain_text_with_only_a_web_link():
    cache = {"notices": [
        {"id": "a", "message": ":warning: [b]x[/b] \u202eev\u200bil", "url": "https://tauric.ai/a"},
        {"id": "b", "message": "Local link", "url": "file:///etc/passwd"},
        {"id": "e", "message": "Malformed link", "url": "https://[docs"},
        {"id": "c", "message": {"not": "text"}},
        {"id": "d", "message": "\x1b\x07"},
    ]}
    assert updates.messages(cache, running="0.7.0") == [":warning: [b]x[/b] evil https://tauric.ai/a", "Local link",
                                                         "Malformed link https://[docs"]
    console = Console(record=True, width=120, color_system=None)
    with mock.patch.object(updates, "read_cache", lambda: cache), mock.patch("tradingagents.__version__", "0.7.0"):
        updates.show(console)
    assert ":warning: [b]x[/b] evil" in console.export_text()


@pytest.mark.unit
def test_notices_are_read_from_their_own_key():
    # Notices have their own key, so ``announcements`` stays a list of strings.
    payload = {"announcements": ["Plain text for older clients"],
               "notices": [{"id": "x", "message": "Targeted", "max_version": "0.6.0"}]}
    assert updates.parse_notices(payload) == payload["notices"]
    assert updates.parse_notices({"announcements": ["old shape only"]}) is None
    assert updates.parse_notices({"notices": []}) == []


# --- how it is checked ---------------------------------------------------------------

@pytest.mark.unit
def test_a_check_is_due_once_a_day():
    now = 1_000_000.0
    assert updates.due({}, now)
    assert not updates.due({"checked_at": now - 3600}, now)
    assert updates.due({"checked_at": now - 25 * 3600}, now)


def _response(payload, status=200):
    return SimpleNamespace(status_code=status, ok=status < 400, json=lambda: payload)


@pytest.mark.unit
def test_a_check_records_the_latest_release_and_notices(tmp_path, monkeypatch):
    cache_file = tmp_path / "update_check.json"
    monkeypatch.setattr(updates, "CACHE", cache_file)

    def get(url, timeout):
        assert timeout <= 3
        if "api.github.com" in url:
            return _response({"tag_name": "v0.7.0", "html_url": LATEST["url"],
                              "body": "Update notices and a ChatGPT plan provider.\n\n## Added"})
        return _response({"announcements": ["old"], "notices": [{"id": "n", "message": "hi"}]})

    monkeypatch.setattr(updates.requests, "get", get)
    updates.refresh(now=5000.0)
    cache = json.loads(cache_file.read_text())
    assert cache["checked_at"] == 5000.0
    assert cache["latest"] == {"version": "0.7.0", "url": LATEST["url"], "summary": LATEST["summary"]}
    assert cache["notices"] == [{"id": "n", "message": "hi"}]


@pytest.mark.unit
def test_a_failed_check_keeps_what_was_known_and_waits_a_day(tmp_path, monkeypatch, capsys):
    cache_file = tmp_path / "update_check.json"
    cache_file.write_text(json.dumps({"checked_at": 1.0, "latest": LATEST, "notices": []}))
    monkeypatch.setattr(updates, "CACHE", cache_file)

    def get(url, timeout):
        raise updates.requests.ConnectionError("offline")

    monkeypatch.setattr(updates.requests, "get", get)
    updates.refresh(now=9000.0)                          # never raises
    cache = json.loads(cache_file.read_text())
    assert cache["checked_at"] == 9000.0 and cache["latest"] == LATEST
    assert capsys.readouterr() == ("", "")               # the check never prints


@pytest.mark.unit
def test_only_a_notices_list_replaces_the_known_notices(tmp_path, monkeypatch):
    cache_file = tmp_path / "update_check.json"
    known = [{"id": "n", "message": "hi"}]
    cache_file.write_text(json.dumps({"checked_at": 1.0, "notices": known}))
    monkeypatch.setattr(updates, "CACHE", cache_file)
    for answer in (_response({"detail": "Not Found"}, 404), _response({"error": "portal"}), _response(["x"])):
        monkeypatch.setattr(updates.requests, "get", lambda url, timeout, answer=answer: answer)
        updates.refresh(now=9000.0)
        assert json.loads(cache_file.read_text())["notices"] == known
    monkeypatch.setattr(updates.requests, "get", lambda url, timeout: _response({"announcements": [], "notices": []}))
    updates.refresh(now=99000.0)
    assert json.loads(cache_file.read_text())["notices"] == []


@pytest.mark.unit
def test_an_unreadable_cache_is_no_news(tmp_path, monkeypatch):
    cache_file = tmp_path / "update_check.json"
    cache_file.write_text("{not json")
    monkeypatch.setattr(updates, "CACHE", cache_file)
    assert updates.read_cache() == {}


# --- the upgrade command for how it was installed ----------------------------------

def _dist(direct=None, installer="pip"):
    files = {"direct_url.json": json.dumps(direct) if direct else None, "INSTALLER": installer}
    return SimpleNamespace(read_text=lambda name: files.get(name))


@pytest.mark.unit
def test_the_upgrade_command_follows_the_install(tmp_path, monkeypatch):
    clone = tmp_path / "TradingAgents"
    (clone / ".git").mkdir(parents=True)
    monkeypatch.delenv("TRADINGAGENTS_IN_DOCKER", raising=False)
    monkeypatch.setattr(updates.sys, "executable", "/venv/bin/python")
    url = clone.as_uri()

    editable = updates.upgrade_command(_dist({"url": url, "dir_info": {"editable": True}}))
    assert editable == f"git -C {clone} pull && /venv/bin/python -m pip install -e {clone}"
    local = updates.upgrade_command(_dist({"url": url, "dir_info": {}}, installer="uv"))
    assert local == f"git -C {clone} pull && uv pip install --python /venv/bin/python {clone}"
    vcs = updates.upgrade_command(_dist({"url": "https://github.com/TauricResearch/TradingAgents.git",
                                         "vcs_info": {"vcs": "git", "commit_id": "abc"}}))
    assert vcs == "/venv/bin/python -m pip install -U git+https://github.com/TauricResearch/TradingAgents.git"


@pytest.mark.unit
def test_no_command_is_guessed_without_a_clone(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_IN_DOCKER", raising=False)
    gone = (tmp_path / "deleted-clone").as_uri()
    assert updates.upgrade_command(_dist({"url": gone, "dir_info": {}})) is None
    assert updates.upgrade_command(_dist(None)) is None
    monkeypatch.setenv("TRADINGAGENTS_IN_DOCKER", "1")
    assert updates.upgrade_command(_dist(None)) == "git pull && docker compose build (on the host)"


@pytest.mark.unit
def test_whats_new_never_waits_for_the_person(tmp_path, monkeypatch):
    cache_file = tmp_path / "update_check.json"
    cache_file.write_text(json.dumps({"latest": LATEST, "notices": [{"id": "x", "message": "Notice"}]}))
    monkeypatch.setattr(updates, "CACHE", cache_file)
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("asked for input")))
    from rich.console import Console
    out = Console(file=io.StringIO(), width=200)
    updates.show(out)
    assert "Notice" in out.file.getvalue()


@pytest.mark.unit
@pytest.mark.parametrize("stored", [
    {"latest": "x"}, {"latest": ["0.9.0"]}, {"notices": 5}, {"notices": {"id": "x"}}, {"checked_at": "today"}, [],
])
def test_a_cache_of_the_wrong_shape_is_no_news(tmp_path, monkeypatch, stored):
    cache_file = tmp_path / "update_check.json"
    cache_file.write_text(json.dumps(stored))
    monkeypatch.setattr(updates, "CACHE", cache_file)
    assert updates.messages(updates.read_cache(), running="0.6.0", upgrade=lambda: None) == []
    assert updates.due(updates.read_cache(), 1_000_000.0)


@pytest.mark.unit
def test_a_check_dated_in_the_future_is_due():
    assert updates.due({"checked_at": 2_000_000.0}, 1_000_000.0)


@pytest.mark.unit
def test_a_notice_with_an_unreadable_expiry_is_not_shown():
    cache = {"notices": [{"message": "Bad date", "expires": "next week"},
                         {"message": "Number", "expires": 20991231},
                         {"message": "Timestamp", "expires": "2999-01-01T00:00:00Z"},
                         {"message": "A date", "expires": "2999-01-01"}]}
    text = "\n".join(updates.messages(cache, running="0.6.0", upgrade=lambda: None))
    assert "Bad date" not in text and "Number" not in text and "Timestamp" not in text and "A date" in text


@pytest.mark.unit
def test_remote_text_cannot_carry_c1_or_direction_controls():
    lines = updates.messages({"notices": [{"message": "A\x9b2Jb‮evil"}]}, running="0.6.0", upgrade=lambda: None)
    assert lines == ["A 2Jbevil"]   # the C1 control reads as a space, the override is dropped


@pytest.mark.unit
def test_a_uv_git_install_is_upgraded_with_uv(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_IN_DOCKER", raising=False)
    monkeypatch.setattr(updates.sys, "executable", "/venv/bin/python")
    vcs = updates.upgrade_command(_dist({"url": "https://github.com/TauricResearch/TradingAgents.git",
                                         "vcs_info": {"vcs": "git"}}, installer="uv"))
    assert vcs == "uv pip install --python /venv/bin/python -U git+https://github.com/TauricResearch/TradingAgents.git"


@pytest.mark.unit
def test_no_command_is_offered_on_windows(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_IN_DOCKER", raising=False)
    monkeypatch.setattr(updates.os, "name", "nt")
    assert updates.upgrade_command(_dist({"url": "https://github.com/TauricResearch/TradingAgents.git",
                                          "vcs_info": {"vcs": "git"}})) is None


@pytest.mark.unit
def test_the_upgrade_command_is_worked_out_only_for_a_newer_release():
    asked = []
    updates.messages({"latest": LATEST}, running=LATEST["version"], upgrade=lambda: asked.append(1))
    assert asked == []
