"""Watch for Oracle Ampere capacity from inside the assistant's own scheduler.

Oracle publishes no capacity signal and offers no alerting, so the only way to
learn an Always Free A1 slot has opened is to attempt a launch and see whether
it errors. The assistant is already an always-on process with a working
Telegram channel, so this rides along with it rather than needing a separate
headless task to babysit.

Notification policy: ONE sentence, and only when the answer changes.
Availability is checked every few minutes, which would be hundreds of messages
a day if each result were reported. A watcher that cries "still nothing" 288
times a day gets muted, and then the one message that matters is missed too.
So: silence while unavailable, one line when it lands.

Disabled unless ``OCI_COMPARTMENT_ID`` and ``OCI_SUBNET_ID`` are set in .env.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Transient conditions. Everything else — a bad OCID, a zero service limit, an
#: auth failure — will never resolve by waiting, so it is logged once and the
#: watch disables itself rather than repeating the same failure indefinitely.
_RETRYABLE = ("out of host capacity", "outofcapacity", "out of capacity")
_THROTTLED = ("toomanyrequests", "too many requests", "rate limit")

#: Network-level failures, which say nothing about capacity and resolve on their
#: own. Unclassified they read as permanent, and one dropped packet then kills a
#: watch that is meant to run for months — which is exactly what happened on
#: 2026-08-11: "The connection to endpoint timed out." disabled it after 12
#: healthy hours, and it stayed dead until the next restart.
_TRANSIENT = (
    "connection to endpoint timed out", "connection timed out", "connect timeout",
    "read timeout", "timed out", "connection aborted", "connection reset",
    "temporary failure in name resolution", "could not resolve host",
    "service unavailable", "bad gateway", "gateway timeout", "connectionerror",
)

#: Consecutive hard errors tolerated before the watch gives up. A misconfigured
#: OCID fails identically every time and trips this quickly; a one-off API
#: hiccup does not.
_MAX_CONSECUTIVE_ERRORS = 3

#: Set once a permanent error is seen, so the job stops re-running a request
#: that cannot succeed. Cleared only by restarting the service.
_disabled_reason: str | None = None
_launched = False
_consecutive_errors = 0


def _classify(blob: str) -> str | None:
    """'retry' | 'throttled' | 'transient' for known conditions, else None."""
    blob = blob.lower()
    if any(m in blob for m in _RETRYABLE):
        return "retry"
    if any(m in blob for m in _THROTTLED):
        return "throttled"
    if any(m in blob for m in _TRANSIENT):
        return "transient"
    return None


def _env(key: str, default: str = "") -> str:
    """Read one key from the repo .env (BOM-safe — see CLAUDE.md)."""
    path = _REPO_ROOT / ".env"
    if not path.exists():
        return default
    for line in path.read_bytes().decode("utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return default


def is_configured() -> bool:
    return bool(_env("OCI_COMPARTMENT_ID") and _env("OCI_SUBNET_ID"))


def _oci() -> str | None:
    found = shutil.which("oci")
    if found:
        return found
    for candidate in (
        Path.home() / "bin" / "oci.exe",
        Path.home() / "bin" / "oci",
        Path("/usr/local/bin/oci"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _try_launch_sync() -> tuple[str, str]:
    """Attempt one launch. Returns (status, detail).

    status is one of: launched | unavailable | throttled | error | unconfigured
    """
    binary = _oci()
    if binary is None:
        return "error", "OCI CLI not found on PATH"

    compartment = _env("OCI_COMPARTMENT_ID")
    subnet = _env("OCI_SUBNET_ID")
    key_path = Path(_env("OCI_SSH_PUBLIC_KEY_PATH", str(Path.home() / ".ssh" / "oci_ta.pub")))
    if not key_path.exists():
        return "error", f"SSH public key not found at {key_path}"

    shape = _env("OCI_SHAPE", "VM.Standard.A1.Flex")
    ocpus = int(_env("OCI_OCPUS", "2"))
    memory = int(_env("OCI_MEMORY_GB", "12"))
    name = _env("OCI_DISPLAY_NAME", "tradingagents-vm")

    def run(args: list[str]) -> tuple[int, str, str]:
        # stdout and stderr stay SEPARATE: the CLI writes a deprecation warning
        # to stderr on every call, and merging it corrupts every JSON parse.
        proc = subprocess.run([binary, *args], capture_output=True, text=True)
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    code, out, err = run([
        "compute", "image", "list", "-c", compartment,
        "--operating-system", "Canonical Ubuntu", "--operating-system-version", "24.04",
        "--shape", shape, "--query", "data[0].id", "--raw-output",
    ])
    image = out.strip()
    if code != 0 or not image.startswith("ocid1.image"):
        blob = (err or out).strip()
        if _classify(blob) == "transient":
            return "transient", blob[:300]
        return "error", blob[:300]

    code, out, err = run([
        "iam", "availability-domain", "list", "-c", compartment, "--query", "data[].name",
    ])
    try:
        ads = [a for a in json.loads(out) if a]
    except Exception:
        blob = (err or out).strip()
        if _classify(blob) == "transient":
            return "transient", blob[:300]
        return "error", blob[:300]

    key = key_path.read_text().strip()
    throttled = transient = False
    for ad in ads:
        code, out, err = run([
            "compute", "instance", "launch",
            "--compartment-id", compartment, "--availability-domain", ad,
            "--shape", shape,
            "--shape-config", json.dumps({"ocpus": ocpus, "memoryInGBs": memory}),
            "--image-id", image, "--subnet-id", subnet,
            "--display-name", name, "--assign-public-ip", "true",
            "--metadata", json.dumps({"ssh_authorized_keys": key}),
            "--wait-for-state", "RUNNING",
        ])
        if code == 0:
            return "launched", ad
        kind = _classify(out + err)
        if kind == "retry":
            continue
        if kind == "throttled":
            throttled = True
            continue
        if kind == "transient":
            transient = True
            continue
        return "error", (err or out).strip()[:300]

    if transient:
        return "transient", ""
    return ("throttled", "") if throttled else ("unavailable", "")


async def check_capacity() -> str:
    """One capacity check. Alerts only on a state change worth acting on."""
    global _disabled_reason, _launched, _consecutive_errors

    if _launched or _disabled_reason or not is_configured():
        return "skipped"

    status, detail = await asyncio.to_thread(_try_launch_sync)

    if status == "launched":
        _launched = True
        _consecutive_errors = 0
        logger.info("Oracle Ampere capacity found — instance launched in %s", detail)
        await _notify(
            f"✅ Oracle Ampere capacity found — your VM is now running in {detail}."
        )
        return status

    if status == "transient":
        # A network failure says nothing about capacity. Retry next tick.
        _consecutive_errors = 0
        logger.warning("Oracle capacity check: transient network failure, will retry")
        return status

    if status == "error":
        # A permanent error repeats forever if left alone, so say it ONCE and
        # stop rather than sending the same stack trace every few minutes. But
        # only after it has repeated: a single odd response used to end the
        # watch for the life of the process.
        _consecutive_errors += 1
        if _consecutive_errors < _MAX_CONSECUTIVE_ERRORS:
            logger.warning(
                "Oracle capacity check failed (%d/%d before giving up): %s",
                _consecutive_errors, _MAX_CONSECUTIVE_ERRORS, detail,
            )
            return status
        _disabled_reason = detail
        logger.error("Capacity watch disabled after %d consecutive failures: %s",
                     _consecutive_errors, detail)
        await _notify(
            "⚠️ Oracle capacity watch stopped — it needs attention. "
            "See the server log for details."
        )
        return status

    # unavailable / throttled: expected, frequent, and not worth a message.
    _consecutive_errors = 0
    logger.info("Oracle Ampere capacity check: %s", status)
    return status


async def _notify(message: str) -> None:
    try:
        from app.services.notifier import Notifier

        await Notifier(get_settings()).send_telegram(message)
    except Exception:
        logger.exception("Capacity notification failed")
