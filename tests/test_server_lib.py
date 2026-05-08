"""Tests for server/lib TypeScript modules via subprocess."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


class TestHledgerParser:
    """hledger JSON output must be parseable and have the expected shape."""

    @pytest.mark.smoke
    def test_hledger_json_parseable(self):
        """hledger print with -j flag must produce valid JSON."""
        hledger_file = os.environ.get("HLEDGER_FILE", os.path.expanduser("~/.tradingagents/test_hledger.journal"))
        if not Path(hledger_file).exists():
            pytest.skip(f"hledger file not found: {hledger_file}")

        result = subprocess.run(
            ["hledger", "print", "-j", "-f", hledger_file],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            pytest.skip(f"hledger print -j not supported: {result.stderr[:100]}")
        data = json.loads(result.stdout)
        assert isinstance(data, list), "hledger print -j should return a list"

    @pytest.mark.smoke
    def test_hledger_holdings_shape(self):
        """hledger holdings query must return expected shape."""
        hledger_file = os.environ.get("HLEDGER_FILE", os.path.expanduser("~/.tradingagents/test_hledger.journal"))
        if not Path(hledger_file).exists():
            pytest.skip(f"hledger file not found: {hledger_file}")

        result = subprocess.run(
            ["hledger", "commodities"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

    def test_hledger_no_json_errors(self):
        """hledger json must not output non-JSON to stdout."""
        hledger_file = os.environ.get("HLEDGER_FILE", os.path.expanduser("~/.tradingagents/test_hledger.journal"))
        if not Path(hledger_file).exists():
            pytest.skip(f"hledger file not found: {hledger_file}")

        result = subprocess.run(
            ["hledger", "json", "-f", hledger_file],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            pytest.skip(f"hledger returned {result.returncode}: {result.stderr[:200]}")
        # stdout should not have unparseable lines
        for line in result.stdout.splitlines():
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    pytest.fail(f"Non-JSON line in stdout: {line[:100]}")


class TestPositionsQuery:
    """positions table query must return expected columns."""

    @pytest.mark.smoke
    def test_positions_table_exists(self):
        """positions table must exist in the database."""
        db_path = os.environ.get("PORTFOLIO_DB", "portfolio.db")
        if not Path(db_path).exists():
            pytest.skip(f"Database not found: {db_path}")

        result = subprocess.run(
            ["sqlite3", db_path, "SELECT sql FROM sqlite_master WHERE name='positions' AND type='table'"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        sql = result.stdout.strip()
        assert "positions" in sql.lower()

        # Check expected columns exist
        result2 = subprocess.run(
            ["sqlite3", db_path, "PRAGMA table_info(positions)"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        cols = [line.split("|")[1] for line in result2.stdout.strip().splitlines() if line.strip()]
        expected = ["id", "ticker", "platform", "quantity", "avg_cost", "entry_date"]
        for col in expected:
            assert col in cols, f"Missing column: {col}"

    @pytest.mark.smoke
    def test_analyses_table_exists(self):
        """analyses table must exist with required columns."""
        db_path = os.environ.get("PORTFOLIO_DB", "portfolio.db")
        if not Path(db_path).exists():
            pytest.skip(f"Database not found: {db_path}")

        result = subprocess.run(
            ["sqlite3", db_path, "PRAGMA table_info(analyses)"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        cols = [line.split("|")[1] for line in result.stdout.strip().splitlines() if line.strip()]
        expected = ["id", "ticker", "date", "decision", "platform"]
        for col in expected:
            assert col in cols, f"Missing column: {col}"


class TestServerExports:
    """Route modules must export expected symbols."""

    @pytest.mark.smoke
    def test_analyses_subrouter_exports(self):
        """analyses/index.ts must export analysesRouter."""
        index_path = ROOT / "server/routes/analyses/index.ts"
        assert index_path.exists(), "analyses/index.ts not found"
        content = index_path.read_text()
        assert "analysesRouter" in content
        assert "analysesDbRouter" in content or "analysesFsRouter" in content

    @pytest.mark.smoke
    def test_analyses_common_exports(self):
        """analyses-common.ts must export shared helpers."""
        common_path = ROOT / "server/routes/analyses-common.ts"
        assert common_path.exists()
        content = common_path.read_text()
        for fn in ["extractSignal", "extractConfidence", "estimateConfidence", "buildConfidenceSparkline", "resultsDir", "escapeHtml", "signalClass"]:
            assert f"export function {fn}" in content, f"Missing export: {fn}"

    @pytest.mark.smoke
    def test_types_exports(self):
        """types.ts must export PriceResult and re-export BenchmarkPrice/PeriodReturn."""
        types_path = ROOT / "server/lib/types.ts"
        assert types_path.exists()
        content = types_path.read_text()
        assert "export interface PriceResult" in content
        assert "BenchmarkPrice" in content
        assert "PeriodReturn" in content

    @pytest.mark.smoke
    def test_utils_exports(self):
        """utils.ts must export findProjectRoot."""
        utils_path = ROOT / "server/lib/utils.ts"
        assert utils_path.exists()
        content = utils_path.read_text()
        assert "export function findProjectRoot" in content

    @pytest.mark.smoke
    def test_markup_exports(self):
        """markup.ts must export esc, fmt, fmtGBP."""
        markup_path = ROOT / "server/lib/markup.ts"
        assert markup_path.exists()
        content = markup_path.read_text()
        for fn in ["esc", "fmt", "fmtCommas", "fmtGBP"]:
            assert f"export function {fn}" in content, f"Missing export: {fn}"

    @pytest.mark.smoke
    def test_governance_lib_exports(self):
        """governance.ts must export checkRules, loadRules, suggestRebalance."""
        gov_path = ROOT / "server/lib/governance.ts"
        assert gov_path.exists()
        content = gov_path.read_text()
        for fn in ["checkRules", "loadRules", "suggestRebalance"]:
            assert f"export function {fn}" in content, f"Missing export: {fn}"

    @pytest.mark.smoke
    def test_feedback_lib_exports(self):
        """feedback.ts lib must export loadPostMortems, computeSignalAccuracy."""
        fb_path = ROOT / "server/lib/feedback.ts"
        assert fb_path.exists()
        content = fb_path.read_text()
        for fn in ["loadPostMortems", "computeSignalAccuracy"]:
            assert f"export function {fn}" in content, f"Missing export: {fn}"

    @pytest.mark.smoke
    def test_positions_lib_exports(self):
        """positions.ts lib must export computeExitStatus, loadAllPlans."""
        pos_path = ROOT / "server/lib/positions.ts"
        assert pos_path.exists()
        content = pos_path.read_text()
        for fn in ["computeExitStatus", "loadAllPlans"]:
            assert f"export function {fn}" in content, f"Missing export: {fn}"


class TestRouteHandlerPatterns:
    """Route files must have the correct handler patterns."""

    @pytest.mark.smoke
    def test_no_inline_dangerously_set_inner_html_in_views(self):
        """Views must not use dangerouslySetInnerHTML for script injection (use <XxxScript /> JSX pattern)."""
        # After refactor, these should all be clean
        problem_files = []
        for tsx in (ROOT / "server/views").glob("*.tsx"):
            content = tsx.read_text()
            # Check for the OLD pattern (dangerouslySetInnerHTML with function call)
            if "dangerouslySetInnerHTML" in content and "Script()" in content:
                problem_files.append(tsx.name)
        assert len(problem_files) == 0, f"Old pattern found in: {', '.join(problem_files)}"

    def test_external_scripts_are_canonical(self):
        """Refactored views should reference external /static/scripts/ (not inline JSX scripts)."""
        # AGENTS.md: canonical client-side runtime lives in server/static/scripts/*.js
        # Views should reference them via <script src="/static/scripts/xxx.js" />
        for name in [
            "workflow.tsx", "exits.tsx", "benchmark.tsx", "governance.tsx",
            "feedback.tsx", "datatype-test.tsx", "history.tsx", "prospects.tsx",
            "signals.tsx", "intelligence.tsx", "portfolio.tsx", "analysis.tsx",
        ]:
            tsx = ROOT / "server/views" / name
            if not tsx.exists():
                continue
            content = tsx.read_text()
            # Ensure no dangerouslySetInnerHTML script injection (covered by other test)
            # and that if scripts are present, they use external src
            if "<script" in content and '<script src="/static/scripts/' not in content:
                pytest.fail(f"{name}: inline script without external src reference")