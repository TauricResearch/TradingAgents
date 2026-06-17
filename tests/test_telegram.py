"""Tests for the Telegram delivery module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from tradingagents.notifications import telegram
from tradingagents.reports.exporter import DecisionSummary


@pytest.mark.unit
class TestTelegramConfig:
    def test_from_env_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert telegram.TelegramConfig.from_env() is None

    def test_from_env_returns_none_when_partial(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        assert telegram.TelegramConfig.from_env() is None

    def test_from_env_returns_config_when_both_set(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        cfg = telegram.TelegramConfig.from_env()
        assert cfg is not None
        assert cfg.bot_token == "abc"
        assert cfg.chat_id == "123"


def _ok_response() -> dict:
    return {"ok": True, "result": {"message_id": 1}}


def _build_decision_file(tmp_path: Path) -> Path:
    p = tmp_path / "decision.md"
    p.write_text(
        "**Rating**: Overweight\n\n"
        "**Executive Summary**: Buy the dip.\n\n"
        "**Price Target**: 77400.0\n\n"
        "**Time Horizon**: 3-6 mesi\n",
        encoding="utf-8",
    )
    return p


@pytest.mark.unit
class TestSendReport:
    def test_skips_when_not_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        decision = _build_decision_file(tmp_path)
        summary = DecisionSummary(rating="Overweight", price_target=77400.0)
        with mock.patch("tradingagents.notifications.telegram._post") as post:
            assert (
                telegram.send_report(
                    "BTC-USD", summary, markdown_path=decision
                )
                is False
            )
            post.assert_not_called()

    def test_sends_message_then_document(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        decision = _build_decision_file(tmp_path)
        summary = DecisionSummary(
            rating="Overweight",
            price_target=77400.0,
            time_horizon="3-6 mesi",
            executive_summary="Buy the dip.",
        )
        with mock.patch(
            "tradingagents.notifications.telegram._post", return_value=_ok_response()
        ) as post:
            assert (
                telegram.send_report(
                    "BTC-USD", summary, markdown_path=decision
                )
                is True
            )
            assert post.call_count == 2
            first_call = post.call_args_list[0]
            assert first_call.args[1] == "sendMessage"
            assert first_call.kwargs["data"]["chat_id"] == "999"
            # MarkdownV2 escapes the ticker: "BTC-USD" -> "BTC\-USD"
            assert "BTC\\-USD" in first_call.kwargs["data"]["text"]
            assert first_call.kwargs["data"]["parse_mode"] == "MarkdownV2"

            second_call = post.call_args_list[1]
            assert second_call.args[1] == "sendDocument"
            assert "Overweight" in second_call.kwargs["data"]["caption"]
            files = second_call.kwargs["files"]
            assert files["document"][0] == "decision.md"

    def test_prefers_pdf_over_markdown(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        md = _build_decision_file(tmp_path)
        pdf = tmp_path / "decision.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%fake\n")
        with mock.patch(
            "tradingagents.notifications.telegram._post", return_value=_ok_response()
        ) as post:
            assert (
                telegram.send_report(
                    "BTC-USD",
                    DecisionSummary(rating="Overweight"),
                    pdf_path=pdf,
                    markdown_path=md,
                )
                is True
            )
        sent_file = post.call_args_list[1].kwargs["files"]["document"]
        assert sent_file[0] == "decision.pdf"

    def test_missing_document_returns_true_after_message(self, monkeypatch, tmp_path):
        """If the message went but no file exists, treat as a soft success."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        with mock.patch(
            "tradingagents.notifications.telegram._post", return_value=_ok_response()
        ) as post:
            assert (
                telegram.send_report(
                    "BTC-USD", DecisionSummary(rating="Overweight")
                )
                is False
            )
            # Only the message call should have been made
            assert post.call_count == 1


@pytest.mark.unit
class TestPostEnvelope:
    def test_raises_on_non_ok_response(self):
        cfg = telegram.TelegramConfig(bot_token="t", chat_id="c")
        bad = mock.MagicMock()
        bad.ok = False
        bad.status_code = 400
        bad.json.return_value = {"ok": False, "description": "bad chat id"}
        with (
            mock.patch("requests.post", return_value=bad),
            pytest.raises(telegram.TelegramError, match="sendMessage failed"),
        ):
            telegram._post(cfg, "sendMessage", data={"chat_id": "c"})

    def test_raises_on_html_response(self):
        cfg = telegram.TelegramConfig(bot_token="t", chat_id="c")
        bad = mock.MagicMock()
        bad.ok = True
        bad.json.side_effect = json.JSONDecodeError("x", "y", 0)
        with (
            mock.patch("requests.post", return_value=bad),
            pytest.raises(telegram.TelegramError, match="non-JSON"),
        ):
            telegram._post(cfg, "sendMessage", data={"chat_id": "c"})


# Characters Telegram's MarkdownV2 parser reserves per
# https://core.telegram.org/bots/api#markdownv2-style. The escape helper
# must backslash-escape every one of these or the Bot API rejects the
# request with "can't parse entities".
_MARKDOWNV2_RESERVED = "_*[]()~`>#+-=|{}.!"


@pytest.mark.unit
class TestEscapeMarkdownV2:
    def test_escapes_every_reserved_character(self):
        for ch in _MARKDOWNV2_RESERVED:
            assert telegram.escape_markdown_v2(ch) == f"\\{ch}", (
                f"MarkdownV2 reserved char {ch!r} must be backslash-escaped"
            )

    def test_escapes_curly_braces(self):
        """Regression: Gemini's review flagged { and } as missing — they're not."""
        assert telegram.escape_markdown_v2("{x}") == "\\{x\\}"
        assert telegram.escape_markdown_v2("a|b") == "a\\|b"
        assert telegram.escape_markdown_v2("a~b") == "a\\~b"

    def test_passes_through_unreserved_text(self):
        assert telegram.escape_markdown_v2("plain text 123") == "plain text 123"
