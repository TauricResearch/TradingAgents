"""F2 regression probes use synthetic canaries only; no provider calls."""

import pytest

from tradingagents.runapi.persist import publish_run
from tradingagents.runapi.redact import Redactor


@pytest.mark.parametrize("text", [
    "OPENAI_API_KEY=CANARY_REVIEW_SECRET_1234567890",
    '"DEEPSEEK_API_KEY": "CANARY_REVIEW_SECRET_1234567890"',
    "CLIENT_SECRET='CANARY_REVIEW_SECRET_1234567890 with spaces'",
    'OPENAI_API_KEY="CANARY_REVIEW_SECRET_1234567890\nsecond-line"',
    "Authorization: Bearer CANARY_REVIEW_SECRET_1234567890",
    "Authorization: Basic CANARY_REVIEW_SECRET_1234567890",
    "Bearer CANARY_REVIEW_SECRET_1234567890",
])
def test_credential_text_and_diagnostics(text):
    redactor = Redactor()
    for result in (redactor.scrub(text), redactor.diagnostic(ValueError(text))):
        assert "CANARY_REVIEW_SECRET_1234567890" not in result
        assert "second-line" not in result
        assert "with spaces" not in result
        assert "[REDACTED]" in result


def test_configured_secret_without_label(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "synthetic-configured-canary-987654")
    redactor = Redactor()
    assert redactor.scrub("failure: synthetic-configured-canary-987654") == "failure: [REDACTED]"
    assert redactor.scrub({"OPENAI_API_KEY": "hidden", "nested": ["synthetic-configured-canary-987654"]}) == {
        "OPENAI_API_KEY": "[REDACTED]", "nested": ["[REDACTED]"]}
    assert redactor.scrub("No current position in AAPL; cash unknown.") == "No current position in AAPL; cash unknown."


def test_published_artifacts_are_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-artifact-canary-123456")
    payload = "OPENAI_API_KEY=CANARY_REVIEW_SECRET_1234567890; synthetic-artifact-canary-123456"

    class Events:
        def emit(self, *args):
            pass

        def write_to(self, path):
            path.write_text("{}\n", encoding="utf-8")
            return True

    artifacts = publish_run(tmp_path, "AAPL", "f2-canary", payload, payload,
                            {"diagnostic": payload}, Events(), Redactor(),
                            state_data={"message": payload}, message_log=payload)
    files = [p for p in artifacts.run_dir.rglob("*") if p.is_file()]
    assert len(files) == 6
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert "CANARY_REVIEW_SECRET_1234567890" not in content
        assert "synthetic-artifact-canary-123456" not in content
