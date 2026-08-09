"""Copy runtime state from ~/.tradingagents into <repo>/data so it travels with the drive.

Idempotent and safe to re-run. That matters: the database keeps changing while the
service runs, so a snapshot taken now is stale by the time you unplug. Run this once
to set things up, then **once more with the service stopped** immediately before
moving the drive.

The database is copied with SQLite's online backup API rather than a file copy. A
plain copy of a live database can capture a page mid-write; the backup API takes a
transactionally consistent snapshot even while the app is writing to it.

Credentials (``--with-secrets``) are copied only when asked for, because the drive is
exFAT and has no file permissions — see the security note in new_pc.md.

Usage, from the repo root:

    python scripts/migrate_to_repo.py                  # data only
    python scripts/migrate_to_repo.py --with-secrets   # + OCI/SSH keys
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

HOME = Path.home()
SOURCE = HOME / ".tradingagents"
DEST = Path("data")

#: Directories copied wholesale. ``memory`` feeds the agents' self-reflection loop,
#: so losing it silently degrades the engine rather than breaking it — which is why
#: it is copied rather than treated as a regenerable cache.
_TREES = ("logs", "cache", "memory")


def copy_database() -> tuple[bool, str]:
    """Snapshot assistant.db consistently, even with the service running."""
    src = SOURCE / "assistant.db"
    if not src.exists():
        return False, f"source database not found at {src}"

    dest = DEST / "assistant.db"
    dest.parent.mkdir(parents=True, exist_ok=True)

    source_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dest_con = sqlite3.connect(str(dest))
    try:
        source_con.backup(dest_con)
    finally:
        dest_con.close()
        source_con.close()

    rows = 0
    con = sqlite3.connect(str(dest))
    try:
        for (name,) in con.execute(
            "select name from sqlite_master where type='table'"
        ).fetchall():
            rows += con.execute(f"select count(*) from {name}").fetchone()[0]
    finally:
        con.close()
    return True, f"{dest} ({dest.stat().st_size:,} bytes, {rows:,} rows total)"


def copy_tree(name: str) -> str:
    src = SOURCE / name
    if not src.exists():
        return f"{name}: not present, skipped"
    dest = DEST / name
    skipped: list[str] = []

    def _copy(a: str, b: str) -> None:
        # A report being written right now would raise; record and move on rather
        # than aborting a migration over one transient file.
        try:
            shutil.copy2(a, b)
        except OSError as exc:
            skipped.append(f"{Path(a).name} ({exc.strerror})")

    shutil.copytree(src, dest, copy_function=_copy, dirs_exist_ok=True)
    count = sum(1 for _ in dest.rglob("*") if _.is_file())
    note = f"{name}: {count} files"
    if skipped:
        note += f"  [locked, skipped: {', '.join(skipped[:3])}]"
    return note


def copy_loose_files() -> list[str]:
    out = []
    for src in SOURCE.glob("*.json"):
        shutil.copy2(src, DEST / src.name)
        out.append(f"{src.name}: {src.stat().st_size:,} bytes")
    return out


def copy_secrets() -> list[str]:
    out = []
    pairs = [
        (HOME / ".oci" / "config", DEST / "secrets" / "oci" / "config"),
        (HOME / ".oci" / "oci_api_key.pem", DEST / "secrets" / "oci" / "oci_api_key.pem"),
        (HOME / ".oci" / "oci_api_key_public.pem",
         DEST / "secrets" / "oci" / "oci_api_key_public.pem"),
        (HOME / ".ssh" / "oci_ta", DEST / "secrets" / "ssh" / "oci_ta"),
        (HOME / ".ssh" / "oci_ta.pub", DEST / "secrets" / "ssh" / "oci_ta.pub"),
    ]
    for src, dest in pairs:
        if not src.exists():
            out.append(f"{src.name}: not found, skipped")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        out.append(f"{src.name}: copied")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-secrets", action="store_true",
                        help="also copy OCI API key and the VM SSH keypair")
    args = parser.parse_args()

    if not Path("app").is_dir() or not Path("pyproject.toml").exists():
        print("ERROR: run this from the repo root (the folder holding pyproject.toml).")
        return 1
    if not SOURCE.exists():
        print(f"ERROR: nothing to migrate — {SOURCE} does not exist.")
        return 1

    DEST.mkdir(exist_ok=True)
    print(f"source : {SOURCE}")
    print(f"dest   : {DEST.resolve()}")
    print()

    ok, detail = copy_database()
    print(f"database : {'OK  ' + detail if ok else 'FAILED  ' + detail}")
    if not ok:
        return 1

    for line in copy_loose_files():
        print(f"file     : {line}")
    for name in _TREES:
        print(f"tree     : {copy_tree(name)}")

    if args.with_secrets:
        print()
        for line in copy_secrets():
            print(f"secret   : {line}")
        print("  NOTE: exFAT has no file permissions — anyone with the drive can read these.")

    print()
    print("Done. Verify with:  python scripts/verify_migration.py")
    print("Re-run this with the service STOPPED right before you unplug the drive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
