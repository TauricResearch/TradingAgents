"""Coordinate shell report generation by docs root, date, deep model, and ticker.

Uses OS advisory locks on macOS/Linux; persistent lock files are intentional.
Removing a lock file could let two processes lock different inodes for one key.
"""

import argparse
import fcntl
import hashlib
import os
import re
import signal
import subprocess
import sys
from contextlib import suppress
from pathlib import Path


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
        for p in directory.iterdir()
    )


def run_guarded(reports, date, model, ticker, log, command):
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
                status = child.wait()
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
        return status if status >= 0 else 128 - status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("missing", "run"))
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--ticker")
    parser.add_argument("--log", type=Path)
    parser.add_argument("arguments", nargs="*")
    # Commands after -- must pass through without parsing uv/CLI options.
    argsv = sys.argv[1:]
    command = []
    if "--" in argsv:
        split = argsv.index("--")
        command, argsv = argsv[split + 1:], argsv[:split]
    args = parser.parse_args(argsv)
    if args.action == "missing":
        prefix = report_prefix(args.date, args.model)
        for ticker in dict.fromkeys(t.upper() for t in args.arguments + command):
            if not report_exists(args.reports_dir, ticker, prefix):
                print(ticker)
        return 0
    if not args.ticker or args.log is None or not command:
        parser.error("run requires --ticker, --log, and a command after --")
    return run_guarded(args.reports_dir, args.date, args.model, args.ticker.upper(), args.log, command)


if __name__ == "__main__":
    sys.exit(main())
