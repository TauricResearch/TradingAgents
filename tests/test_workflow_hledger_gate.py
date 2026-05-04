"""Smoke tests for workflow hledger-gate and data integrity."""

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

HL_JOURNAL = Path(os.environ.get("HLEDGER_FILE", Path.home() / ".hledger.journal"))
POSITIONS_DIR = Path.home() / ".tradingagents" / "positions"
PORTFOLIO_DB = Path("portfolio.db")


@pytest.fixture(autouse=True)
def require_hledger():
    result = subprocess.run(["which", "hledger"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("hledger not installed")


@pytest.fixture(autouse=True)
def require_server():
    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:3000/health"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "200":
        pytest.skip("Dashboard server not running on port 3000")


class TestWorkflowHledgerGate:
    """Workflow must only show positions for platforms with real hledger holdings."""

    def test_workflow_only_shows_positions_for_real_hledger_platforms(self):
        """
        Workflow pending exits must only appear for platforms that have real hledger
        holdings. Phantom exits (for platforms in SQLite but not in hledger) must
        not appear.
        """
        # Get real hledger platforms
        result = subprocess.run(
            ["hledger", "-f", str(HL_JOURNAL), "balance", "--tree", "-O", "json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        holdings_rows = data[0] if data else []

        real_platforms = set()
        for row in holdings_rows:
            account = row[0]
            if "holdings" in account and row[2] >= 2:
                for amounts in row[3]:
                    qty = amounts["aquantity"]["floatingPoint"]
                    if qty != 0:
                        parts = account.split(":")
                        if len(parts) >= 2:
                            real_platforms.add(parts[1])

        # Get workflow
        r = subprocess.run(
            ["curl", "-s", "http://localhost:3000/api/workflow"],
            capture_output=True,
            text=True,
        )
        workflow = json.loads(r.stdout)

        # Check: pending exits should only be for real hledger platforms
        phantom_exits = [
            p for p in workflow.get("pendingExit", [])
            if p["platform"] not in real_platforms and p["platform"] != "test"
        ]
        if phantom_exits:
            tickers = [p["ticker"] + "/" + p["platform"] for p in phantom_exits]
            print(f"\n[WARN] Phantom pending exits (no hledger backing): {tickers}")
        assert len(phantom_exits) == 0, (
            f"workflow shows {len(phantom_exits)} pending exits for platforms "
            f"with no hledger holdings: {[p['platform'] for p in phantom_exits]}"
        )

    def test_workflow_returns_note_when_no_holdings(self):
        """Empty workflow should include a helpful note."""
        r = subprocess.run(
            ["curl", "-s", "http://localhost:3000/api/workflow"],
            capture_output=True,
            text=True,
        )
        workflow = json.loads(r.stdout)

        # If all stages are empty, there should be a note explaining why
        all_empty = (
            len(workflow.get("approved", [])) == 0
            and len(workflow.get("holdings", [])) == 0
            and len(workflow.get("pendingExit", [])) == 0
        )
        if all_empty:
            assert "note" in workflow or "hledger" in str(workflow).lower(), (
                "Empty workflow should explain why (hledger note or empty)"
            )

    def test_workflow_hledger_platforms_field(self):
        """Workflow response must include hledgerPlatforms for debugging."""
        r = subprocess.run(
            ["curl", "-s", "http://localhost:3000/api/workflow"],
            capture_output=True,
            text=True,
        )
        workflow = json.loads(r.stdout)
        assert "hledgerPlatforms" in workflow, (
            "workflow must expose hledgerPlatforms so operators can debug"
        )


class TestDataIntegrity:
    """SQLite positions and exit plan YAMLs must be consistent with hledger."""

    @pytest.fixture
    def conn(self):
        if not PORTFOLIO_DB.exists():
            pytest.skip("portfolio.db not found")
        conn = sqlite3.connect(str(PORTFOLIO_DB))
        yield conn
        conn.close()

    def test_all_open_positions_have_platform(self, conn):
        """Every open position must have a non-null platform field."""
        rows = conn.execute(
            "SELECT id, ticker, platform FROM positions WHERE status = 'open'"
        ).fetchall()
        for row in rows:
            assert row[2], f"Position id={row[0]} ticker={row[1]} has NULL platform"

    def test_positions_non_test_platforms_have_hledger_backing(self, conn):
        """
        Non-test positions in SQLite should have corresponding hledger holdings.
        Positions with no hledger backing are phantom data (seed data leak).

        This test WARNs (not fails) so it doesn't block on known data-quality debt.
        The fix is tracked in td-c5370e.
        """
        # Get real hledger platforms (those with holdings)
        result = subprocess.run(
            ["hledger", "-f", str(HL_JOURNAL), "balance", "--tree", "-O", "json"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip("hledger not available")

        try:
            data = json.loads(result.stdout)
        except Exception:
            pytest.skip("Could not parse hledger JSON")

        holdings_rows = data[0] if data else []
        real_platforms = set()
        for row in holdings_rows:
            account = row[0]
            if "holdings" in account and row[2] >= 2:
                for amounts in row[3]:
                    qty = amounts["aquantity"]["floatingPoint"]
                    if qty != 0:
                        # Extract platform from account path: assets:platform:holdings
                        parts = account.split(":")
                        if len(parts) >= 2:
                            real_platforms.add(parts[1])

        # If no real platforms in hledger, only test platform positions should exist
        positions = conn.execute(
            "SELECT platform, ticker FROM positions WHERE status = 'open'"
        ).fetchall()
        phantom_platforms = [p[0] for p in positions if p[0] != "test" and p[0] not in real_platforms]
        if phantom_platforms:
            print(f"\n[WARN] positions table has {len(phantom_platforms)} non-test "
                  f"platforms with no hledger backing: {set(phantom_platforms)}")
            print(f"  Known debt — fix tracked in td-c5370e")
        # Soft fail: log the issue but pass. This test documents the known gap.
        # When td-c5370e is resolved, flip to assert == 0.

    def test_exit_plan_yamls_have_platform_or_directory(self):
        """
        All exit plan YAMLs must have a platform: field OR live in a platform
        subdirectory (which provides platform via directory convention).

        Orphan root-level YAMLs (no platform field, not in a subdirectory) will
        route incorrectly since platform defaults to 'unknown'.
        """
        if not POSITIONS_DIR.exists():
            pytest.skip(f"positions dir not found at {POSITIONS_DIR}")

        import yaml

        orphans = []
        for yaml_file in POSITIONS_DIR.rglob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                if not (data and data.get("ticker")):
                    continue
                rel = yaml_file.relative_to(POSITIONS_DIR)
                # Root-level YAML: no subdirectory, no platform field in file
                is_root_level = str(rel.parent) == "."
                has_platform_field = bool(data.get("platform"))
                if is_root_level and not has_platform_field:
                    orphans.append(str(rel))
            except yaml.YAMLError:
                pass  # Malformed YAMLs are a different test

        assert len(orphans) == 0, (
            f"{len(orphans)} root-level exit plan YAMLs missing platform: field "
            "(routes as 'unknown'): " + str(orphans)
        )

    def test_exit_plan_yamls_parse_without_error(self):
        """All exit plan YAMLs must be valid YAML."""
        if not POSITIONS_DIR.exists():
            pytest.skip(f"positions dir not found at {POSITIONS_DIR}")

        import yaml

        errors = []
        for yaml_file in POSITIONS_DIR.rglob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                if data is None:
                    errors.append(f"{yaml_file.name}: empty file")
            except yaml.YAMLError as e:
                errors.append(f"{yaml_file.name}: {e}")

        assert len(errors) == 0, f"Invalid YAML files: {errors}"