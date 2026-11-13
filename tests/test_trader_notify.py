import logging

import requests

from trader import notify
from trader.ledger import Ledger
from trader.notify import Notifier, Outbox, _chunks, labeled
from trader.settings import Settings

T0 = 1_768_003_800_000  # 2026-01-10 00:10 UTC


class FakeResponse:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} for url https://api.telegram.org/botSECRET/sendMessage",
                response=self,
            )


class FakeSession:
    """Telegram answering each post with ``status``, or with ``statuses`` in turn first."""

    def __init__(self, status=200, statuses=()):
        self.status = status
        self.statuses = list(statuses)
        self.posts = []
        self.taken = []  # the texts of the posts it answered with success

    def post(self, url, json, timeout):
        self.posts.append((url, json))
        status = self.statuses.pop(0) if self.statuses else self.status
        if status < 400:
            self.taken.append(json["text"])
        return FakeResponse(status)


def _settings(tmp_path, token="SECRET", chat_id="42"):
    return Settings(home=tmp_path, telegram_token=token, telegram_chat_id=chat_id)


def test_without_a_bot_nothing_is_sent(tmp_path):
    session = FakeSession()
    assert Notifier(_settings(tmp_path, token=None), session).send("hi") is False
    assert session.posts == []


def test_sends_to_the_chat(tmp_path):
    session = FakeSession()
    assert Notifier(_settings(tmp_path), session).send("hi") is True
    assert session.posts == [
        ("https://api.telegram.org/botSECRET/sendMessage", {"chat_id": "42", "text": "hi"})
    ]


def test_long_text_is_split_at_line_breaks():
    text = "\n".join("x" * 100 for _ in range(100))
    chunks = _chunks(text)
    assert len(chunks) == 3
    assert "".join(chunks) == text
    assert all(len(c) <= 4000 for c in chunks)
    assert all(c.endswith("\n") for c in chunks[:-1])


def test_a_line_over_the_limit_is_cut():
    assert [len(c) for c in _chunks("y" * 9000)] == [4000, 4000, 1000]


def test_a_failed_send_returns_false_without_logging_the_token(tmp_path, caplog):
    with caplog.at_level(logging.ERROR):
        assert Notifier(_settings(tmp_path), FakeSession(status=401)).send("hi") is False
    assert "401" in caplog.text
    assert "SECRET" not in caplog.text


def test_a_labeled_notifier_heads_each_message_with_the_account_once(tmp_path):
    session = FakeSession()
    live = labeled(Notifier(_settings(tmp_path), session), "live")
    assert labeled(live, "live") is live
    assert live.send("运行失败：x") is True
    assert [post["text"] for _, post in session.posts] == ["【live】运行失败：x"]


def test_a_long_labeled_message_carries_the_label_on_its_first_piece(tmp_path):
    session = FakeSession()
    labeled(Notifier(_settings(tmp_path), session), "demo").send("\n".join("x" * 100 for _ in range(100)))
    texts = [post["text"] for _, post in session.posts]
    assert len(texts) == 3 and texts[0].startswith("【demo】xxx")
    assert not any("【" in text for text in texts[1:])


# -- the outbox -------------------------------------------------------------------------


def _outbox(tmp_path, session, now, token="SECRET"):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.initialize(10_000.0, T0)
    notifier = labeled(Notifier(_settings(tmp_path, token=token), session), "demo")
    return Outbox(notifier, ledger, "demo_unsent", lambda: now[0]), ledger


def test_an_outbox_keeps_what_telegram_refused_and_sends_it_first_the_next_time(tmp_path):
    session, now = FakeSession(status=502), [T0]
    box, ledger = _outbox(tmp_path, session, now)
    assert box.send("日报") is False
    now[0] += 3_600_000
    assert box.send("运行失败：x", kind="OKXError") is False
    assert box.holds("OKXError") and not box.holds("ConnectionError")
    assert box.flush() == [] and session.taken == []  # still down: everything stays
    session.status = 200
    assert box.flush() == ["OKXError"]
    assert session.taken == [
        "【demo】日报\n（补发：01-10 00:10 UTC 没发出去）",
        "【demo】运行失败：x\n（补发：01-10 01:10 UTC 没发出去）",
    ]
    assert not box.holds("OKXError") and ledger.get("demo_unsent") == {"messages": [], "dropped": 0}
    assert box.flush() == [] and len(session.taken) == 2
    assert box.send("下一条") is True and session.taken[-1] == "【demo】下一条"


def test_a_flush_stops_where_telegram_fails_again_and_keeps_the_rest_in_order(tmp_path):
    session, now = FakeSession(status=502), [T0]
    box, ledger = _outbox(tmp_path, session, now)
    for text in ("一", "二", "三"):
        box.send(text, kind=text)
    session.statuses = [200, 429]
    assert box.flush() == ["一"]
    assert [m["text"] for m in ledger.get("demo_unsent")["messages"]] == ["二", "三"]


def test_without_a_chat_an_outbox_keeps_nothing(tmp_path):
    session = FakeSession()
    box, ledger = _outbox(tmp_path, session, [T0], token=None)
    assert box.notifier.configured is False
    assert box.send("日报") is False and ledger.get("demo_unsent") is None and session.posts == []
    assert box.flush() == [] and ledger.get("demo_unsent") is None  # nothing kept, nothing written
    assert labeled(Notifier(_settings(tmp_path), session), "demo").configured is True


def test_an_outbox_keeps_the_newest_messages_and_says_how_many_gave_way(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "OUTBOX_LIMIT", 2)
    session, now = FakeSession(status=502), [T0]
    box, ledger = _outbox(tmp_path, session, now)
    for text in ("一", "二", "三"):
        box.send(text)
    assert [m["text"] for m in ledger.get("demo_unsent")["messages"]] == ["二", "三"]
    assert ledger.get("demo_unsent")["dropped"] == 1
    assert box.flush() == [] and ledger.get("demo_unsent")["dropped"] == 1  # the note was refused too
    session.status = 200
    box.flush()
    assert session.taken == [
        "【demo】有 1 条更早的消息当时没发出去，也没留着补发：全文在运行日志里",
        "【demo】二\n（补发：01-10 00:10 UTC 没发出去）",
        "【demo】三\n（补发：01-10 00:10 UTC 没发出去）",
    ]
    assert ledger.get("demo_unsent") == {"messages": [], "dropped": 0}
