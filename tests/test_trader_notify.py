import logging

import requests

from trader.notify import Notifier, _chunks, labeled
from trader.settings import Settings


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
    def __init__(self, status=200):
        self.status = status
        self.posts = []

    def post(self, url, json, timeout):
        self.posts.append((url, json))
        return FakeResponse(self.status)


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
