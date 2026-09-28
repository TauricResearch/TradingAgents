"""Native per-ticker/date CLI artifacts, shared by prompted and headless runs."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import RLock

from tradingagents.dataflows.symbols import safe_ticker_component


@dataclass(frozen=True)
class RunOutput:
    directory: Path
    reports: Path
    log: Path


def run_directory(config: dict, ticker: str, trade_date: str) -> Path:
    """Use the interactive CLI's results_dir / ticker / analysis-date layout."""
    try:
        canonical = datetime.strptime(trade_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("analysis date must use YYYY-MM-DD") from None
    if canonical != trade_date:
        raise ValueError("analysis date must use YYYY-MM-DD")
    return Path(config["results_dir"]).expanduser() / safe_ticker_component(ticker) / trade_date


def default_export_directory(config: dict, ticker: str) -> Path:
    """The native Save report? prompt's default, separate from incremental logs."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (Path(config["results_dir"]).expanduser() / "reports"
            / f"{safe_ticker_component(ticker)}_{stamp}")


@contextmanager
def persist_run_buffer(buffer, directory: Path, lock: RLock):
    """Persist buffer events immediately, independently of the display mode.

    Logs append and named sections overwrite, as in the original interactive
    CLI. Scope the wrappers: leaving them installed would write a later run's
    messages into every earlier ticker's log. Restore even on Ctrl+C/failure.
    """
    directory.mkdir(parents=True, exist_ok=True)
    output = RunOutput(directory, directory / "reports", directory / "message_tool.log")
    output.reports.mkdir(exist_ok=True)
    output.log.touch(exist_ok=True)
    original_attributes = {
        name: (name in vars(buffer), vars(buffer).get(name))
        for name in ("add_message", "add_tool_call", "update_report_section")
    }
    add_message = buffer.add_message
    add_tool_call = buffer.add_tool_call
    update_report_section = buffer.update_report_section
    last_written = {}

    def append(line: str) -> None:
        # One line per native event, even for multi-line tool arguments.
        with output.log.open("a", encoding="utf-8") as stream:
            stream.write(line.replace("\r", " ").replace("\n", " ") + "\n")

    @wraps(add_message)
    def message(*args, **kwargs):
        with lock:
            result = add_message(*args, **kwargs)
            timestamp, kind, content = buffer.messages[-1]
            append(f"{timestamp} [{kind}] {content}")
            return result

    @wraps(add_tool_call)
    def tool(*args, **kwargs):
        with lock:
            result = add_tool_call(*args, **kwargs)
            timestamp, name, arguments = buffer.tool_calls[-1]
            arguments = ", ".join(f"{key}={value}" for key, value in arguments.items())
            append(f"{timestamp} [Tool Call] {name}({arguments})")
            return result

    @wraps(update_report_section)
    def section(name, content):
        with lock:
            result = update_report_section(name, content)
            if name in buffer.report_sections and name in buffer.REPORT_SECTIONS:
                current = buffer.report_sections[name]
                if current:
                    text = "\n".join(map(str, current)) if isinstance(current, list) else str(current)
                    if text != last_written.get(name):
                        (output.reports / f"{name}.md").write_text(text, encoding="utf-8")
                        last_written[name] = text
            return result

    buffer.add_message = message
    buffer.add_tool_call = tool
    buffer.update_report_section = section
    try:
        yield output
    finally:
        for name, (was_local, value) in original_attributes.items():
            if was_local:
                setattr(buffer, name, value)
            else:
                delattr(buffer, name)
