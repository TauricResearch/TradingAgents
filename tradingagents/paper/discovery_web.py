"""Loopback-only discovery subprocess + independently saved research snapshots."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from .discovery import DEFAULT_HOME

_RUN=re.compile(r"^\d{8}T\d{6}Z$")
_TICKER=re.compile(r"^[A-Z0-9.-]{1,12}$")


def safe_report(home: Path, run_id: str, ticker: str, filename: str="complete_report.html") -> Path | None:
    if filename not in ("complete_report.html","compounder_memo.md"):
        return None
    if not _RUN.fullmatch(run_id) or not _TICKER.fullmatch(ticker):
        return None
    root=(home/"runs").resolve()
    report=(root/run_id/"reports"/ticker/filename).resolve()
    return report if report.is_relative_to(root) and report.is_file() else None


def latest(home: Path=DEFAULT_HOME) -> dict:
    path=home/"latest.json"
    if not path.is_file():
        return {"status":"not_run","candidates":[],"ai_reports":[],
                "notice":"No stock discovery run yet. No orders."}
    try:
        with path.open("r",encoding="utf-8") as stream:
            record=json.load(stream)
        if record.get("schema")!="koral_equities_discovery_v1":
            raise ValueError("Unrecognised snapshot")
        reports=[]
        for item in record.get("ai_reports",[]):
            visible={k:v for k,v in item.items() if k!="report_path"}
            run=record.get("run_id","")
            ticker=item.get("ticker","")
            if safe_report(home,run,ticker):
                visible["report_url"]=f"/discovery/reports/{run}/{ticker}/complete_report.html"
            if item.get("memo_status")=="completed" and safe_report(home,run,ticker,"compounder_memo.md"):
                visible["memo_url"]=f"/discovery/reports/{run}/{ticker}/compounder_memo.md"
            reports.append(visible)
        record["ai_reports"]=reports
        record.pop("profile_exclusions",None)
        return record
    except (OSError,ValueError,TypeError,KeyError):
        return {"status":"error","candidates":[],"ai_reports":[],
                "notice":"Saved discovery report invalid or unavailable"}


class DiscoveryRuntime:
    def __init__(self,home: Path=DEFAULT_HOME,working_dir: Path | None=None):
        self.home=home.expanduser().resolve()
        self.cwd=working_dir or Path.cwd()
        self.lock=threading.Lock()
        self.process: subprocess.Popen | None=None
        self.started_at: str | None=None
        self.log_path=self.home/"discovery_scan.log"

    def start(self, max_symbols: int=350, ai: int=2):
        if type(max_symbols) is not int or not 50<=max_symbols<=2000:
            raise ValueError("Choose 50–2000 symbols")
        if type(ai) is not int or not 0<=ai<=3:
            raise ValueError("Choose 0–3 AI reports")
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("Discovery scan already in progress")
            self.home.mkdir(parents=True,exist_ok=True)
            with self.log_path.open("w",encoding="utf-8") as output:
                self.process=subprocess.Popen(
                    [sys.executable,"-u","-m","tradingagents.paper.discovery",
                     "--home",str(self.home),"--max-symbols",str(max_symbols),
                     "--ai",str(ai)],
                    cwd=str(self.cwd),stdin=subprocess.DEVNULL,
                    stdout=output,stderr=subprocess.STDOUT,
                )
            self.started_at=datetime.now(timezone.utc).isoformat()

    def status(self) -> dict:
        with self.lock:
            running=self.process is not None and self.process.poll() is None
            finished=self.process is not None and not running
            rc=self.process.returncode if finished else None
            log=""
            try:
                if self.log_path.exists():
                    with self.log_path.open("rb") as file:
                        file.seek(max(0,file.seek(0,2)-15000))
                        log=file.read().decode("utf-8",errors="replace")
            except OSError:
                log="Log currently inaccessible"
            return {"running":running,"finished":finished,"returncode":rc,
                    "started_at":self.started_at,"log":log}
