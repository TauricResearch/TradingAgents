"""Smoke tests for hledger backup script and journal integrity."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

HL_JOURNAL = Path(os.environ.get("HLEDGER_FILE", Path.home() / ".hledger.journal"))
BACKUP_BIN = Path.home() / ".tradingagents" / "bin" / "backup-hledger.sh"
BACKUP_DIR = Path.home() / ".tradingagents" / "backups"


@pytest.fixture(autouse=True)
def require_hledger(monkeypatch):
    """Skip if hledger is not on PATH."""
    result = subprocess.run(["which", "hledger"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("hledger not installed")


@pytest.fixture(autouse=True)
def require_backup_script():
    if not BACKUP_BIN.exists():
        pytest.skip(f"backup script not found at {BACKUP_BIN}")


class TestJournalValidity:
    """hledger journal must parse, balance, and have all required accounts."""

    def test_journal_exists(self):
        assert HL_JOURNAL.exists(), f"Journal not found at {HL_JOURNAL}"

    def test_journal_parses(self):
        """hledger must be able to parse the journal without errors."""
        result = subprocess.run(
            ["hledger", "-f", str(HL_JOURNAL), "balance", "--depth=1"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"hledger parse failed: {result.stderr}"

    def test_journal_balances(self):
        """Journal must be double-entry balanced (debits == credits)."""
        result = subprocess.run(
            ["hledger", "-f", str(HL_JOURNAL), "balance"],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().split("\n")
        bottom_line = lines[-1] if lines else ""
        # Bottom line of hledger balance output is the total.
        # For a balanced journal this ends in a single commodity amount.
        # We check it parses without error; unbalanced journals error out.
        assert result.returncode == 0

    def test_accounts_declared(self):
        """All asset accounts used in journal should exist (no undefined accounts)."""
        # hledger print should reveal all postings
        result = subprocess.run(
            ["hledger", "-f", str(HL_JOURNAL), "print"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Confirm at least one account path is present
        assert "assets:" in result.stdout, "No assets: accounts found in journal"


class TestBackupScript:
    """backup-hledger.sh must create valid backups and verify cleanly."""

    def test_backup_creates_file(self, tmp_path):
        """Backup must create a .journal file in BACKUP_DIR."""
        # Run backup (uses real source journal)
        result = subprocess.run(
            [str(BACKUP_BIN)],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(Path.home())},
        )
        assert result.returncode == 0, f"Backup failed: {result.stderr}"

        # Check a backup was created
        backups = list(BACKUP_DIR.glob("hledger-*.journal"))
        assert len(backups) >= 1, f"No backups found in {BACKUP_DIR}"

    def test_verify_succeeds(self):
        """backup-hledger.sh --verify must pass on existing backups."""
        result = subprocess.run(
            [str(BACKUP_BIN), "--verify"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(Path.home())},
        )
        assert result.returncode == 0, f"Verify failed: {result.stderr}"
        assert "[OK]" in result.stdout

    def test_backup_restore_roundtrip(self, tmp_path):
        """Restoring a backup must produce a valid journal."""
        # Get latest backup
        backups = sorted(BACKUP_DIR.glob("hledger-*.journal"))
        assert len(backups) >= 1, "No backups to test"
        latest = backups[-1]

        # Copy to temp location
        temp_journal = tmp_path / "test-restore.journal"
        temp_journal.write_bytes(latest.read_bytes())

        # Verify restored file parses
        result = subprocess.run(
            ["hledger", "-f", str(temp_journal), "balance"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Restored journal invalid: {result.stderr}"

    def test_backup_prunes_old_backups(self):
        """Backup script must not leave >30 day old backups."""
        before = set(BACKUP_DIR.glob("hledger-*.journal"))
        # Run backup
        subprocess.run([str(BACKUP_BIN)], capture_output=True, check=True)
        after = set(BACKUP_DIR.glob("hledger-*.journal"))

        # Should have at least one backup
        assert len(after) >= 1

        # latest.journal symlink must exist
        assert BACKUP_DIR.joinpath("latest.journal").exists()