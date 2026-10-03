"""Coordinate shell report generation by docs root, date, deep model, and ticker.

Uses OS advisory locks on macOS/Linux; persistent lock files are intentional.
Removing a lock file could let two processes lock different inodes for one key.
"""

import argparse
import fcntl
import hashlib
import math
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli.report_fields import extract_price_target  # noqa: E402


def report_prefix(date, model):
    slug = model.strip().replace("/", "-").replace(":", "-").replace(".", "-")
    return date.replace("-", "") + "_" + slug + "_"


def report_exists(reports, ticker, prefix):
    directory = reports / ticker
    if not directory.is_dir():
        return False
    # The writer appends YYYYMMDD_HHMMSS; require that exact suffix so model
    # names containing underscores cannot match a different model's prefix.
    return any(
        p.is_dir() and p.name.startswith(prefix)
        and re.fullmatch(r"[0-9]{8}_[0-9]{6}", p.name[len(prefix):])
        and report_complete(p)
        for p in directory.iterdir()
    )


def report_complete(directory):
    """A completed run needs populated stages and an absolute numeric target."""
    def populated(path):
        try:
            return bool(path.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError):
            return False

    try:
        target = extract_price_target((directory / "5_portfolio/decision.md").read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return False
    return (
        target is not None
        and
        all(populated(directory / name) for name in (
            "complete_report.md", "3_trading/trader.md", "5_portfolio/decision.md",
        ))
        and any(populated(directory / "1_analysts" / name) for name in (
            "market.md", "sentiment.md", "news.md", "fundamentals.md",
        ))
    )


def wait_for_worker(child, max_seconds):
    if max_seconds is None:
        return child.wait()
    # subprocess timeouts use a clock that pauses during sleep on macOS.
    # Poll a wall deadline so a suspended machine cannot extend the run limit.
    deadline = time.time() + max_seconds
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(child.args, max_seconds)
        try:
            return child.wait(timeout=min(remaining, 1))
        except subprocess.TimeoutExpired:
            continue


def run_guarded(reports, date, model, ticker, log, command, max_seconds=None):
    prefix = report_prefix(date, model)
    # Canonical docs paths make symlinked launchers share the same lock domain.
    reports = reports.resolve()
    key = hashlib.sha256(str(reports / ticker / prefix).encode()).hexdigest()
    locks = reports.parent / ".tradingagents" / "report-locks"
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / (key + ".lock")).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"[WAIT {ticker}] another run owns {prefix}", flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
        if report_exists(reports, ticker, prefix):
            print(f"[SKIP {ticker}] report already exists: {prefix}", flush=True)
            return 0
        print(f"[START {ticker}] {prefix}", flush=True)
        # Open logs only after the lock/check so a duplicate cannot truncate them.
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as output:
            child = subprocess.Popen(
                command, stdout=output, stderr=subprocess.STDOUT,
                start_new_session=True, pass_fds=(lock.fileno(),),
            )
            def forward_signal(signum, frame):
                with suppress(ProcessLookupError):
                    os.killpg(child.pid, signum)
            previous = {s: signal.signal(s, forward_signal) for s in (signal.SIGINT, signal.SIGTERM)}
            try:
                try:
                    status = wait_for_worker(child, max_seconds)
                except subprocess.TimeoutExpired:
                    print(f"[TIMEOUT {ticker}] worker exceeded {max_seconds:g}s; checkpoint retained", flush=True)
                    forward_signal(signal.SIGTERM, None)
                    with suppress(subprocess.TimeoutExpired):
                        child.wait(timeout=10)
                    # An exited parent can leave descendants holding the lock.
                    # Stop the entire worker group even if child.wait succeeded.
                    forward_signal(signal.SIGKILL, None)
                    child.wait()
                    return 124
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
        if status == 0 and not report_exists(reports, ticker, prefix):
            print(f"[FAIL {ticker}] worker exited without a complete report with a numeric target", flush=True)
            return 1
        return status if status >= 0 else 128 - status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("missing", "run"))
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--ticker")
    parser.add_argument("--log", type=Path)
    parser.add_argument("--max-seconds", type=float, default=os.environ.get("TRADINGAGENTS_REPORT_MAX_SECONDS"),
                        help="Optional worker wall-clock limit; interrupted checkpoints remain available.")
    parser.add_argument("arguments", nargs="*")
    # Commands after -- must pass through without parsing uv/CLI options.
    argsv = sys.argv[1:]
    command = []
    if "--" in argsv:
        split = argsv.index("--")
        command, argsv = argsv[split + 1:], argsv[:split]
    args = parser.parse_args(argsv)
    if args.max_seconds is not None and (not math.isfinite(args.max_seconds) or args.max_seconds <= 0):
        parser.error("--max-seconds must be a finite positive number")
    if args.action == "missing":
        prefix = report_prefix(args.date, args.model)
        for ticker in dict.fromkeys(t.upper() for t in args.arguments + command):
            if not report_exists(args.reports_dir, ticker, prefix):
                print(ticker)
        return 0
    if not args.ticker or args.log is None or not command:
        parser.error("run requires --ticker, --log, and a command after --")
    return run_guarded(args.reports_dir, args.date, args.model, args.ticker.upper(), args.log, command, args.max_seconds)


if __name__ == "__main__":
    sys.exit(main())
