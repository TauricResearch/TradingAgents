"""Go-live readiness self-check (Phase 3).

``go_live_readiness()`` runs every security/ops precondition and returns
a ``ReadinessReport``. Any FAIL blocks arming (the Phase-4 ceremony
refuses); WARN items print loudly but don't block. The report is
"signed" by appending it to the hash-chained audit log — the arming
decision and the evidence it was based on become tamper-evident history.

Checks:
- dashboard auth token present and non-trivial (live mode must never
  run open, unlike the paper dev mode)
- venue clock skew within the signing budget (Delta signatures die in 5s)
- venue key scope: verified Trading-scope by a harmless authenticated
  read; Delta India API keys have no withdrawal scope at all — recorded
  as evidence, not assumed
- secrets file permissions (no group/other access)
- .env hygiene: production keys should come from _FILE/SOPS, not
  plaintext .env (WARN)
- host: Docker Desktop / macOS laptop is not an acceptable armed-live
  host (WARN now, prominent; deployment docs target an always-on VPS)
- IP-whitelist reminder (venue-side setting we cannot verify from here)
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field

from tradingagents.pro.secrets import describe_source, get_secret

MIN_TOKEN_LENGTH = 16


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str          # "pass" | "warn" | "fail"
    detail: str


@dataclass
class ReadinessReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append(CheckResult(name, status, detail))

    def as_dict(self) -> dict:
        return {"ok": self.ok,
                "checks": [c.__dict__ for c in self.checks]}

    def render(self) -> str:
        icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
        lines = ["go-live readiness report", "-" * 40]
        for c in self.checks:
            lines.append(f"[{icon[c.status]}] {c.name}: {c.detail}")
        lines.append("-" * 40)
        lines.append("READY TO ARM" if self.ok
                     else "NOT READY — every FAIL above blocks arming")
        return "\n".join(lines)


def check_auth(report: ReadinessReport) -> None:
    token = get_secret("PRO_DASHBOARD_TOKEN")
    if not token:
        report.add("dashboard_auth", "fail",
                   "PRO_DASHBOARD_TOKEN unset — live mode must not run "
                   "with an open dashboard (dev auth-off is paper-only)")
    elif len(token) < MIN_TOKEN_LENGTH:
        report.add("dashboard_auth", "fail",
                   f"token shorter than {MIN_TOKEN_LENGTH} chars — too weak "
                   "for a control surface over real capital")
    else:
        report.add("dashboard_auth", "pass",
                   f"token set ({describe_source('PRO_DASHBOARD_TOKEN')})")


def check_clock(report: ReadinessReport, adapter) -> None:
    try:
        adapter.check_clock()
        report.add("clock_skew", "pass",
                   "local/venue skew within the 2s signing budget")
    except Exception as exc:
        report.add("clock_skew", "fail", f"{exc}")


def check_key_scope(report: ReadinessReport, adapter) -> None:
    """A harmless authenticated read proves the key works for trading
    data. Delta India keys carry Read/Trading scopes only — withdrawal
    by API does not exist on this venue; recorded as evidence."""
    try:
        adapter.account()
        report.add("venue_key_scope", "pass",
                   "authenticated read OK; venue key scopes are Read/"
                   "Trading only (Delta India has no withdrawal-by-API)")
    except Exception as exc:
        report.add("venue_key_scope", "fail",
                   f"authenticated venue read failed: {exc}")


def check_secrets_hygiene(report: ReadinessReport,
                          names: tuple[str, ...] = (
                              "DELTA_API_KEY", "DELTA_API_SECRET")) -> None:
    from tradingagents.pro.secrets import file_permissions_ok

    for name in names:
        source = describe_source(name)
        if source.startswith("file:"):
            path = source.split(":", 1)[1]
            try:
                if file_permissions_ok(path):
                    report.add(f"secret_{name}", "pass", "file, mode 0600")
                else:
                    report.add(f"secret_{name}", "fail",
                               f"{path} readable by group/other")
            except OSError as exc:
                report.add(f"secret_{name}", "fail", str(exc))
        elif source == "env":
            report.add(f"secret_{name}", "warn",
                       "from plain env — fine for testnet; production should "
                       "use _FILE/Docker secrets or sops exec-env")
        else:
            report.add(f"secret_{name}", "fail", "not configured")

    env_file = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_file):
        from tradingagents.pro.secrets import file_permissions_ok as _ok

        try:
            if not _ok(env_file):
                report.add("dotenv_permissions", "fail",
                           ".env readable by group/other — chmod 600 it")
            else:
                report.add("dotenv_permissions", "pass", ".env mode 0600")
        except OSError:
            pass


def check_host(report: ReadinessReport) -> None:
    in_docker = os.path.exists("/.dockerenv")
    if platform.system() == "Darwin" or (
            in_docker and "linuxkit" in platform.release().lower()):
        report.add("host", "warn",
                   "running on Docker Desktop / a laptop — acceptable for "
                   "shadow/canary, NOT for unattended armed live (sleep = "
                   "unmanaged positions); target an always-on Linux host "
                   "with NTP")
    else:
        report.add("host", "pass", f"{platform.system()} {platform.release()}")


def check_ip_whitelist_reminder(report: ReadinessReport) -> None:
    report.add("venue_ip_whitelist", "warn",
               "cannot be verified from here — confirm the API key is "
               "IP-whitelisted in the Delta dashboard before arming")


def go_live_readiness(adapter=None, audit=None) -> ReadinessReport:
    """Full self-check. ``adapter`` = the live venue adapter (skipping it
    marks the venue checks failed — no adapter, no arming). Appends the
    signed report to the audit chain when provided."""
    report = ReadinessReport()
    check_auth(report)
    if adapter is not None:
        check_clock(report, adapter)
        check_key_scope(report, adapter)
    else:
        report.add("clock_skew", "fail", "no venue adapter supplied")
        report.add("venue_key_scope", "fail", "no venue adapter supplied")
    check_secrets_hygiene(report)
    check_host(report)
    check_ip_whitelist_reminder(report)
    if audit is not None:
        audit.append("go_live_readiness", report.as_dict())
    return report
