"""Retry an Oracle Ampere launch until capacity appears, then alert on Telegram.

Oracle publishes no capacity signal and offers no alerting, so the only way to
know an Always Free A1 slot has opened is to attempt a launch and see whether it
errors. This does that on a schedule and tells you the moment it succeeds,
reusing the Telegram bot the assistant already has configured.

Setup (one time):
  1. Install the OCI CLI:
       PowerShell> Invoke-WebRequest https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.ps1 -OutFile install.ps1
       PowerShell> .\\install.ps1
  2. Configure it — this writes ~/.oci/config and uploads an API key:
       oci setup config
     Answer the prompts, then upload the generated public key in the console at
     Identity -> My profile -> API keys.
  3. Fill in the OCIDs below (get them from Cloud Shell, see README).

Run:
  python deploy/watch-for-capacity.py                 # every 15 min until it lands
  python deploy/watch-for-capacity.py --once          # single attempt, for testing
  python deploy/watch-for-capacity.py --interval 1800 # every 30 min

Leave it running in a spare terminal. It costs nothing: a failed launch is a
rejected API call, not a resource.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(key: str, default: str = "") -> str:
    """Read one key from the repo .env.

    Deliberately a local reader rather than app.core.config: these are
    deployment concerns, and the assistant's settings model should not grow
    fields describing cloud provisioning. Decoded utf-8-sig because a BOM
    corrupts the first key on Windows (see CLAUDE.md).
    """
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


# --- read from .env; see deploy/README.md for how to get the OCIDs ----------
COMPARTMENT_ID = _env("OCI_COMPARTMENT_ID")
SUBNET_ID = _env("OCI_SUBNET_ID")
SSH_PUBLIC_KEY_PATH = _env(
    "OCI_SSH_PUBLIC_KEY_PATH", str(Path.home() / ".ssh" / "oci_ta.pub")
)

SHAPE = _env("OCI_SHAPE", "VM.Standard.A1.Flex")
OCPUS = int(_env("OCI_OCPUS", "2"))
MEMORY_GB = int(_env("OCI_MEMORY_GB", "12"))
DISPLAY_NAME = _env("OCI_DISPLAY_NAME", "tradingagents-vm")
# Ampere is available in every AD, so try each one — capacity is per-AD.
AVAILABILITY_DOMAINS: list[str] = []   # empty = discover automatically

# "Out of capacity" is the only error worth retrying. Anything else — a bad
# OCID, a quota of zero, an auth failure — will never fix itself, so stop and
# say so rather than hammering the API for days.
_RETRYABLE = ("out of host capacity", "outofcapacity", "out of capacity")


def _oci_binary() -> str:
    """Absolute path to the OCI CLI.

    On Windows ``oci`` is a .cmd/.exe shim that ``subprocess`` cannot resolve
    from a bare name, and a shell opened before the installer ran will not have
    the updated PATH either — both surface as a bare WinError 2. Resolving the
    path explicitly turns that into a message that says what to do.
    """
    import shutil

    found = shutil.which("oci")
    if found:
        return found
    # Default install locations the installer uses when PATH has not refreshed.
    candidates = [
        Path.home() / "bin" / "oci.exe",
        Path.home() / "bin" / "oci",
        Path.home() / "lib" / "oracle-cli" / "Scripts" / "oci.exe",
        Path("C:/Program Files/Oracle/oci-cli/oci.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "The OCI CLI was not found.\n"
        "  - If you just installed it, CLOSE AND REOPEN this terminal so PATH refreshes.\n"
        "  - Verify with:  oci --version\n"
        "  - Install:      https://docs.oracle.com/iaas/Content/API/SDKDocs/cliinstall.htm"
    )


_OCI: str | None = None


def _run(args: list[str]) -> tuple[int, str, str]:
    """Run the CLI. Returns (returncode, stdout, stderr) — kept SEPARATE.

    The OCI CLI writes a CryptographyDeprecationWarning to stderr on every
    invocation. Merging the streams appends that text after the JSON payload
    and breaks every parse, so stdout stays clean for parsing and stderr is
    used only for error messages.
    """
    global _OCI
    if _OCI is None:
        _OCI = _oci_binary()
    resolved = [_OCI if a == "oci" else a for a in args]
    proc = subprocess.run(resolved, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or ""), (proc.stderr or "")


_LOG_PATH = _REPO_ROOT / "capacity-watch.log"


def _log(message: str) -> None:
    """Print and append to a file.

    Running headless via Task Scheduler there is no console to watch, so the
    log is the only way to tell "waiting patiently" from "died on startup".
    """
    stamped = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}  {message}"
    print(stamped, flush=True)
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(stamped + "\n")
    except OSError:
        pass


def _notify(message: str) -> None:
    """Best-effort Telegram ping using the assistant's existing credentials."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from app.core.config import get_settings

        settings = get_settings()
        token = settings.telegram_bot_token.strip()
        chat_id = settings.telegram_chat_id.strip()
        if not token or not chat_id:
            return
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        ).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=15
        )
    except Exception:
        pass  # an alerting failure must not stop the watch


