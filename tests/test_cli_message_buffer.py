from cli.main import MessageBuffer, RunLogger


def test_message_buffer_logging_does_not_stack_between_runs(tmp_path):
    base = tmp_path / "message-buffer"
    report1 = base / "reports1"
    report2 = base / "reports2"
    report1.mkdir(parents=True)
    report2.mkdir(parents=True)
    log1 = base / "run1.log"
    log2 = base / "run2.log"

    b1 = MessageBuffer(logger=RunLogger(log1, report1))
    b1.add_message("System", "first")

    b2 = MessageBuffer(logger=RunLogger(log2, report2))
    b2.add_message("System", "second")

    assert "first" in log1.read_text(encoding="utf-8")
    assert "second" not in log1.read_text(encoding="utf-8")
    assert "second" in log2.read_text(encoding="utf-8")
