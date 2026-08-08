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

# --- fill these in from Cloud Shell -----------------------------------------
# echo $C; echo $SUBNET   (see deploy/README.md)
COMPARTMENT_ID = ""          # ocid1.tenancy.oc1..
SUBNET_ID = ""               # ocid1.subnet.oc1...
SSH_PUBLIC_KEY_PATH = str(Path.home() / ".ssh" / "oci_ta.pub")

SHAPE = "VM.Standard.A1.Flex"
OCPUS = 2
MEMORY_GB = 12
DISPLAY_NAME = "tradingagents-vm"
# Ampere is available in every AD, so try each one — capacity is per-AD.
AVAILABILITY_DOMAINS: list[str] = []   # empty = discover automatically

# "Out of capacity" is the only error worth retrying. Anything else — a bad
# OCID, a quota of zero, an auth failure — will never fix itself, so stop and
# say so rather than hammering the API for days.
_RETRYABLE = ("out of host capacity", "outofcapacity", "out of capacity")


def _run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


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
    code, out = _run([
        "oci", "iam", "availability-domain", "list",
        "--query", "data[].name", "--raw-output",
    ])
    if code != 0:
        return []
    try:
        return [a.strip() for a in json.loads(out) if a.strip()]
    except Exception:
        return []


def _find_image() -> str | None:
    code, out = _run([
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
    code, out = _run([
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
    lowered = out.lower()
    if any(marker in lowered for marker in _RETRYABLE):
        return False, "out of capacity"
    # A non-capacity error will not resolve by waiting — surface it.
    raise RuntimeError(out.strip()[:600])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=900, help="seconds between rounds")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not COMPARTMENT_ID or not SUBNET_ID:
        print("Fill in COMPARTMENT_ID and SUBNET_ID at the top of this file first.")
        return 2

    image_id = _find_image()
    if not image_id:
        print("Could not resolve an Ubuntu 24.04 image for", SHAPE)
        return 2

    ads = AVAILABILITY_DOMAINS or _discover_ads()
    if not ads:
        print("Could not list availability domains — is the OCI CLI configured?")
        return 2

    print(f"watching {SHAPE} ({OCPUS} OCPU / {MEMORY_GB} GB) across {len(ads)} ADs")
    print(f"image {image_id[:40]}...  every {args.interval}s.  Ctrl+C to stop.\n")

    rounds = 0
    while True:
        rounds += 1
        for ad in ads:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
            try:
                launched, detail = attempt(image_id, ad)
            except RuntimeError as exc:
                print(f"{stamp}  FATAL in {ad}: {exc}")
                _notify(f"🛑 <b>Capacity watch stopped</b>\n{exc}")
                return 1
            if launched:
                print(f"\n{stamp}  LAUNCHED in {ad}")
                _notify(
                    "🎉 <b>Ampere capacity found</b>\n"
                    f"{DISPLAY_NAME} is RUNNING in {ad} "
                    f"({OCPUS} OCPU / {MEMORY_GB} GB).\n"
                    "Get the IP:\n<code>oci compute instance list-vnics "
                    "--instance-id &lt;ocid&gt; --query 'data[0].\"public-ip\"'</code>"
                )
                print(detail[:2000])
                return 0
            print(f"{stamp}  {ad}: {detail}")
        if args.once:
            return 3
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