def _discover_ads() -> list[str]:
    # -c is required outside Cloud Shell: there the config supplies a default
    # compartment, so omitting it works there and fails everywhere else.
    # NOT --raw-output: on a list query that prints a pseudo-JSON blob whose
    # lines still carry quotes and commas, which then travel into the launch
    # call as part of the AD name and come back as CannotParseRequest.
    code, out, err = _run([
        "oci", "iam", "availability-domain", "list",
        "-c", COMPARTMENT_ID,
        "--query", "data[].name",
    ])
    if code != 0:
        # Surface the CLI's own message — "could not list" on its own gives the
        # reader nothing to act on, and the usual cause (an API key generated
        # but never uploaded to the console) has a specific fix.
        print(err.strip()[:400] or out.strip()[:400])
        return []
    try:
        return [a.strip() for a in json.loads(out) if a and a.strip()]
    except Exception:
        print(out.strip()[:400])
        return []


def _find_image() -> str | None:
    code, out, _ = _run([
        "oci", "compute", "image", "list", "-c", COMPARTMENT_ID,
        "--operating-system", "Canonical Ubuntu",
        "--operating-system-version", "24.04",
        "--shape", SHAPE,
        "--query", "data[0].id", "--raw-output",
    ])
    return out.strip() if code == 0 and out.strip().startswith("ocid1.image") else None


def attempt(image_id: str, ad: str) -> tuple[bool, str]:
    """One launch attempt. Returns (launched, message)."""
    key = Path(SSH_PUBLIC_KEY_PATH).read_text().strip()
    code, out, err = _run([
        "oci", "compute", "instance", "launch",
        "--compartment-id", COMPARTMENT_ID,
        "--availability-domain", ad,
        "--shape", SHAPE,
        "--shape-config", json.dumps({"ocpus": OCPUS, "memoryInGBs": MEMORY_GB}),
        "--image-id", image_id,
        "--subnet-id", SUBNET_ID,
        "--display-name", DISPLAY_NAME,
        "--assign-public-ip", "true",
        "--metadata", json.dumps({"ssh_authorized_keys": key}),
        "--wait-for-state", "RUNNING",
    ])
    if code == 0:
        return True, out
    combined = (out + err)
    lowered = combined.lower()
    if any(marker in lowered for marker in _RETRYABLE):
        return False, "out of capacity"
    # A non-capacity error will not resolve by waiting — surface it.
    raise RuntimeError(combined.strip()[:600])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=900, help="seconds between rounds")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not COMPARTMENT_ID or not SUBNET_ID:
        print(
            "Set OCI_COMPARTMENT_ID and OCI_SUBNET_ID in .env first.\n"
            "  In OCI Cloud Shell:\n"
            "    echo $OCI_TENANCY\n"
            "    oci network subnet list -c $OCI_TENANCY \\\n"
            "      --query 'data[].{name:\"display-name\",id:id}' --output table"
        )
        return 2

    try:
        print(f"using OCI CLI at {_oci_binary()}")
    except FileNotFoundError as exc:
        print(exc)
        return 2

    key_path = Path(SSH_PUBLIC_KEY_PATH)
    if not key_path.exists():
        print(f"SSH public key not found at {key_path}")
        return 2

    image_id = _find_image()
    if not image_id:
        print("Could not resolve an Ubuntu 24.04 image for", SHAPE)
        return 2

    ads = AVAILABILITY_DOMAINS or _discover_ads()
    if not ads:
        print("Could not list availability domains — is the OCI CLI configured?")
        return 2

    _log(f"watching {SHAPE} ({OCPUS} OCPU / {MEMORY_GB} GB) across {len(ads)} ADs")
    _log(f"image {image_id[:40]}...  every {args.interval}s")
    if not args.once:
        # Confirm the watch is alive when it starts headless — otherwise a
        # scheduled task that silently failed to launch is indistinguishable
        # from one that is patiently waiting.
        _notify(
            f"👀 <b>Ampere capacity watch started</b>\n"
            f"{SHAPE} · {OCPUS} OCPU / {MEMORY_GB} GB · {len(ads)} ADs\n"
            f"Checking every {args.interval // 60} min. You will be pinged the "
            "moment it launches."
        )

    rounds = 0
    while True:
        rounds += 1
        for ad in ads:
            try:
                launched, detail = attempt(image_id, ad)
            except RuntimeError as exc:
                _log(f"FATAL in {ad}: {exc}")
                _notify(f"🛑 <b>Capacity watch stopped</b>\n{exc}")
                return 1
            if launched:
                _log(f"LAUNCHED in {ad}")
                _notify(
                    "🎉 <b>Ampere capacity found</b>\n"
                    f"{DISPLAY_NAME} is RUNNING in {ad} "
                    f"({OCPUS} OCPU / {MEMORY_GB} GB).\n"
                    "Get the IP:\n<code>oci compute instance list-vnics "
                    "--instance-id &lt;ocid&gt; --query 'data[0].\"public-ip\"'</code>"
                )
                _log(detail[:2000])
                return 0
            _log(f"{ad}: {detail}")
        if args.once:
            return 3
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
